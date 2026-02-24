# SpireMind

SpireMind is a hybrid combat/strategy bot for Slay the Spire that blends fast heuristics with LLM reasoning, strategic pathing, deck‑aware drafting, and lightweight memory. It talks to the game via JSON over stdin/stdout and never blocks the main loop.

**Why It’s Different**
- Heuristics first: lethal and perfect blocks happen instantly (CPU math > LLM tokens)
- Strategic map pathing: looks 4 floors ahead on the DAG and picks the safest/most rewarding path
- Deck building with context: the agent considers your current deck and reward options, not just the first card
- RAG hooks + training logs: prepared for fine‑tuning and knowledge lookups (relics, events)

**How It Works**
- Communication: a background listener thread reads game JSON; commands are written to stdout only
- State parsing: defensive Pydantic models flatten nested JSON (hand, monsters, map, deck, shop, relics)
- Orchestrator: menu actions and combat decisions flow through a single async loop with a watchdog
- Agent: builds a compact prompt; runs heuristic layer first; falls back to Llama3 via Ollama when needed

**Key Features**
- Lethal Check: if total attack damage in hand ≥ target effective HP (hp+block), play the highest damage card immediately
- Perfect Block: simplified knapsack chooses a block combo to cover incoming damage (intent parser supports `8x2` etc.)
- Potion Use: auto‑use at low HP or on turn 1 vs elites
- Strategic Pathing: depth‑4 DFS over map edges with context weights (HP %, gold) to pick `choose <idx>`
- Draft Logic: tier list fallback (`tier_list.json`) and prompt injection of deck + reward options for synergy decisions
- Memory: per‑turn cards/commands, potions used, elites defeated; tracked in `SessionManager`
- RAG Notes: shop item lookups appended to the prompt when available (swap stub for real vector DB)
- Training Logs: append NDJSON entries of (state → action → result) for future LoRA/RL

**Project Structure**
```text
src/
  core/
    communication.py   # stdin listener, stdout writer
    orchestrator.py    # main async loop, menu/combat flow, map pathing
    session.py         # per‑turn memory (cards, commands, elites, potions)
  agents/
    ollama_agent.py    # heuristics + LLM (Ollama llama3) + RAG notes
  models/
    state.py           # robust GameState/Card/Monster/MapNode parsing
  gui/
    dashboard.py       # status GUI (CustomTkinter)
  utils/
    logger.py          # Loguru config
    rag.py             # relic RAG stub (json cache)
    training_logger.py # NDJSON training log writer
tier_list.json         # per‑character card scores for draft fallback
```

**Setup**
```bash
python -m venv .venv
. .venv/Scripts/activate  # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e .
ollama serve && ollama pull llama3
```

Optional extras:
```bash
# LoRA/LLM stack (Unsloth + torch/transformers)
pip install -e ".[llm]"

# RL stack (Gymnasium + Stable-Baselines3)
pip install -e ".[rl]"

# Both
pip install -e ".[llm,rl]"
```

**Run**
```bash
python src/main.py
```

**Design Highlights**
- Validation & Safety: all actions gated by `available_commands`; play/target indices checked; auto‑retry on invalid target
- Watchdog: resends `state` when the stream is quiet; prevents stalls
- Prompting: includes enemies, hand, map choices, deck, reward options; asks for `Thought:` then `Action:` (sanitizer extracts the command)
- Logging: diagnostics to `logs/spire_mind.log`; training data to `logs/training_data.ndjson`

**Heuristics (Combat)**
- `lethal`: compute damage from playable ATTACKs; if ≥ target hp+block, play next best attack
- `block`: DP over energy budget using SKILL block values; prefer covering incoming with minimal overshoot
- `potions`: low HP or elite turn 1 triggers suitable potion use if a command exists

**Strategic Pathing (Map)**
- Scores nodes by context:
  - HP < 30% + REST = +100
  - HP > 80% + ELITE = +50
  - Gold ≥ 300 + SHOP = +80
  - MONSTER = +5
- DFS depth 4 on DAG edges; picks `choose <idx>` with max cumulative score

**Deck Building & Draft**
- Prompt injects deck summary and reward card names
- Fallback to `tier_list.json` when the LLM is uncertain; picks the highest score for the detected class
- Next up: shop/event heuristics to prefer “Remove a card” and target base Strikes

**RAG & Training**
- RAG stub: `src/utils/rag.py` looks up relics from `relics_cache.json`; append “RAG NOTES” to prompt
- Training logger: `src/utils/training_logger.py` writes NDJSON tuples for future LoRA/RL pipelines
- LLM dataset: `python scripts/prepare_llm_dataset.py` converts NDJSON to chat JSONL under `data/llm/`

**Quality Tooling**
```bash
ruff check src && black --check src && mypy src
pytest -q
```

**Testing**
- Tests live in `tests/` (heuristics, prompt). Run with `pytest -q`.

**Reinforcement Learning (Mock Training)**
- Install extra deps: `pip install gymnasium stable-baselines3`
- Train on mock env: `python scripts/train_rl.py`
- Enable RL agent: set `USE_RL_AGENT=1` in `configs/.env`
- Model path defaults to `data/rl_models/spire_ppo.zip`

**LLM Fine-Tuning (LoRA/QLoRA)**
- Generate dataset: `PYTHONPATH=src python scripts/prepare_llm_dataset.py`
- Output JSONL: `data/llm/train.jsonl` and `data/llm/val.jsonl`
- Lenient mode (keeps simple commands even when validation falls back):
  `PYTHONPATH=src python scripts/prepare_llm_dataset.py --lenient`
- Training guide: `docs/LLM_TRAINING.md`
- Use LoRA agent: set `USE_LORA_AGENT=1` and `LORA_MODEL_PATH=spiremind_lora_model` in `configs/.env`
- Unsloth scripts: `scripts/llm/train_spire.py`, `scripts/llm/test_inference.py`, `scripts/llm/test_gpu.py`

**Contributing**
- Keep stdout clean (only game commands); use Loguru for diagnostics
- Follow absolute imports under `src/*` and defensive parsing conventions in `models/state.py`
- Prefer small, focused changes with clear commit messages

**Roadmap**
- Replace relic RAG stub with SQL Server 2025 vector store
- Expand `tier_list.json` with up‑to‑date scores (SpireLogs) per ascension
- Persist session memory to disk for run continuity
- Add tests for map scoring, draft selection, and heuristic edge cases

SpireMind aims to feel smart, fast, and intentional—no random walks, no wasted turns. Plug in stronger knowledge and training, and it scales with you.
