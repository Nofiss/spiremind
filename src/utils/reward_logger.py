from __future__ import annotations

import os
import json
import time
from typing import Any, Dict

from loguru import logger


class RewardLogger:
    """
    Append-only logger for RL reward events.
    Writes NDJSON lines under logs/rl_rewards.ndjson.
    """

    def __init__(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logs_dir = os.path.join(root, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.file_path = os.path.join(self.logs_dir, "rl_rewards.ndjson")

    def log(self, entry: Dict[str, Any]) -> None:
        try:
            payload = {"ts": time.time(), **entry}
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=True) + "\n")
        except Exception as exc:
            logger.debug(f"RewardLogger write error: {exc}")
