from __future__ import annotations

from typing import Dict, Any

import numpy as np

import gymnasium as gym

from rl.actions import action_count, action_id_to_command, build_action_mask
from rl.features import encode_observation
from rl.mock.sim_game import SimGame


class SpireEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self._py_rng = __import__("random").Random(int(seed))
        self.sim = SimGame(self._py_rng)
        self.action_space = gym.spaces.Discrete(action_count())
        self.observation_space = gym.spaces.Dict(
            {
                "player": gym.spaces.Box(0.0, 1.0, shape=(4,), dtype=np.float32),
                "hand": gym.spaces.Box(0.0, 1.0, shape=(10, 4), dtype=np.float32),
                "monsters": gym.spaces.Box(0.0, 1.0, shape=(3, 3), dtype=np.float32),
                "command_mask": gym.spaces.Box(0.0, 1.0, shape=(3,), dtype=np.float32),
            }
        )

    def reset(self, *, seed: int | None = None, options: Dict[str, Any] | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self._py_rng.seed(int(seed))
        state = self.sim.reset()
        obs = encode_observation(state)
        info = {"action_mask": build_action_mask(state)}
        return obs, info

    def step(self, action: int):
        state = self.sim._build_state()
        cmd = action_id_to_command(action, state)
        next_state, reward, terminated, truncated = self.sim.step(cmd or "")
        obs = encode_observation(next_state)
        info = {"action_mask": build_action_mask(next_state), "last_command": cmd}
        return obs, reward, terminated, truncated, info

    def render(self):
        return None

    def close(self):
        return None
