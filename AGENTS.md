# SpireMind Agents Guide

This document gives agentic coding agents a practical, repo-specific playbook for building, linting, testing, and contributing code in this repository. It reflects how the codebase is structured and the conventions already in use.

## Project Overview

- Language/runtime: Python 3.12+
- Entry point: `src/main.py` (starts GUI and orchestrator threads)
- Packages: `src/core`, `src/agents`, `src/models`, `src/utils`, `src/gui`
- Dependencies (from `pyproject.toml`): `customtkinter`, `loguru`, `ollama`, `pydantic`
- Logging: central file logger in `src/utils/logger.py` (Loguru)
- IPC: `src/core/communication.py` manages stdio with a non‑blocking queue and a background input listener thread
- AI: `src/agents/ollama_agent.py` (Ollama chat) with command sanitization
- State modeling: `src/models/state.py` (Pydantic models and a defensive parser)

## Environment Setup

Use a Python 3.12 virtual environment.

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

Install dependencies (pyproject lists runtime deps; there is no `requirements.txt`).

```bash
# Simple and reliable: install explicit deps
pip install "customtkinter>=5.2.2" "loguru>=0.7.3" "ollama>=0.6.1" "pydantic>=2.12.5"

# Optional: add dev tooling
pip install ruff black mypy pytest
```

Ollama setup (required for the agent):

```bash
# Ensure Ollama is installed and running
ollama --version
ollama serve  # or ensure the service is running
ollama pull llama3
```

## Build and Run

- Run the application (GUI + orchestrator):

```bash
python src/main.py
```

- The app writes logs to `logs/spire_mind.log` and uses `stop.txt` in repo root as a kill‑switch.
- GUI uses CustomTkinter in dark mode; on headless environments it will not render.

## Linting, Formatting, Types

Adopt these tools consistently across the repo:

```bash
# Lint (Ruff)
ruff check src

# Format (Black)
black src

# Types (Mypy)
```

Fast pre‑commit style checks (combine):

```bash
ruff check src && black --check src && mypy src
```

## Testing

There are currently no test files in the repo. Use `pytest` for new tests and place them under `tests/` or co‑locate with modules as `test_*.py`.

Run all tests:

```bash
pytest -q
```

Run a single test via node id:

```bash
pytest -q tests/test_ollama_agent.py::test_sanitize_command_play_with_target
```

Filter by name with `-k`:

```bash
pytest -q -k sanitize_command
```

Example test layout suggestion:

```python
# tests/test_ollama_agent.py
from src.models.state import GameState, Card, Monster
from src.agents.ollama_agent import OllamaAgent

def test_sanitize_command_play_with_target():
    state = GameState(
        available_commands=["play", "end"],
        ready_for_command=True,
        in_game=True,
        hand=[Card(name="Strike", cost=1, is_playable=True, has_target=True)],
        monsters=[Monster(name="Cultist", current_hp=40)],
    )
    agent = OllamaAgent()
    assert agent.sanitize_command("play 1 0", state) == "play 1 0"
```

## Imports and Module Structure

- Code runs from `src/main.py` and assumes the `src` directory is on `sys.path`.
- Within `src/*`, use absolute imports rooted at `src` packages (e.g., `from core.orchestrator import SpireOrchestrator`, `from gui.dashboard import SpireDashboard`).
- From non‑`src` locations (e.g., tests at repo root), prefer running modules with `python -m src.main` or add `src` to `PYTHONPATH` in test configuration.
- Avoid introducing new `sys.path` hacks; keep imports consistent with the existing pattern.

## Formatting Conventions

- Line length: aim for 100 columns max; wrap thoughtfully.
- Strings: prefer double quotes unless single quotes avoid escaping.
- Indentation: 4 spaces; no tabs.
- Trailing commas: allow in multi‑line literals and argument lists.
- ASCII only by default; use UTF‑8 only where required (file I/O already uses `encoding="utf-8"`).
- Minimal comments; add them only when non‑obvious logic benefits from context.

## Types and Pydantic

- Use type hints on public functions and methods; keep return types explicit.
- Model classes live in `src/models/state.py` and use Pydantic v2.
- Favor defensive parsing: see `GameState.parse` which flattens nested input, normalizes alias fields, and ignores extras.
- When extending models, keep defaults safe (e.g., empty lists, zero values) and set `model_config = ConfigDict(extra='ignore')` unless stricter parsing is needed.

## Naming Conventions

- Classes: `CamelCase` (e.g., `SpireOrchestrator`, `OllamaAgent`).
- Functions/methods/variables: `snake_case` (e.g., `ai_thread_task`, `sanitize_command`).
- Constants: `UPPER_SNAKE_CASE` in `config.py` (e.g., `MENU_ACTION_DELAY`).
- Modules/packages: lowercase, words separated by underscores where needed.

## Error Handling and Logging

- Use Loguru logger via `SpireLogger` initialized early in `main.py`.
- Do not print to stdout; stdout is reserved for game commands (`SpireBridge.write`).
- Catch exceptions at thread boundaries and IO points; log with appropriate level (`error`, `warning`, `info`, `debug`).
- Fail safe: on unexpected errors from AI (Ollama) or parsing, prefer safe fallbacks (e.g., return `"end"` or request `"state"`).
- Avoid crashing the GUI or orchestrator loop; protect background threads with try/except.

## Concurrency and IPC

- `SpireBridge` runs a background input listener thread reading stdin and places lines onto a `queue.Queue`.
- Use `read_line_nowait()` to poll without blocking main loops.
- Only send commands via `SpireBridge.write`; throttle or delay as needed (`BotConfig.MENU_ACTION_DELAY`).
- When adding new AI actions, gate by `state.available_commands` and `state.ready_for_command`.
- For `play` commands: cards are 1‑based indices; targets are 0‑based. Validate indexes, card playability, and target aliveness.

## GUI Practices

- `src/gui/dashboard.py` uses CustomTkinter; keep UI updates on the main thread.
- Use `after(...)` for periodic state refresh; avoid blocking calls in callbacks.
- Log user actions to the textbox via `add_log`; keep messages short and informative.
- Respect kill‑switch semantics (`stop.txt`) and orchestrator flags (`paused`, `autostart`).

## AI Agent Guidelines

- Build prompts in `OllamaAgent.build_prompt` with concise state summaries.
- Always sanitize model output via `sanitize_command` before sending to the game.
- Prefer `state` fallback when a command is invalid or ambiguous.
- Log sanitization differences at `info` level to assist troubleshooting.

## File Paths and IO

- Resolve project root via `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` inside `src/*`.
- Use `os.path.join` and avoid hard‑coded separators.
- When writing files (e.g., `stop.txt`, logs), specify `encoding="utf-8"`.

## Cursor/Copilot Rules

- No Cursor rules found in `.cursor/rules/` or `.cursorrules`.
- No Copilot instructions found at `.github/copilot-instructions.md`.
- If you add these later, mirror the guidance here and call them out explicitly for agents.

## Git Hygiene for Agents

- Keep changes scoped; do not revert user edits you did not make.
- Prefer small, focused commits with clear messages (explain the "why").
- Do not force push or amend without explicit instruction.
- Avoid committing secrets; never add auth tokens to the repo.

## Common Commands Cheat Sheet

```bash
# Run app
python src/main.py

# Lint/format/types
ruff check src
black src
mypy src

# Tests
pytest -q
pytest -q tests/test_file.py::TestClass::test_case
pytest -q -k some_name

# Ollama model setup
ollama pull llama3
```

## Adding Tests Quickly

- Place new tests under `tests/`.
- Use `pytest` fixtures for state setup; test both happy paths and defensive fallbacks.
- Mock `ollama.chat` for deterministic behavior when testing `OllamaAgent.think`.

## Final Notes

- Maintain the existing import style and defensive programming posture.
- Favor readability and safety over cleverness; the orchestrator must remain stable.
- Keep stdout clean (only game commands); all diagnostics go to the log file.
