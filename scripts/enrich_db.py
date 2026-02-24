"""
Enrich SQL Server 2025 vector store with structured fields for cards and relics.

Reads a curated JSON (default: data/wiki.json) with entries:
{
  "cards": [
    {"name": "Heavy Blade", "description": "...", "type": "ATTACK", "cost": 2, "character": "IRONCLAD", "tags": ["strength"]},
    ...
  ],
  "relics": [
    {"name": "Kunai", "description": "...", "type": "RELIC", "tags": ["dexterity", "attack-synergy"]},
    ...
  ]
}

Upserts rows into dbo.cards and dbo.relics, setting structured columns and embedding.
"""

import os
import sys
import json
import struct
from typing import Dict, Any, List
from loguru import logger


def get_env(key: str, default: str | None = None) -> str | None:
    try:
        from utils import config_loader

        # Ensure .env is loaded from configs/.env or overridden path
        config_loader.reload()
        return config_loader.get(key, default)
    except Exception:
        return os.getenv(key, default)


def connect_db():
    import pyodbc  # type: ignore

    conn_str = get_env("SQLSERVER_CONN_STR", "") or ""
    if not conn_str:
        raise RuntimeError("SQLSERVER_CONN_STR not set in .env or environment")
    return pyodbc.connect(conn_str, autocommit=True)


def embed(text: str) -> List[float]:
    import ollama  # type: ignore

    model = get_env("RAG_EMBED_MODEL", "llama3") or "llama3"
    res = ollama.embed(model=model, input=text or "")
    vec = res.get("embedding") or (res.get("embeddings") or [[]])[0]
    return list(vec)


def pack_vec(vec: List[float]) -> bytes:
    try:
        return struct.pack("<" + "f" * len(vec), *vec)
    except Exception:
        return json.dumps(vec).encode("utf-8")


def to_tags_str(tags: Any) -> str:
    if tags is None:
        return ""
    if isinstance(tags, str):
        return tags
    if isinstance(tags, (list, tuple)):
        return ",".join(str(t) for t in tags)
    return str(tags)


def upsert_card(cur, item: Dict[str, Any]):
    name = str(item.get("name") or "").strip()
    if not name:
        return
    desc = str(item.get("description") or "")
    type_ = str(item.get("type") or "")
    character = str(item.get("character") or "")
    cost = item.get("cost")
    try:
        cost = int(cost) if cost is not None else None
    except Exception:
        cost = None
    tags = to_tags_str(item.get("tags"))

    vec = embed(desc)
    payload = pack_vec(vec)

    # UPDATE first
    cur.execute(
        "UPDATE dbo.cards SET description=?, type=?, cost=?, character=?, tags=?, embedding=? WHERE LOWER(name)=LOWER(?)",
        (desc, type_, cost, character, tags, payload, name),
    )
    if cur.rowcount and cur.rowcount > 0:
        logger.info(f"Updated card: {name}")
        return
    # INSERT
    cur.execute(
        "INSERT INTO dbo.cards(name, description, type, cost, character, tags, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, desc, type_, cost, character, tags, payload),
    )
    logger.info(f"Inserted card: {name}")


def upsert_relic(cur, item: Dict[str, Any]):
    name = str(item.get("name") or "").strip()
    if not name:
        return
    desc = str(item.get("description") or "")
    type_ = str(item.get("type") or "")
    tags = to_tags_str(item.get("tags"))

    vec = embed(desc)
    payload = pack_vec(vec)

    # UPDATE first
    cur.execute(
        "UPDATE dbo.relics SET description=?, type=?, tags=?, embedding=? WHERE LOWER(name)=LOWER(?)",
        (desc, type_, tags, payload, name),
    )
    if cur.rowcount and cur.rowcount > 0:
        logger.info(f"Updated relic: {name}")
        return
    # INSERT
    cur.execute(
        "INSERT INTO dbo.relics(name, description, type, tags, embedding) VALUES (?, ?, ?, ?, ?)",
        (name, desc, type_, tags, payload),
    )
    logger.info(f"Inserted relic: {name}")


def main(json_path: str):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cards = data.get("cards") or []
    relics = data.get("relics") or []
    cn = connect_db()
    cur = cn.cursor()
    logger.info(
        f"Upserting {len(cards)} cards and {len(relics)} relics from {json_path}"
    )
    for c in cards:
        try:
            upsert_card(cur, c)
        except Exception as e:
            logger.error(f"Card upsert failed: {c.get('name')}: {e}")
    for r in relics:
        try:
            upsert_relic(cur, r)
        except Exception as e:
            logger.error(f"Relic upsert failed: {r.get('name')}: {e}")
    try:
        cn.commit()
    except Exception:
        pass
    cn.close()
    logger.info("Done.")


if __name__ == "__main__":
    # Usage: python scripts/enrich_db.py [path/to/wiki.json]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_path = os.path.join(root, "data", "wiki.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default_path
    main(path)
