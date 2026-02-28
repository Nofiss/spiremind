from __future__ import annotations

from typing import Optional, Tuple
import os

import numpy as np
from loguru import logger

from rl.actions import build_action_mask, action_id_to_command
from rl.features import encode_observation


class RlAgent:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.last_action_id: Optional[int] = None
        self.last_obs: Optional[dict] = None
        self._load_model()

    def _resolve_model_path(self) -> str:
        path = self.model_path or ""
        candidates = [path]
        if path.endswith(".zip.zip"):
            candidates.append(path[: -len(".zip")])
        elif path and not path.endswith(".zip"):
            candidates.append(path + ".zip")

        for cand in candidates:
            if cand and os.path.exists(cand):
                if cand != path:
                    logger.warning(f"RL model path corrected: {path} -> {cand}")
                return cand
        return path

    def _load_model(self) -> None:
        try:
            from stable_baselines3 import PPO

            resolved = self._resolve_model_path()
            self.model = PPO.load(resolved)
            self.model_path = resolved
            logger.info(f"RL model loaded: {resolved}")
        except Exception as exc:
            self.model = None
            logger.error(f"RL model load failed: {exc}")

    def think(self, state) -> Tuple[Optional[str], Optional[int], Optional[dict]]:
        if not self.model:
            return None, None, None
        obs = encode_observation(state)
        action_mask = build_action_mask(state)
        if action_mask.sum() <= 0:
            return None, None, None
        action, _ = self.model.predict(obs, deterministic=True)
        action_id = int(action)
        if action_mask[action_id] <= 0.0:
            valid = np.where(action_mask > 0.0)[0]
            if len(valid) == 0:
                return None, None, None
            action_id = int(valid[0])
        self.last_action_id = action_id
        self.last_obs = obs
        return action_id_to_command(action_id, state), action_id, obs
