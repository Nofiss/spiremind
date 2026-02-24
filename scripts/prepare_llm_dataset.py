from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Dict, Iterable

from loguru import logger

try:
    from models.state import GameState
    from utils.command_policy import normalize_and_validate_command
    from utils.prompt import build_combat_prompt
except Exception as exc:
    raise SystemExit(
        "Missing imports. Run with PYTHONPATH=src (example: "
        "`PYTHONPATH=src python scripts/prepare_llm_dataset.py`). "
        f"Import error: {exc}"
    )


SYSTEM_PROMPT = "You are a Slay the Spire expert bot. Output only valid game commands."


def _iter_ndjson(path: str) -> Iterable[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _resolve_default_input() -> str:
    src_path = os.path.join("src", "logs", "training_data.ndjson")
    root_path = os.path.join("logs", "training_data.ndjson")
    if os.path.exists(src_path):
        return src_path
    return root_path


def _is_fallback_state(raw: str, normalized: str) -> bool:
    return normalized == "state" and str(raw or "").strip().lower() not in ("state",)


def _lenient_normalize(raw: str | None) -> str | None:
    if not raw:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text == "end":
        return "end"
    if text.startswith("wait"):
        parts = text.split()
        if len(parts) == 1:
            return "wait 0.5"
        return f"wait {parts[1]}"
    if text.startswith("choose"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return f"choose {int(parts[1])}"
        return None
    if text.startswith("play"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2].isdigit():
                return f"play {int(parts[1])} {int(parts[2])}"
            return f"play {int(parts[1])}"
    return None


def build_dataset(
    input_path: str,
    out_dir: str,
    val_pct: float,
    max_end_pct: float,
    exclude_actions: set[str],
    lenient: bool,
) -> int:
    os.makedirs(out_dir, exist_ok=True)
    train_path = os.path.join(out_dir, "train.jsonl")
    val_path = os.path.join(out_dir, "val.jsonl")

    seen = set()
    action_counts: Dict[str, int] = {}
    skips = {
        "invalid_state": 0,
        "not_ready": 0,
        "invalid_action": 0,
        "excluded_action": 0,
        "end_cap": 0,
        "duplicate": 0,
        "lenient_used": 0,
    }

    total_in = 0
    total_out = 0
    total_end = 0

    val_threshold = int(max(0.0, min(1.0, val_pct)) * 100)

    with (
        open(train_path, "w", encoding="utf-8") as train_f,
        open(val_path, "w", encoding="utf-8") as val_f,
    ):
        for entry in _iter_ndjson(input_path):
            total_in += 1
            state_raw = entry.get("state") or {}
            if not isinstance(state_raw, dict):
                skips["invalid_state"] += 1
                continue
            try:
                state = GameState.model_validate(state_raw)
            except Exception:
                skips["invalid_state"] += 1
                continue

            if not getattr(state, "ready_for_command", False):
                skips["not_ready"] += 1
                continue

            action_raw = entry.get("action")
            if not isinstance(action_raw, str) or not action_raw.strip():
                skips["invalid_action"] += 1
                continue

            normalized = normalize_and_validate_command(action_raw, state)
            if (
                not normalized or _is_fallback_state(action_raw, normalized)
            ) and lenient:
                relaxed = _lenient_normalize(action_raw)
                if relaxed:
                    normalized = relaxed
                    skips["lenient_used"] += 1

            if not normalized:
                skips["invalid_action"] += 1
                continue

            if normalized in exclude_actions:
                skips["excluded_action"] += 1
                continue

            if normalized == "end":
                if max_end_pct >= 0.0:
                    projected = (total_end + 1) / max(1, total_out + 1)
                    if projected > max_end_pct:
                        skips["end_cap"] += 1
                        continue

            prompt = build_combat_prompt(state)
            dedupe_key = _hash_text(prompt + "\n" + normalized)
            if dedupe_key in seen:
                skips["duplicate"] += 1
                continue
            seen.add(dedupe_key)

            example = {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": normalized},
                ]
            }

            bucket = int(_hash_text(dedupe_key), 16) % 100
            out_file = val_f if bucket < val_threshold else train_f
            out_file.write(json.dumps(example, ensure_ascii=True) + "\n")

            total_out += 1
            if normalized == "end":
                total_end += 1
            action_counts[normalized] = action_counts.get(normalized, 0) + 1

    logger.info(f"Read: {total_in} lines")
    logger.info(f"Wrote: {total_out} examples")
    logger.info(f"Train file: {train_path}")
    logger.info(f"Val file: {val_path}")

    logger.info("Skip counts:")
    for key, val in skips.items():
        logger.info(f"  {key}: {val}")

    logger.info("Action distribution:")
    for action, count in sorted(action_counts.items(), key=lambda x: (-x[1], x[0])):
        logger.info(f"  {action}: {count}")
    return 0


def main() -> int:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    parser = argparse.ArgumentParser(
        description="Prepare LLM dataset from training logs"
    )
    parser.add_argument(
        "--input",
        default=_resolve_default_input(),
        help="Path to training_data.ndjson (default: src/logs/training_data.ndjson)",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join("data", "llm"),
        help="Output directory for train/val JSONL",
    )
    parser.add_argument(
        "--val-pct",
        type=float,
        default=0.1,
        help="Validation split percentage (0-1)",
    )
    parser.add_argument(
        "--max-end-pct",
        type=float,
        default=0.3,
        help="Max allowed ratio of 'end' actions (0-1); set <0 to disable",
    )
    parser.add_argument(
        "--exclude-action",
        action="append",
        default=["state"],
        help="Exclude actions (repeatable). Default excludes 'state'.",
    )
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="Accept simple commands even when validation falls back to 'state'.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Input file not found: {args.input}")
        return 1

    exclude_actions = {str(a).strip().lower() for a in args.exclude_action if a}
    return build_dataset(
        input_path=args.input,
        out_dir=args.out_dir,
        val_pct=args.val_pct,
        max_end_pct=args.max_end_pct,
        exclude_actions=exclude_actions,
        lenient=args.lenient,
    )


if __name__ == "__main__":
    raise SystemExit(main())
