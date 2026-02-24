from __future__ import annotations

from typing import Dict

import numpy as np

from rl.actions import MAX_HAND, MAX_TARGETS


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def encode_observation(state) -> Dict[str, np.ndarray]:
    hp = float(getattr(state, "hp", 0) or 0)
    max_hp = float(getattr(state, "max_hp", 1) or 1)
    energy = float(getattr(state, "energy", 0) or 0)
    block = float(getattr(state, "player_block", 0) or 0)
    turn = float(getattr(state, "turn", 0) or 0)

    obs: Dict[str, np.ndarray] = {}
    obs["player"] = np.array(
        [
            _clamp01(hp / max_hp),
            _clamp01(energy / 10.0),
            _clamp01(block / 100.0),
            _clamp01(turn / 20.0),
        ],
        dtype=np.float32,
    )

    hand = list(getattr(state, "hand", []) or [])
    hand_feat = np.zeros((MAX_HAND, 4), dtype=np.float32)
    for i in range(min(len(hand), MAX_HAND)):
        c = hand[i]
        hand_feat[i, 0] = _clamp01(float(getattr(c, "cost", 0) or 0) / 5.0)
        hand_feat[i, 1] = _clamp01(float(getattr(c, "damage", 0) or 0) / 30.0)
        hand_feat[i, 2] = _clamp01(float(getattr(c, "block_value", 0) or 0) / 30.0)
        hand_feat[i, 3] = 1.0 if getattr(c, "is_playable", False) else 0.0
    obs["hand"] = hand_feat

    monsters = list(getattr(state, "monsters", []) or [])
    mon_feat = np.zeros((MAX_TARGETS, 3), dtype=np.float32)
    for i in range(min(len(monsters), MAX_TARGETS)):
        m = monsters[i]
        chp = float(getattr(m, "current_hp", 0) or 0)
        mhp = float(getattr(m, "max_hp", 1) or 1)
        mon_feat[i, 0] = _clamp01(chp / mhp)
        mon_feat[i, 1] = _clamp01(float(getattr(m, "block", 0) or 0) / 100.0)
        mon_feat[i, 2] = 0.0 if getattr(m, "is_gone", False) else 1.0
    obs["monsters"] = mon_feat

    cmds = set(getattr(state, "available_commands", []) or [])
    cmd_mask = np.array(
        [
            1.0 if "end" in cmds else 0.0,
            1.0 if "play" in cmds else 0.0,
            1.0 if "wait" in cmds else 0.0,
        ],
        dtype=np.float32,
    )
    obs["command_mask"] = cmd_mask
    return obs
