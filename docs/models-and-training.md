# Models And Training Overview

This document explains the model types used in SpireMind, how they are trained,
and how they interact at runtime. It is written for external readers who want a
functional understanding without digging into the code.

## High-Level Flow

1) The game sends state over stdin.
2) The orchestrator builds a decision request.
3) A decision is produced by RL (if enabled), otherwise by an LLM agent.
4) The command is normalized and validated before being written to stdout.
5) Training data is logged for future fine-tuning.

Core runtime entry points:
- Orchestrator: `src/core/orchestrator.py`
- Agents: `src/agents/ollama_agent.py`, `src/agents/lora_agent.py`,
  `src/agents/rl_agent.py`
- Command safety: `src/utils/command_policy.py`

## Model Types

### 1) LLM Agent (Ollama)

Purpose
- General decision-making via prompting.
- Default fallback agent when LoRA is not enabled or available.

Implementation
- Class: `OllamaAgent` in `src/agents/ollama_agent.py`
- Uses the Ollama runtime (`ollama.chat`) with a compact combat prompt
  (`src/utils/prompt.py`).

Decision flow
- Heuristic shortcuts run first (lethal, block, potion usage).
- Optional RAG notes are appended to the prompt (shop items, relics).
- LLM output is sanitized and normalized via `normalize_and_validate_command`.

Dependencies
- Core dependency: `ollama` (already in base `pyproject.toml`).
- Requires a local Ollama model, default `llama3`.

### 2) LLM Agent (LoRA / Unsloth)

Purpose
- Local, fine-tuned LLM for faster or more specialized command generation.

Implementation
- Class: `LoraAgent` in `src/agents/lora_agent.py`.
- Loads a LoRA fine-tuned model via Unsloth and runs inference locally.

Decision flow
- Heuristic shortcuts run first (same logic as Ollama).
- The prompt is generated with the same `build_combat_prompt` function.
- Output is sanitized by the same command policy layer.

Dependencies
- Optional extra group: `llm` in `pyproject.toml`.
- Requires `unsloth`, `torch`, and related libraries.

### 3) Reinforcement Learning (PPO)

Purpose
- Fast policy selection for combat actions using a learned agent.
- Runs before LLMs and can short-circuit LLM usage when confident.

Implementation
- Class: `RlAgent` in `src/agents/rl_agent.py`.
- Uses Stable-Baselines3 PPO to load a policy from disk.

Inputs and action space
- Observation encoding: `src/rl/features.py` (player/hand/monsters/command mask).
- Action catalog: `src/rl/actions.py` (end, wait, play with targets).
- Action mask enforces valid actions against the current state.

Dependencies
- Optional extra group: `rl` in `pyproject.toml`.
- Requires `gymnasium` and `stable-baselines3`.

## Training Pipelines

### LoRA / QLoRA (LLM)

Data generation
- The system logs gameplay data to NDJSON at
  `logs/training_data.ndjson` via `src/utils/training_logger.py`.
- A dataset builder converts logs into chat JSONL:
  `scripts/prepare_llm_dataset.py`.

Training script
- Unsloth-based fine-tuning script:
  `scripts/llm/train_spire.py`.
- Documentation: `docs/LLM_TRAINING.md`.

Artifacts
- Output model directory defaults to `spiremind_lora_model`.
- Runtime uses `LORA_MODEL_PATH` from `src/config.py`.

### Reinforcement Learning (PPO)

Environment
- Uses a mock simulation environment for training:
  `src/rl/envs/spire_env.py` and `src/rl/mock/sim_game.py`.
- This is not a full game integration; it is a lightweight training loop.

Training script
- `scripts/train_rl.py` trains PPO for 50k timesteps and saves the model.
- Output location defaults to `data/rl_models/spire_ppo`.

Artifacts
- Runtime loads from `RL_MODEL_PATH` in `src/config.py`.

## How Models Interact At Runtime

Priority
1) If `USE_RL_AGENT` is enabled and the RL model is loaded, RL produces an
   action first.
2) If RL returns no action, the active LLM agent is used.
3) The LLM agent is determined by `USE_LORA_AGENT`:
   - True: `LoraAgent` with fallback to `OllamaAgent` if loading fails.
   - False: `OllamaAgent` is used directly.

Safety and validation
- All commands pass through `normalize_and_validate_command` to enforce:
  - Allowed actions from `available_commands`.
  - 1-based card indexing and valid target selection.
  - Safe fallbacks (`state` or `end`) when actions are invalid.

Heuristics
- Both LLM agents run a heuristic layer before generating text.
- Heuristics are in `src/agents/heuristics.py` and include:
  - Lethal damage checks
  - Block optimization via DP over energy
  - Potion use triggers (low HP, early elite)

## Configuration Summary

Primary toggles in `src/config.py`:
- `USE_LORA_AGENT`: switch LLM engine to LoRA (Unsloth).
- `USE_RL_AGENT`: enable PPO policy inference.
- `LORA_MODEL_PATH`: directory containing the fine-tuned LoRA model.
- `RL_MODEL_PATH`: PPO model file path.

Optional dependency groups in `pyproject.toml`:
- `llm`: Unsloth + Torch + Transformers stack.
- `rl`: Gymnasium + Stable-Baselines3.

## Practical Notes

- RL training is currently based on a mock simulation, not live game feedback.
- The system is designed to stay safe: invalid commands are corrected or
  replaced with `state` / `end` instead of crashing.
- Training data logging is always append-only and can be used for both LoRA
  fine-tuning and future RL pipelines.
