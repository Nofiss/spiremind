from typing import List, Optional
from loguru import logger
from models.state import GameState
import re


def alive_targets(state: GameState) -> List[int]:
    return [
        i
        for i, m in enumerate(state.monsters)
        if not getattr(m, "is_gone", False) and getattr(m, "current_hp", 0) > 0
    ]


def parse_incoming_damage(state: GameState) -> int:
    total = 0
    for m in state.monsters:
        if getattr(m, "is_gone", False) or getattr(m, "current_hp", 0) <= 0:
            continue
        intent = str(getattr(m, "intent", ""))
        for a, b in re.findall(r"(\d+)x(\d+)", intent):
            try:
                total += int(a) * int(b)
            except Exception:
                pass
        intent_clean = re.sub(r"(\d+)x(\d+)", "", intent)
        for n in re.findall(r"\d+", intent_clean):
            try:
                total += int(n)
            except Exception:
                pass
    return total


def lethal_action(state: GameState) -> Optional[str]:
    if "play" not in (state.available_commands or []):
        return None
    alive = alive_targets(state)
    if not alive:
        return None
    target_idx = min(
        alive,
        key=lambda i: (
            max(0, getattr(state.monsters[i], "current_hp", 0))
            + max(0, getattr(state.monsters[i], "block", 0))
        ),
    )
    target = state.monsters[target_idx]
    target_hp = max(0, getattr(target, "current_hp", 0)) + max(
        0, getattr(target, "block", 0)
    )

    candidates = []
    for i, c in enumerate(state.hand):
        if not getattr(c, "is_playable", False):
            continue
        if str(getattr(c, "type", "")).upper() != "ATTACK":
            continue
        dmg = int(getattr(c, "damage", 0) or 0)
        if dmg <= 0:
            continue
        candidates.append((i + 1, c, dmg))

    if not candidates:
        return None

    total_damage = sum(d for _, __, d in candidates)
    if total_damage < target_hp:
        return None

    candidates.sort(key=lambda t: t[2], reverse=True)
    idx1, card, _ = candidates[0]
    if getattr(card, "has_target", False):
        return f"play {idx1} {target_idx}"
    return f"play {idx1}"


def block_action(state: GameState) -> Optional[str]:
    if getattr(state, "player_block", 0) > 0:
        return None
    incoming = parse_incoming_damage(state)
    if incoming <= 0:
        return None
    if "play" not in (state.available_commands or []):
        return None

    skills = []
    for i, c in enumerate(state.hand):
        if not getattr(c, "is_playable", False):
            continue
        if str(getattr(c, "type", "")).upper() != "SKILL":
            continue
        blk = int(getattr(c, "block_value", 0) or 0)
        if blk <= 0:
            continue
        cost = int(getattr(c, "cost", 0) or 0)
        skills.append((i + 1, c, blk, cost))

    if not skills:
        return None

    energy = max(0, int(getattr(state, "energy", 0) or 0))
    dp = [(0, [])] + [(-1, []) for _ in range(energy)]
    for idx1, _card, blk, cost in skills:
        for e in range(energy, cost - 1, -1):
            prev_blk, prev_idxs = dp[e - cost]
            if prev_blk >= 0:
                new_blk = prev_blk + blk
                if new_blk > dp[e][0]:
                    dp[e] = (new_blk, prev_idxs + [idx1])

    best_combo: List[int] = []
    best_blk = 0
    best_overshoot = 10**9
    for e in range(0, energy + 1):
        blk, combo = dp[e]
        if blk < 0:
            continue
        overshoot = max(0, blk - incoming)
        if blk >= incoming:
            if overshoot < best_overshoot or (
                overshoot == best_overshoot and blk > best_blk
            ):
                best_overshoot = overshoot
                best_blk = blk
                best_combo = combo
        else:
            if best_blk < incoming and blk > best_blk:
                best_blk = blk
                best_combo = combo

    if best_combo:
        chosen = max((s for s in skills if s[0] in best_combo), key=lambda t: t[2])
        return f"play {chosen[0]}"

    chosen = max(skills, key=lambda t: t[2])
    return f"play {chosen[0]}"


def potion_action(state: GameState) -> Optional[str]:
    cmds = set(state.available_commands or [])
    if not cmds:
        return None
    max_hp = max(1, int(getattr(state, "max_hp", 0) or 1))
    hp = max(0, int(getattr(state, "hp", 0) or 0))
    low_hp = hp <= 0.2 * max_hp

    use_cmd = None
    for cand in ("use_potion", "potion", "use", "drink"):
        if cand in cmds:
            use_cmd = cand
            break
    if use_cmd is None:
        return None

    potions = list(getattr(state, "potions", []) or [])
    if not potions:
        return None

    def potion_kind(p):
        s = str(getattr(p, "name", getattr(p, "type", p)) or "").lower()
        return s

    idx_to_use = None
    room_type = str(getattr(state, "room_type", "")).lower()
    turn = int(getattr(state, "turn", 0) or 0)
    if ("elite" in room_type) and turn <= 1:
        for i, p in enumerate(potions):
            k = potion_kind(p)
            if any(x in k for x in ("strength", "dexterity", "force", "destrezza")):
                idx_to_use = i
                break

    if idx_to_use is None and low_hp:
        for i, p in enumerate(potions):
            k = potion_kind(p)
            if any(x in k for x in ("heal", "healing", "block", "armor", "guard")):
                idx_to_use = i
                break

    if idx_to_use is None:
        return None
    return f"{use_cmd} {idx_to_use}"


def heuristic_action(state: GameState) -> Optional[str]:
    try:
        act = lethal_action(state)
        if act:
            logger.info(f"Heuristic lethal -> {act}")
            return act
        act = block_action(state)
        if act:
            logger.info(f"Heuristic block -> {act}")
            return act
        act = potion_action(state)
        if act:
            logger.info(f"Heuristic potion -> {act}")
            return act
    except Exception as e:
        logger.debug(f"Heuristic layer error: {e}")
    return None
