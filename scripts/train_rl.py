from __future__ import annotations

import os
from pathlib import Path

from loguru import logger


def main() -> int:
    try:
        from stable_baselines3 import PPO
    except Exception as exc:
        logger.error(f"stable-baselines3 missing: {exc}")
        return 1

    from rl.envs.spire_env import SpireEnv

    env = SpireEnv(seed=0)
    model = PPO("MultiInputPolicy", env, verbose=1)
    model.learn(total_timesteps=50_000)

    out_dir = Path("data") / "rl_models"
    os.makedirs(out_dir, exist_ok=True)
    out_path = out_dir / "spire_ppo"
    model.save(str(out_path))
    logger.info(f"Saved model to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
