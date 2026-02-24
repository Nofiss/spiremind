import os
import json
from typing import Optional, List, Tuple
import struct
from loguru import logger


class GameRAG:
    """
    SQL Server 2025 vector-store backed lookup for multiple entity types:
    - relics: dbo.relics(name, description, embedding VARBINARY(MAX))
    - cards:  dbo.cards(name, description, embedding VARBINARY(MAX))
    - events: dbo.events(name, description, embedding VARBINARY(MAX))
    Falls back to local JSON caches if DB/driver is unavailable.
    """

    def __init__(self):
        self.conn = None
        # Prefer .env config over OS environment
        try:
            from utils.config_loader import get as cfg_get
        except Exception:
            cfg_get = lambda k, d=None: os.getenv(k, d)

        self.embed_model = cfg_get("RAG_EMBED_MODEL", "llama3") or "llama3"
        self.conn_str = cfg_get("SQLSERVER_CONN_STR", "") or ""
        # Optional local cache fallback (per entity)
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def load_cache(name: str):
            path = os.path.join(root, f"{name}_cache.json")
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
            except Exception as e:
                logger.debug(f"RAG cache load error ({name}): {e}")
            return {}

        self.cache_relics = load_cache("relics")
        self.cache_cards = load_cache("cards")
        self.cache_events = load_cache("events")

        # Try connect to SQL Server via pyodbc
        try:
            if self.conn_str:
                import pyodbc  # type: ignore

                self.pyodbc = pyodbc
                self.conn = pyodbc.connect(self.conn_str, autocommit=True)
                logger.info("RelicRAG: SQL Server connection established")
            else:
                self.pyodbc = None
        except Exception as e:
            logger.debug(f"RelicRAG: SQL Server connection failed: {e}")
            self.conn = None
            self.pyodbc = None

        # Embeddings via Ollama
        try:
            import ollama

            self.ollama = ollama
        except Exception as e:
            logger.debug(f"RelicRAG: Ollama not available for embeddings: {e}")
            self.ollama = None

    def is_connected(self) -> bool:
        return bool(self.conn and self.pyodbc)

    def _embed(self, text: str) -> Optional[List[float]]:
        if not self.ollama:
            return None
        try:
            res = self.ollama.embed(model=self.embed_model, input=text)
            # ollama returns { 'embeddings': [[...]] } or {'embedding': [...] } depending on version
            vec = res.get("embedding") or (res.get("embeddings") or [[]])[0]
            return list(vec)
        except Exception as e:
            logger.debug(f"RelicRAG: embedding error: {e}")
            return None

    def _pack_vector(self, vec: List[float]) -> bytes:
        # Pack floats into little-endian float32 bytes
        try:
            return struct.pack("<" + "f" * len(vec), *vec)
        except Exception:
            # Fallback: JSON bytes (less efficient, but may work with custom UDFs)
            return json.dumps(vec).encode("utf-8")

    def _vector_search(self, table: str, vec: List[float]) -> Optional[Tuple[str, str]]:
        if not (self.conn and self.pyodbc):
            return None
        # Prefer native vector ANN query; allow overriding via env var
        try:
            from utils.config_loader import get as cfg_get
        except Exception:
            cfg_get = lambda k, d=None: os.getenv(k, d)
        sql = cfg_get(
            "SQLSERVER_VECTOR_SEARCH_SQL",
            # Default pattern using native ANN search hint and cosine distance
            # Adjust to your build’s vector function/operator syntax
            "SELECT TOP 1 name, description FROM dbo.{table} WITH (ANN_SEARCH=ON) "
            "ORDER BY VECTOR_COSINE_DISTANCE(embedding, ?) ASC",
        )
        sql = (
            sql
            or "SELECT TOP 1 name, description FROM dbo.{table} WITH (ANN_SEARCH=ON) ORDER BY VECTOR_COSINE_DISTANCE(embedding, ?) ASC"
        ).replace("{table}", table)
        payload = self._pack_vector(vec)
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (payload,))
            row = cur.fetchone()
            if row:
                return (str(row[0]), str(row[1]))
        except Exception as e:
            logger.debug(f"RelicRAG: vector search error: {e}")
        return None

    def _vector_search_k(
        self, table: str, vec: List[float], k: int = 3
    ) -> List[Tuple[str, str]]:
        results: List[Tuple[str, str]] = []
        if not (self.conn and self.pyodbc):
            return results
        try:
            k = max(1, int(k))
        except Exception:
            k = 3
        base_sql = (
            f"SELECT TOP {k} name, description FROM dbo.{{table}} WITH (ANN_SEARCH=ON) "
            f"ORDER BY VECTOR_COSINE_DISTANCE(embedding, ?) ASC"
        )
        sql = base_sql.replace("{table}", table)
        payload = self._pack_vector(vec)
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (payload,))
            rows = cur.fetchall() or []
            for r in rows:
                try:
                    results.append((str(r[0]), str(r[1])))
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"RelicRAG: vector search K error: {e}")
        return results

    def _exact_lookup(self, table: str, name: str) -> Optional[str]:
        # Try SQL exact match first
        if self.conn and self.pyodbc:
            try:
                cur = self.conn.cursor()
                cur.execute(
                    f"SELECT TOP 1 description FROM dbo.{table} WHERE LOWER(name)=LOWER(?)",
                    (name,),
                )
                row = cur.fetchone()
                if row:
                    return str(row[0])
            except Exception as e:
                logger.debug(f"RelicRAG: SQL exact lookup error: {e}")
        # Fallback to cache
        try:
            q = (name or "").strip().lower()
            cache = {
                "relics": self.cache_relics,
                "cards": self.cache_cards,
                "events": self.cache_events,
            }.get(table, {})
            for k, v in cache.items():
                if k.lower() == q:
                    return str(v)
        except Exception:
            pass
        return None

    def search(self, entity_type: str, query: str) -> Optional[str]:
        table = (
            "relics"
            if entity_type.lower() == "relic"
            else (
                "cards"
                if entity_type.lower() == "card"
                else ("events" if entity_type.lower() == "event" else None)
            )
        )
        if not table:
            return None
        name = (query or "").strip()
        # 1) Exact lookup
        desc = self._exact_lookup(table, name)
        if desc:
            return desc
        # 2) Vector search if embedding available
        vec = self._embed(name)
        if vec:
            hit = self._vector_search(table, vec)
            if hit:
                return hit[1]
        return None

    def search_top_k(
        self, entity_type: str, query: str, k: int = 3
    ) -> List[Tuple[str, str]]:
        table = (
            "relics"
            if entity_type.lower() == "relic"
            else (
                "cards"
                if entity_type.lower() == "card"
                else ("events" if entity_type.lower() == "event" else None)
            )
        )
        if not table:
            return []
        name = (query or "").strip()
        vec = self._embed(name)
        if not vec:
            return []
        return self._vector_search_k(table, vec, k)

    # Convenience wrappers
    def search_relic(self, name: str) -> Optional[str]:
        return self.search("relic", name)

    def search_card(self, name: str) -> Optional[str]:
        return self.search("card", name)

    def search_event(self, name: str) -> Optional[str]:
        return self.search("event", name)

    # Auto-ingest (cards/events/relics)
    def _exists(self, table: str, name: str) -> bool:
        if self.conn and self.pyodbc:
            try:
                cur = self.conn.cursor()
                cur.execute(
                    f"SELECT 1 FROM dbo.{table} WHERE LOWER(name)=LOWER(?)",
                    (name,),
                )
                return cur.fetchone() is not None
            except Exception as e:
                logger.debug(f"GameRAG: exists check failed: {e}")
        # Fallback to cache
        cache = {
            "relics": self.cache_relics,
            "cards": self.cache_cards,
            "events": self.cache_events,
        }.get(table, {})
        return (name or "").strip().lower() in {k.lower() for k in cache.keys()}

    def _insert(
        self, table: str, name: str, description: str, vec: List[float]
    ) -> bool:
        if not (self.conn and self.pyodbc):
            return False
        try:
            payload = self._pack_vector(vec)
            cur = self.conn.cursor()
            logger.info(f"GameRAG: ingest -> {table} name='{name}' len(vec)={len(vec)}")
            # Try structured insert first based on table; fallback to minimal
            try:
                if table == "cards":
                    # Attempt to read extra fields from description JSON if provided
                    # In general runtime, we don’t pass structured here; a separate upsert can enrich later
                    cur.execute(
                        "INSERT INTO dbo.cards(name, description, embedding) VALUES (?, ?, ?)",
                        (name, description, payload),
                    )
                elif table == "relics":
                    cur.execute(
                        "INSERT INTO dbo.relics(name, description, embedding) VALUES (?, ?, ?)",
                        (name, description, payload),
                    )
                elif table == "events":
                    cur.execute(
                        "INSERT INTO dbo.events(name, description, embedding) VALUES (?, ?, ?)",
                        (name, description, payload),
                    )
                else:
                    cur.execute(
                        f"INSERT INTO dbo.{table}(name, description, embedding) VALUES (?, ?, ?)",
                        (name, description, payload),
                    )
            except Exception:
                # Fallback generic minimal insert
                cur.execute(
                    f"INSERT INTO dbo.{table}(name, description, embedding) VALUES (?, ?, ?)",
                    (name, description, payload),
                )
            try:
                self.conn.commit()
            except Exception:
                pass
            logger.info(f"GameRAG: ingest OK -> {table} '{name}'")
            return True
        except Exception as e:
            logger.debug(f"GameRAG: insert failed: {e}")
            return False

    def ensure_card(self, name: str, description: str) -> bool:
        """Ensure the card exists in dbo.cards; insert if missing with embedded description."""
        try:
            if not name:
                return False
            exists = self._exists("cards", name)
            if exists:
                logger.debug(f"GameRAG: card already exists '{name}'")
                return False
            if not self.is_connected():
                logger.info(f"GameRAG: DB not connected; skip ingest card '{name}'")
                return False
            vec = self._embed(description or name) or []
            return self._insert("cards", name, description or name, vec)
        except Exception:
            return False

    def ensure_relic(self, name: str, description: str) -> bool:
        """Ensure the relic exists in dbo.relics; insert if missing with embedded description."""
        try:
            if not name:
                return False
            exists = self._exists("relics", name)
            if exists:
                logger.debug(f"GameRAG: relic already exists '{name}'")
                return False
            if not self.is_connected():
                logger.info(f"GameRAG: DB not connected; skip ingest relic '{name}'")
                return False
            vec = self._embed(description or name) or []
            return self._insert("relics", name, description or name, vec)
        except Exception:
            return False

    def ensure_event(self, name: str, description: str) -> bool:
        """Ensure the event exists in dbo.events; insert if missing with embedded description."""
        try:
            if not name:
                return False
            exists = self._exists("events", name)
            if exists:
                logger.debug(f"GameRAG: event already exists '{name}'")
                return False
            if not self.is_connected():
                logger.info(f"GameRAG: DB not connected; skip ingest event '{name}'")
                return False
            vec = self._embed(description or name) or []
            return self._insert("events", name, description or name, vec)
        except Exception:
            return False

    # Structured fetch helpers
    def fetch_card_info(self, name: str) -> Optional[dict]:
        if not (self.conn and self.pyodbc):
            return None
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT TOP 1 type, cost, character, tags FROM dbo.cards WHERE LOWER(name)=LOWER(?)",
                (name,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "type": str(row[0]) if row[0] is not None else None,
                    "cost": int(row[1]) if row[1] is not None else None,
                    "character": str(row[2]) if row[2] is not None else None,
                    "tags": str(row[3]) if row[3] is not None else None,
                }
        except Exception as e:
            logger.debug(f"GameRAG: fetch_card_info failed: {e}")
        return None

    def fetch_relic_info(self, name: str) -> Optional[dict]:
        if not (self.conn and self.pyodbc):
            return None
        try:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT TOP 1 type, tags FROM dbo.relics WHERE LOWER(name)=LOWER(?)",
                (name,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "type": str(row[0]) if row[0] is not None else None,
                    "tags": str(row[1]) if row[1] is not None else None,
                }
        except Exception as e:
            logger.debug(f"GameRAG: fetch_relic_info failed: {e}")
        return None


# Backward-compat adapter
class RelicRAG:
    """Backward-compatible relic-only RAG wrapper using GameRAG internally."""

    def __init__(self):
        self._rag = GameRAG()

    def search(self, query: str) -> Optional[str]:
        return self._rag.search_relic(query)
