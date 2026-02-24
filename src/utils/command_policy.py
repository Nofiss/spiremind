import re
from typing import Optional

from loguru import logger
from models.state import GameState


def normalize_and_validate_command(
    cmd: str | None, state: GameState, *, default_class: str = "ironclad"
) -> str | None:
    if not cmd:
        return _fallback(state)

    raw_original = str(cmd)
    cmd = _extract_action_line(raw_original)
    cmd = cmd.strip().lower()
    if not cmd:
        return _fallback(state)

    cmd = re.sub(r"[^a-z0-9_\s\.]", "", cmd)
    parts = [p for p in cmd.split() if p]
    if not parts:
        return _fallback(state)

    cmds = _normalized_commands(state)
    base = parts[0]

    base = _apply_aliases(base, cmds)

    if base == "state":
        return (
            _log_result(raw_original, "state", "state")
            if ("state" in cmds or cmds)
            else None
        )

    if base == "wait":
        if "wait" not in cmds:
            return _fallback(state)
        if len(parts) == 1:
            return _log_result(raw_original, "wait", "wait 0.5")
        try:
            float(parts[1])
            return _log_result(raw_original, "wait", f"wait {parts[1]}")
        except Exception:
            return _log_result(raw_original, "wait", "wait 0.5")

    if base == "end":
        return (
            _log_result(raw_original, "end", "end")
            if "end" in cmds
            else _fallback(state)
        )

    if base == "play":
        return _log_result(raw_original, "play", _normalize_play(parts, state, cmds))

    if base == "potion":
        return _log_result(
            raw_original, "potion", _normalize_potion(parts, state, cmds)
        )

    if base == "start":
        return _log_result(
            raw_original, "start", _normalize_start(parts, cmds, default_class)
        )

    if base == "continue":
        if "continue" in cmds:
            return _log_result(raw_original, "continue", "continue")
        return _fallback(state)

    if base == "choose":
        return _log_result(
            raw_original, "choose", _normalize_choose(parts, state, cmds)
        )

    if base in ("proceed", "confirm", "leave", "cancel"):
        if base in cmds:
            return _log_result(raw_original, base, base)
        return _fallback(state)

    return _fallback(state)


def _extract_action_line(text: str) -> str:
    try:
        for ln in text.splitlines():
            if ln.strip().lower().startswith("action:"):
                return ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return text


def _normalized_commands(state: GameState) -> set[str]:
    try:
        return {str(c).strip().lower() for c in (state.available_commands or []) if c}
    except Exception:
        return set()


def _fallback(state: GameState) -> str | None:
    cmds = _normalized_commands(state)
    if "state" in cmds:
        return "state"
    if getattr(state, "in_game", False) and "end" in cmds:
        return "end"
    return None


def _apply_aliases(base: str, cmds: set[str]) -> str:
    if base in ("use_potion", "drink", "use"):
        return "potion" if "potion" in cmds else base
    if base in ("pass",):
        return "end"
    if base in ("resume",):
        return "continue"
    if base in ("next",):
        return "proceed"
    if base in ("ok",):
        return "confirm"
    if base in ("exit",):
        return "leave"
    if base in ("buy", "purchase", "take", "click"):
        return "choose" if "choose" in cmds else base
    return base


def _normalize_play(parts: list[str], state: GameState, cmds: set[str]) -> str | None:
    if "play" not in cmds:
        return _fallback(state)
    if len(parts) < 2:
        return _fallback(state)
    try:
        idx_raw = int(parts[1])
    except Exception:
        return _fallback(state)

    hand = list(getattr(state, "hand", []) or [])
    if not hand:
        return _fallback(state)

    if 1 <= idx_raw <= len(hand):
        idx1 = idx_raw
    elif 0 <= idx_raw < len(hand):
        idx1 = idx_raw + 1
    else:
        return _fallback(state)

    card = hand[idx1 - 1]
    if not getattr(card, "is_playable", False):
        return _fallback(state)

    needs_target = bool(getattr(card, "has_target", False))
    if not needs_target:
        return f"play {idx1}"

    target = _pick_target(parts, state)
    if target is None:
        return _fallback(state)
    return f"play {idx1} {target}"


def _normalize_potion(parts: list[str], state: GameState, cmds: set[str]) -> str | None:
    if "potion" not in cmds:
        return _fallback(state)
    if len(parts) < 2:
        return _fallback(state)
    try:
        idx = int(parts[1])
    except Exception:
        return _fallback(state)

    potions = list(getattr(state, "potions", []) or [])
    if idx < 0 or idx >= len(potions):
        return _fallback(state)

    potion = potions[idx]
    requires_target = _potion_requires_target(potion)
    target = _pick_target(parts, state)
    if requires_target and target is None:
        return _fallback(state)

    if target is None:
        return f"potion {idx}"
    return f"potion {idx} {target}"


def _normalize_start(
    parts: list[str], cmds: set[str], default_class: str
) -> str | None:
    if "start" not in cmds:
        return None
    cls = parts[1] if len(parts) >= 2 else default_class
    cls = str(cls or default_class).lower()
    if cls not in ("ironclad", "silent", "defect"):
        cls = default_class

    extra = []
    for p in parts[2:]:
        if re.fullmatch(r"\d+", p):
            extra.append(p)
    return " ".join(["start", cls] + extra)


def _normalize_choose(parts: list[str], state: GameState, cmds: set[str]) -> str | None:
    if "choose" not in cmds:
        return _fallback(state)
    if len(parts) < 2:
        return _fallback(state)
    try:
        idx = int(parts[1])
    except Exception:
        return _fallback(state)

    choice_list = list(getattr(state, "choice_list", []) or [])
    if choice_list:
        if idx < 0 or idx >= len(choice_list):
            return _fallback(state)
    else:
        if idx < 0:
            return _fallback(state)

    return f"choose {idx}"


def _pick_target(parts: list[str], state: GameState) -> Optional[int]:
    alive = [
        i
        for i, m in enumerate(getattr(state, "monsters", []) or [])
        if not getattr(m, "is_gone", False) and getattr(m, "current_hp", 0) > 0
    ]
    if not alive:
        return None

    if len(parts) >= 3:
        try:
            t = int(parts[2])
            if t in alive:
                return t
        except Exception:
            pass

    return alive[0]


def _potion_requires_target(potion: object) -> bool:
    try:
        if isinstance(potion, dict):
            return bool(
                potion.get("requires_target")
                or potion.get("requiresTarget")
                or potion.get("target_required")
            )
    except Exception:
        pass
    return False


def _log_result(raw: str, base: str, normalized: str | None) -> str | None:
    if not normalized:
        logger.debug(f"CMD_INVALID: raw='{raw}'")
        return None
    raw_clean = _extract_action_line(raw).strip().lower()
    raw_clean = re.sub(r"[^a-z0-9_\s\.]", "", raw_clean)
    if normalized in ("state", "end") and raw_clean not in ("state", "end"):
        logger.debug(f"CMD_FALLBACK: raw='{raw}' -> '{normalized}'")
        return normalized
    if raw_clean and normalized != raw_clean:
        logger.debug(f"CMD_NORM: raw='{raw}' -> '{normalized}'")
    return normalized
