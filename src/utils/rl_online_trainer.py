from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import torch
from loguru import logger


@dataclass
class Transition:
    obs: dict
    action: int
    reward: float
    done: bool


class RlOnlineTrainer:
    def __init__(self, model):
        self.model = model
        self._buffer: List[Transition] = []

    def record(self, obs: dict, action: int) -> None:
        if not self.model:
            return
        self._buffer.append(Transition(obs=obs, action=action, reward=0.0, done=False))

    def apply_reward(self, reward: float, done: bool, reason: str) -> None:
        if not self.model or not self._buffer:
            return
        for t in self._buffer:
            t.reward = float(reward)
            t.done = bool(done)
        try:
            self._train_on_buffer()
            logger.info(
                f"RL online update: steps={len(self._buffer)} reward={reward:.3f} reason={reason}"
            )
        except Exception as exc:
            logger.error(f"RL online update failed: {exc}")
        finally:
            self._buffer.clear()

    def _train_on_buffer(self) -> None:
        if not self._buffer:
            return
        try:
            from stable_baselines3.common.buffers import RolloutBuffer
        except Exception as exc:
            raise RuntimeError(
                "stable-baselines3 required for online training"
            ) from exc

        obs_list = [t.obs for t in self._buffer]
        action_arr = np.array([t.action for t in self._buffer], dtype=np.int64)
        reward_arr = np.array([t.reward for t in self._buffer], dtype=np.float32)
        done_arr = np.array([t.done for t in self._buffer], dtype=np.float32)

        policy = self.model.policy
        obs_tensor = policy.obs_to_tensor(obs_list)[0]
        policy.set_training_mode(True)
        actions_tensor = torch.as_tensor(action_arr, device=policy.device)
        values, log_probs, _ = policy.evaluate_actions(obs_tensor, actions_tensor)

        rollout = RolloutBuffer(
            buffer_size=len(self._buffer),
            observation_space=self.model.observation_space,
            action_space=self.model.action_space,
            device=self.model.device,
            gae_lambda=self.model.gae_lambda,
            gamma=self.model.gamma,
            n_envs=1,
        )
        for i, t in enumerate(self._buffer):
            episode_start = i == 0
            rollout.add(
                t.obs,
                np.array(t.action, dtype=np.int64),
                float(t.reward),
                episode_start,
                values[i].detach(),
                log_probs[i].detach(),
            )

        last_values = values[-1].detach()
        rollout.compute_returns_and_advantage(
            last_values=last_values, dones=np.array([done_arr[-1]], dtype=np.float32)
        )
        self.model.rollout_buffer = rollout
        self.model.train()
