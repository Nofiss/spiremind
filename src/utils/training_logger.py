import os
import json
import time
from typing import Any, Dict
from loguru import logger


class TrainingLogger:
    """
    Append-only logger of (state -> action -> result) tuples for future fine-tuning.
    Writes NDJSON lines under logs/training_data.ndjson.
    """

    def __init__(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logs_dir = os.path.join(root, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.file_path = os.path.join(self.logs_dir, "training_data.ndjson")

    def log(self, state: Dict[str, Any], action: str, result: Dict[str, Any]):
        try:
            entry = {
                "ts": time.time(),
                "state": state,
                "action": action,
                "result": result,
            }
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception as e:
            logger.debug(f"TrainingLogger write error: {e}")
