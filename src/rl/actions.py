from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


MAX_HAND = 10
MAX_TARGETS = 3


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    card_index: Optional[int] = None
    target_index: Optional[int] = None


def build_action_catalog() -> List[ActionSpec]:
    actions: List[ActionSpec] = [
        ActionSpec(kind="end"),
        ActionSpec(kind="wait"),
    ]
    for idx1 in range(1, MAX_HAND + 1):
        actions.append(ActionSpec(kind="play", card_index=idx1))
        for t in range(MAX_TARGETS):
            actions.append(ActionSpec(kind="play", card_index=idx1, target_index=t))
    return actions


_ACTION_CATALOG = build_action_catalog()


def action_count() -> int:
    return len(_ACTION_CATALOG)


def action_id_to_spec(action_id: int) -> ActionSpec:
    return _ACTION_CATALOG[int(action_id)]


def build_action_mask(state) -> np.ndarray:
    mask = np.zeros(action_count(), dtype=np.float32)
    if not state:
        return mask

    cmds = set(getattr(state, "available_commands", []) or [])
    hand = list(getattr(state, "hand", []) or [])
    monsters = list(getattr(state, "monsters", []) or [])

    for i, spec in enumerate(_ACTION_CATALOG):
        if spec.kind == "end":
            if "end" in cmds:
                mask[i] = 1.0
            continue
        if spec.kind == "wait":
            if "wait" in cmds:
                mask[i] = 1.0
            continue
        if spec.kind == "play":
            if "play" not in cmds:
                continue
            idx1 = spec.card_index or 0
            if idx1 < 1 or idx1 > len(hand):
                continue
            card = hand[idx1 - 1]
            if not getattr(card, "is_playable", False):
                continue
            needs_target = bool(getattr(card, "has_target", False))
            if needs_target and spec.target_index is None:
                continue
            if not needs_target and spec.target_index is not None:
                continue
            if needs_target:
                t = int(spec.target_index or 0)
                if t < 0 or t >= len(monsters):
                    continue
                m = monsters[t]
                if getattr(m, "is_gone", False) or getattr(m, "current_hp", 0) <= 0:
                    continue
            mask[i] = 1.0
    return mask


def action_id_to_command(action_id: int, state) -> Optional[str]:
    try:
        spec = action_id_to_spec(action_id)
    except Exception:
        return None

    if spec.kind == "end":
        return "end"
    if spec.kind == "wait":
        return "wait 0.5"
    if spec.kind == "play":
        idx1 = spec.card_index
        if idx1 is None:
            return None
        if spec.target_index is None:
            return f"play {idx1}"
        return f"play {idx1} {spec.target_index}"
    return None
