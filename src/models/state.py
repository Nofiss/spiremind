from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from loguru import logger
import time


_PARSE_LOG_LAST: dict[str, float] = {}


def _rate_limit_log(key: str, min_interval: float = 10.0) -> bool:
    now = time.time()
    last = _PARSE_LOG_LAST.get(key, 0.0)
    if now - last >= min_interval:
        _PARSE_LOG_LAST[key] = now
        return True
    return False


# --- Sottomodelli ---
class Card(BaseModel):
    name: str
    cost: int = 0  # Default a 0 se manca
    is_playable: bool = False
    has_target: bool = False
    type: str = "UNKNOWN"
    # Valori numerici opzionali (se forniti dal gioco/mod)
    damage: int = 0
    block_value: int = 0


class Monster(BaseModel):
    name: str
    current_hp: int = 0
    max_hp: int = 0
    intent: str = "UNKNOWN"
    block: int = 0
    is_gone: bool = False


class MapNode(BaseModel):
    node_id: str = ""
    x: int = 0
    y: int = 0
    type: str = "UNKNOWN"
    edges: List[str] = Field(default_factory=list)


# --- Modello Principale ---
class GameState(BaseModel):
    # Configurazione per ignorare campi extra non definiti qui
    model_config = ConfigDict(extra="ignore")

    # CAMPI ROBUSTI (Con Default)
    # Se 'available_commands' manca, usa una lista vuota
    available_commands: List[str] = Field(default_factory=list)

    # Se 'ready_for_command' manca, assumiamo False per sicurezza
    ready_for_command: bool = False

    in_game: bool = False

    # Dati opzionali (potrebbero essere None o mancare)
    screen_type: str = "UNKNOWN"
    room_phase: str = "UNKNOWN"

    # Dati di gioco specifici (Default ai valori minimi)
    hand: List[Card] = Field(default_factory=list)
    monsters: List[Monster] = Field(default_factory=list)
    energy: int = 0
    hp: int = Field(default=0, alias="current_hp")
    max_hp: int = 0
    # Block corrente del player (se disponibile)
    player_block: int = 0
    # Elenco pozioni (se disponibile). Struttura libera: dict/name string.
    potions: List[Any] = Field(default_factory=list)
    # Turno corrente della battaglia (se disponibile)
    turn: int = 0
    # Tipo di stanza (per distinguere Elite/Boss/Normal se disponibile)
    room_type: str = "UNKNOWN"
    # Valuta
    gold: int = 0
    # Mappa e scelte
    map_nodes: List[MapNode] = Field(default_factory=list)
    map_choices: List[str] = Field(default_factory=list)
    # Deck completo (nomi)
    deck: List[str] = Field(default_factory=list)
    # Opzioni carta ricompensa (strutturate)
    reward_cards: List[Card] = Field(default_factory=list)
    # Opzioni generiche testuali (es. "Remove a card", ecc.)
    generic_choices: List[str] = Field(default_factory=list)
    # Relics posseduti e oggetti del negozio
    relics: List[str] = Field(default_factory=list)
    # Oggetti del negozio: lista di dict {name, price, type}
    shop_items: List[Any] = Field(default_factory=list)
    # Lista scelte shop (UI order) e mapping dettagliato
    choice_list: List[str] = Field(default_factory=list)
    shop_choices: List[dict] = Field(default_factory=list)

    @classmethod
    def parse(cls, raw: dict):
        """
        Parser difensivo che appiattisce la struttura nidificata
        e gestisce i casi limite.
        """
        # 1. Estrazione sicura dei sotto-dizionari
        game_data = raw.get("game_state") or {}  # Se è None, usa {}
        combat_data = game_data.get("combat_state") or {}
        player_data = combat_data.get("player") or {}

        # 2. Merge dei dati
        # L'ordine è importante: i dati più specifici sovrascrivono quelli generali
        merged = {
            **raw,  # Livello root (available_commands, ready_for_command)
            **game_data,  # Livello game (screen_type, room_phase)
            **combat_data,  # Livello combat (monsters, hand)
            **player_data,  # Livello player (energy, current_hp)
        }

        # 2b. Normalizza comandi disponibili
        try:
            cmds_raw = raw.get(
                "available_commands", merged.get("available_commands", [])
            )
            if isinstance(cmds_raw, list):
                cmds = [str(c).strip().lower() for c in cmds_raw if str(c).strip()]
            elif isinstance(cmds_raw, str):
                if "," in cmds_raw:
                    cmds = [c.strip().lower() for c in cmds_raw.split(",") if c.strip()]
                else:
                    cmds = [c.strip().lower() for c in cmds_raw.split() if c.strip()]
            else:
                cmds = []
            merged["available_commands"] = cmds
            if not cmds and _rate_limit_log("parse_missing_available_commands"):
                logger.debug("PARSE_MISS: available_commands missing or empty")
        except Exception:
            pass

        # 2c. Normalizza screen_type e room_phase
        try:
            st = game_data.get("screen_type", merged.get("screen_type", "UNKNOWN"))
            merged["screen_type"] = str(st or "UNKNOWN").upper()
            if merged["screen_type"] == "UNKNOWN" and _rate_limit_log(
                "parse_fallback_screen_type"
            ):
                logger.debug("PARSE_FALLBACK: screen_type=UNKNOWN")
        except Exception:
            pass
        try:
            rp = game_data.get("room_phase", merged.get("room_phase", "UNKNOWN"))
            merged["room_phase"] = str(rp or "UNKNOWN").upper()
            if merged["room_phase"] == "UNKNOWN" and _rate_limit_log(
                "parse_fallback_room_phase"
            ):
                logger.debug("PARSE_FALLBACK: room_phase=UNKNOWN")
        except Exception:
            pass

        # 3. Normalizzazione di hand e monsters per gestire alias dei campi
        try:
            hand_raw = combat_data.get("hand") or merged.get("hand") or []
            normalized_hand = []
            for item in hand_raw:
                if isinstance(item, dict):
                    norm = {
                        "name": item.get("name") or item.get("card_name") or "UNKNOWN",
                        "cost": item.get("cost", item.get("energy_cost", 0)),
                        # alias: playable / can_play
                        "is_playable": item.get(
                            "is_playable",
                            item.get("playable", item.get("can_play", False)),
                        ),
                        # alias: target_required / requires_target
                        "has_target": item.get(
                            "has_target",
                            item.get(
                                "target_required", item.get("requires_target", False)
                            ),
                        ),
                        # alias: card_type / type
                        "type": item.get("type", item.get("card_type", "UNKNOWN")),
                        # valori numerici opzionali
                        "damage": item.get("damage", item.get("base_damage", 0)),
                        "block_value": item.get(
                            "block_value", item.get("block", item.get("base_block", 0))
                        ),
                    }
                    normalized_hand.append(norm)
                else:
                    # Non-dict (es. stringhe) -> fallback minimo
                    normalized_hand.append(
                        {
                            "name": str(item),
                            "cost": 0,
                            "is_playable": False,
                            "has_target": False,
                            "type": "UNKNOWN",
                            "damage": 0,
                            "block_value": 0,
                        }
                    )
            merged["hand"] = normalized_hand
        except Exception:
            pass

        try:
            monsters_raw = combat_data.get("monsters") or merged.get("monsters") or []
            normalized_monsters = []
            for m in monsters_raw:
                if isinstance(m, dict):
                    norm_m = {
                        "name": m.get("name") or "UNKNOWN",
                        "current_hp": m.get("current_hp", m.get("hp", 0)),
                        "max_hp": m.get("max_hp", m.get("maxHp", 0)),
                        "intent": m.get("intent", "UNKNOWN"),
                        "block": m.get("block", 0),
                        # alias: gone
                        "is_gone": m.get("is_gone", m.get("gone", False)),
                    }
                    normalized_monsters.append(norm_m)
                else:
                    normalized_monsters.append(
                        {
                            "name": str(m),
                            "current_hp": 0,
                            "max_hp": 0,
                            "intent": "UNKNOWN",
                            "block": 0,
                            "is_gone": False,
                        }
                    )
            merged["monsters"] = normalized_monsters
        except Exception:
            pass

        # 4. Validazione Pydantic
        # Normalizzazione pozioni (se presenti)
        try:
            potions_raw = combat_data.get("potions") or merged.get("potions") or []
            merged["potions"] = potions_raw if isinstance(potions_raw, list) else []
        except Exception:
            pass

        # Player block (se fornito dal livello player)
        try:
            merged["player_block"] = int(
                player_data.get("block", merged.get("player_block", 0)) or 0
            )
        except Exception:
            pass

        # Max HP (alias robusti)
        try:
            merged["max_hp"] = int(
                player_data.get(
                    "max_hp", player_data.get("maxHp", merged.get("max_hp", 0))
                )
                or 0
            )
        except Exception:
            pass

        # Turno
        try:
            merged["turn"] = int(
                combat_data.get(
                    "turn", combat_data.get("turn_number", merged.get("turn", 0))
                )
                or 0
            )
        except Exception:
            pass

        # Tipo di stanza
        try:
            merged["room_type"] = str(
                game_data.get("room_type", merged.get("room_type", "UNKNOWN"))
                or "UNKNOWN"
            ).upper()
        except Exception:
            pass

        # Gold
        try:
            merged["gold"] = int(
                player_data.get("gold", merged.get("gold", raw.get("gold", 0))) or 0
            )
        except Exception:
            pass

        # Mappa
        try:
            map_raw = game_data.get("map") or raw.get("map") or []
            nodes: List[dict] = []
            for item in map_raw:
                if isinstance(item, dict):
                    x = int(item.get("x", item.get("col", 0)) or 0)
                    y = int(item.get("y", item.get("row", item.get("floor", 0))) or 0)
                    t = str(
                        item.get("type", item.get("room_type", "UNKNOWN")) or "UNKNOWN"
                    )
                    symbol = str(item.get("symbol", ""))
                    if symbol and symbol != "NONE":
                        symbol_map = {
                            "R": "REST",
                            "E": "ELITE",
                            "$": "SHOP",
                            "?": "UNKNOWN",
                            "M": "MONSTER",
                            "T": "TREASURE",
                        }
                        t_norm = symbol_map.get(symbol.upper(), "UNKNOWN")
                    else:
                        t_up = t.upper()
                        if "ELITE" in t_up:
                            t_norm = "ELITE"
                        elif "REST" in t_up or "CAMP" in t_up or "FIRE" in t_up:
                            t_norm = "REST"
                        elif "SHOP" in t_up or "MERCHANT" in t_up:
                            t_norm = "SHOP"
                        elif "MONSTER" in t_up or "ENEMY" in t_up or "FIGHT" in t_up:
                            t_norm = "MONSTER"
                        elif "TREASURE" in t_up or "CHEST" in t_up:
                            t_norm = "TREASURE"
                        else:
                            t_norm = "UNKNOWN"
                    edges_raw = (
                        item.get(
                            "edges", item.get("connections", item.get("links", []))
                        )
                        or []
                    )
                    if not edges_raw and item.get("children"):
                        edges_raw = item.get("children") or []
                    edges: List[str] = []
                    for e in edges_raw:
                        if isinstance(e, dict):
                            ex = int(e.get("x", e.get("col", 0)) or 0)
                            ey = int(e.get("y", e.get("row", e.get("floor", 0))) or 0)
                            edges.append(f"{ex}:{ey}")
                        elif isinstance(e, (list, tuple)) and len(e) >= 2:
                            edges.append(f"{int(e[0])}:{int(e[1])}")
                        else:
                            edges.append(str(e))
                    nid = str(item.get("node_id", item.get("id", f"{x}:{y}")))
                    nodes.append(
                        {"node_id": nid, "x": x, "y": y, "type": t_norm, "edges": edges}
                    )
                elif isinstance(item, (list, tuple)) and len(item) >= 3:
                    try:
                        x = int(item[0])
                        y = int(item[1])
                        t = str(item[2])
                        edges = [str(e) for e in (item[3] if len(item) > 3 else [])]
                        nid = f"{x}:{y}"
                        nodes.append(
                            {"node_id": nid, "x": x, "y": y, "type": t, "edges": edges}
                        )
                    except Exception:
                        pass
            merged["map_nodes"] = nodes
        except Exception:
            pass

        # Scelte mappa (ordine dei bottoni)
        try:
            choices_raw = (
                game_data.get("map_choices")
                or game_data.get("available_nodes")
                or (game_data.get("screen_state") or {}).get("next_nodes")
                or (raw.get("screen_state") or {}).get("next_nodes")
                or raw.get("map_choices")
                or []
            )
            choices: List[str] = []
            for c in choices_raw:
                if isinstance(c, dict):
                    cx = int(c.get("x", c.get("col", 0)) or 0)
                    cy = int(c.get("y", c.get("row", c.get("floor", 0))) or 0)
                    nid = str(c.get("node_id", c.get("id", f"{cx}:{cy}")))
                    choices.append(nid)
                elif isinstance(c, (list, tuple)) and len(c) >= 2:
                    choices.append(f"{int(c[0])}:{int(c[1])}")
                else:
                    choices.append(str(c))
            merged["map_choices"] = choices
        except Exception:
            pass

        # Deck
        try:
            deck_raw = (
                game_data.get("deck")
                or game_data.get("master_deck")
                or raw.get("deck")
                or []
            )
            deck_list: List[str] = []
            for d in deck_raw:
                if isinstance(d, dict):
                    nm = d.get("name", d.get("card_name", d.get("id", "UNKNOWN")))
                    deck_list.append(str(nm))
                else:
                    deck_list.append(str(d))
            merged["deck"] = deck_list
        except Exception:
            pass

        # Card reward options
        try:
            reward_raw = (
                game_data.get("card_reward")
                or game_data.get("reward_cards")
                or (game_data.get("screen_state") or {}).get("cards")
                or (raw.get("screen_state") or {}).get("cards")
                or raw.get("card_reward")
                or []
            )
            reward_norm: List[dict] = []
            for item in reward_raw:
                if isinstance(item, dict):
                    reward_norm.append(
                        {
                            "name": item.get("name", item.get("card_name", "UNKNOWN")),
                            "cost": item.get("cost", item.get("energy_cost", 0)),
                            "is_playable": True,
                            "has_target": item.get(
                                "has_target", item.get("requires_target", False)
                            ),
                            "type": item.get("type", item.get("card_type", "UNKNOWN")),
                            "damage": item.get("damage", item.get("base_damage", 0)),
                            "block_value": item.get(
                                "block_value",
                                item.get("block", item.get("base_block", 0)),
                            ),
                        }
                    )
                else:
                    reward_norm.append(
                        {
                            "name": str(item),
                            "cost": 0,
                            "is_playable": True,
                            "has_target": False,
                            "type": "UNKNOWN",
                            "damage": 0,
                            "block_value": 0,
                        }
                    )
            merged["reward_cards"] = reward_norm
        except Exception:
            pass

        # Generic textual choices (events/shop)
        try:
            gen_choices = game_data.get("choices") or raw.get("choices") or []
            merged["generic_choices"] = (
                [str(x) for x in gen_choices] if isinstance(gen_choices, list) else []
            )
        except Exception:
            pass

        # Relics
        try:
            relics_raw = (
                player_data.get("relics")
                or game_data.get("relics")
                or raw.get("relics")
                or []
            )
            merged["relics"] = [
                (r.get("name") if isinstance(r, dict) else str(r)) for r in relics_raw
            ]
        except Exception:
            pass

        # Shop items (support dict with name/price/type; fallback to strings)
        try:
            screen_state = game_data.get("screen_state") or {}
            shop_raw = (
                game_data.get("shop_items") or game_data.get("shop") or screen_state
            )
            items: List[dict] = []

            def _norm_item(obj: dict, category: str) -> dict:
                nm = (
                    obj.get("name")
                    or obj.get("id")
                    or obj.get("card_name")
                    or obj.get("relic_name")
                    or "UNKNOWN"
                )
                pr = obj.get("price", obj.get("cost", obj.get("gold", None)))
                tp = obj.get("type", obj.get("item_type", category))
                return {
                    "name": str(nm),
                    "price": pr,
                    "type": str(tp),
                    "category": category,
                }

            if isinstance(shop_raw, list):
                for it in shop_raw:
                    if isinstance(it, dict):
                        items.append(_norm_item(it, "UNKNOWN"))
                    else:
                        items.append(
                            {
                                "name": str(it),
                                "price": None,
                                "type": "UNKNOWN",
                                "category": "UNKNOWN",
                            }
                        )
            elif isinstance(shop_raw, dict):
                for c in shop_raw.get("cards", []) or []:
                    if isinstance(c, dict):
                        items.append(_norm_item(c, "CARD"))
                for p in shop_raw.get("potions", []) or []:
                    if isinstance(p, dict):
                        items.append(_norm_item(p, "POTION"))
                for r in shop_raw.get("relics", []) or []:
                    if isinstance(r, dict):
                        items.append(_norm_item(r, "RELIC"))
                if shop_raw.get("purge_available"):
                    items.append(
                        {
                            "name": "purge",
                            "price": shop_raw.get("purge_cost", None),
                            "type": "PURGE",
                            "category": "PURGE",
                        }
                    )
            merged["shop_items"] = items
        except Exception:
            pass

        # Shop choice list mapping (UI order)
        try:
            choice_list = (
                game_data.get("choice_list")
                or (game_data.get("screen_state") or {}).get("choice_list")
                or []
            )
            merged["choice_list"] = (
                [str(x) for x in choice_list] if isinstance(choice_list, list) else []
            )

            # Build detailed choices mapping name->price/type/category based on screen_state sections
            ss = game_data.get("screen_state") or {}
            by_name = {}
            for c in ss.get("cards", []) or []:
                if isinstance(c, dict):
                    nm = str(c.get("name", "")).lower()
                    by_name[nm] = {
                        "name": c.get("name"),
                        "price": c.get("price"),
                        "type": c.get("type", "CARD"),
                        "category": "CARD",
                    }
            for p in ss.get("potions", []) or []:
                if isinstance(p, dict):
                    nm = str(p.get("name", "")).lower()
                    by_name[nm] = {
                        "name": p.get("name"),
                        "price": p.get("price"),
                        "type": "POTION",
                        "category": "POTION",
                    }
            for r in ss.get("relics", []) or []:
                if isinstance(r, dict):
                    nm = str(r.get("name", "")).lower()
                    by_name[nm] = {
                        "name": r.get("name"),
                        "price": r.get("price"),
                        "type": "RELIC",
                        "category": "RELIC",
                    }

            choices_detailed: List[dict] = []
            for idx, nm in enumerate(merged["choice_list"]):
                key = nm.lower()
                if key in ("purge", "remove"):
                    choices_detailed.append(
                        {
                            "index": idx,
                            "name": "purge",
                            "price": ss.get("purge_cost", None),
                            "type": "PURGE",
                            "category": "PURGE",
                        }
                    )
                else:
                    data = by_name.get(key) or {
                        "name": nm,
                        "price": None,
                        "type": "UNKNOWN",
                        "category": "UNKNOWN",
                    }
                    data_with_index = {"index": idx, **data}
                    choices_detailed.append(data_with_index)
            merged["shop_choices"] = choices_detailed
        except Exception:
            pass

        return cls.model_validate(merged)
