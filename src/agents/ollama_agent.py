import re
from models.state import GameState
from loguru import logger
from utils.rag import GameRAG
from agents.heuristics import heuristic_action
from utils.prompt import build_combat_prompt
from utils.command_policy import normalize_and_validate_command


_OLLAMA_UNAVAILABLE_LOGGED = False
_OLLAMA_DISABLED = False
_OLLAMA_DISABLED_LOGGED = False


def _get_ollama_client():
    global _OLLAMA_UNAVAILABLE_LOGGED, _OLLAMA_DISABLED
    if _OLLAMA_DISABLED:
        return None
    try:
        import ollama

        return ollama
    except Exception as exc:
        if not _OLLAMA_UNAVAILABLE_LOGGED:
            logger.warning(f"Ollama not available; disabling LLM calls: {exc}")
            _OLLAMA_UNAVAILABLE_LOGGED = True
        return None


class OllamaAgent:
    def __init__(self, model="llama3"):
        self.model = model

    # --- Heuristic Layer ---
    # Heuristic helpers are now in src/agents/heuristics.py

    # Combat intent parsing moved to src/agents/heuristics.py

    # Lethal moved to src/agents/heuristics.py

    # Block moved to src/agents/heuristics.py

    # Potion moved to src/agents/heuristics.py

    # Heuristic action composed in src/agents/heuristics.py

    # --- Draft Heuristic (Tier List fallback) ---
    def _heuristic_draft(self, state: GameState) -> str | None:
        cmds = set(state.available_commands or [])
        if "choose" not in cmds:
            return None
        rewards = list(getattr(state, "reward_cards", []) or [])
        if not rewards:
            return None
        # Load tier list JSON
        try:
            import os, json

            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            root = os.path.dirname(here)
            tl_path = os.path.join(root, "tier_list.json")
            with open(tl_path, "r", encoding="utf-8") as f:
                tiers = json.load(f)
        except Exception:
            tiers = {}

        # Simple class detection from deck starters
        deck = [str(x) for x in (getattr(state, "deck", []) or [])]
        cls_key = "IRONCLAD"
        deck_lower = [d.lower() for d in deck]
        if any("neutralize" in d or "survivor" in d for d in deck_lower):
            cls_key = "SILENT"

        score_map = tiers.get(cls_key, {})
        best_idx = 0
        best_score = -1.0
        for i, rc in enumerate(rewards):
            name = getattr(rc, "name", "UNKNOWN")
            score = float(score_map.get(name, 0.0))
            if score > best_score:
                best_score = score
                best_idx = i

        return f"choose {best_idx}"

    def build_prompt(self, state: GameState) -> str:
        return build_combat_prompt(state)

    def sanitize_command(self, raw_cmd: str, state: GameState) -> str:
        """
        Sanitize command to match game expectations and prevent invalid actions.
        - Cards are 1-based; targets are 0-based.
        - Ensures 'play' only when allowed and with valid indexes/targets.
        - Adds default for 'wait' without argument.
        - Falls back to 'state' when command is not allowed.
        """
        normalized = normalize_and_validate_command(raw_cmd, state)
        if normalized is None:
            return "end" if getattr(state, "in_game", False) else "state"
        return normalized

    def think(self, state: GameState) -> str:
        # 1) Heuristic quick decisions (override LLM when obvious)
        if state and state.ready_for_command:
            h = heuristic_action(state)
            if h:
                return self.sanitize_command(h, state)

        # 2) RAG: if in shop/event with unknown relic/item, augment prompt
        rag = GameRAG()
        rag_notes = []
        try:
            # Append connection status to rag notes
            if rag.is_connected():
                rag_notes.append("DB: connected")
            else:
                rag_notes.append("DB: not connected")

            for name in state.shop_items or []:
                desc = rag.search_relic(str(name))
                if desc:
                    rag_notes.append(f"Relic '{name}': {desc}")
                else:
                    # If unknown and connected, auto-ingest with a minimal placeholder description
                    rag.ensure_relic(str(name), "(unknown relic; added by bot)")
            # Also ingest new card rewards not present in DB (lightweight wiki building)
            for rc in state.reward_cards or []:
                nm = getattr(rc, "name", None)
                if nm:
                    # Use simple summary if available; otherwise minimal placeholder
                    summary = f"Card {nm}: type={getattr(rc, 'type', 'UNKNOWN')} cost={getattr(rc, 'cost', 0)}"
                    rag.ensure_card(str(nm), summary)
        except Exception:
            pass

        # 3) Fallback to LLM
        prompt = self.build_prompt(state)
        if rag_notes:
            prompt = prompt + "\nRAG NOTES:\n" + "\n".join(rag_notes)
        try:
            client = _get_ollama_client()
            if not client:
                return "end"
            res = client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Slay the Spire expert bot. Output only valid game commands.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            raw_action = res["message"]["content"]

            # Qui avviene la magia: puliamo il comando prima di darlo al gioco
            final_action = self.sanitize_command(raw_action, state)

            # Logghiamo cosa ha pensato l'AI vs cosa eseguiamo davvero
            if final_action != raw_action.strip().lower():
                logger.info(f"Sanitizer: '{raw_action}' -> '{final_action}'")

            return final_action

        except Exception as e:
            global _OLLAMA_DISABLED, _OLLAMA_DISABLED_LOGGED
            msg = str(e).lower()
            if (
                "failed to connect" in msg
                or "connection refused" in msg
                or "connection error" in msg
            ):
                _OLLAMA_DISABLED = True
                if not _OLLAMA_DISABLED_LOGGED:
                    logger.warning(f"Ollama unreachable; disabling LLM calls: {e}")
                    _OLLAMA_DISABLED_LOGGED = True
            else:
                logger.error(f"Errore Ollama: {e}")
            return "end"
