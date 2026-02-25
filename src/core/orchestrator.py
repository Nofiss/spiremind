import threading
import queue
import json
import time
import re
from core.communication import SpireBridge
from models.state import GameState
from agents.ollama_agent import OllamaAgent
from agents.lora_agent import LoraAgent
from agents.rl_agent import RlAgent
from config import BotConfig
from loguru import logger
from core.session import SessionManager
from utils.training_logger import TrainingLogger
from utils.reward_tracker import RewardTracker
from utils.reward_logger import RewardLogger
from utils.rl_online_trainer import RlOnlineTrainer
from utils.rag import GameRAG
from utils.command_policy import normalize_and_validate_command


class SpireOrchestrator:
    def __init__(self):
        self.bridge = SpireBridge()
        if BotConfig.USE_LORA_AGENT:
            try:
                self.agent = LoraAgent(
                    model_path=str(BotConfig.LORA_MODEL_PATH or "spiremind_lora_model"),
                    max_new_tokens=BotConfig.LORA_MAX_NEW_TOKENS,
                    max_seq_length=BotConfig.LORA_MAX_SEQ_LENGTH,
                )
            except Exception as exc:
                logger.warning(f"LoraAgent unavailable, fallback to Ollama: {exc}")
                self.agent = OllamaAgent()
        else:
            self.agent = OllamaAgent()
        self.rl_agent = None
        self.rl_trainer = None
        self.reward_tracker = RewardTracker()
        self.reward_logger = RewardLogger()
        self._pending_rl_cmd = None
        self._pending_rl_action_id = None
        self._pending_rl_obs = None
        if BotConfig.USE_RL_AGENT:
            model_path = str(BotConfig.RL_MODEL_PATH or "data/rl_models/spire_ppo.zip")
            self.rl_agent = RlAgent(model_path)
            if self.rl_agent and self.rl_agent.model:
                self.rl_trainer = RlOnlineTrainer(self.rl_agent.model)
        self.command_queue = queue.Queue()
        self.is_thinking = False
        self.session = SessionManager()
        self.training_logger = TrainingLogger()
        self.rag = GameRAG()
        self.shop_exit_attempted = False  # prevent merchant open/close loops

        # WATCHDOG
        self.last_data_received_time = time.time()
        self.WATCHDOG_TIMEOUT = 2.0
        self.last_state_request_time = 0.0
        self.MIN_STATE_INTERVAL = 1.5

        # Backoff when no data
        self._no_data_cycles = 0
        self._sleep_backoff = 0.02
        self._min_sleep = 0.02
        self._max_sleep = 0.5

        # Menu de-dup
        self._last_menu_cmd = None
        self._last_menu_cmd_time = 0.0

        self.selected_character = "ironclad"

        # Preferenza: riprendere partita avviata se disponibile
        self.prefer_resume = True

        # Stato menu per la GUI
        self.last_available_commands = []
        self.last_ready_for_command = False

        # Stato run controllato da GUI
        self.autostart_enabled = False
        self.paused = True
        self.last_state = None
        # Tracking ultimo comando AI inviato e retry
        self.last_sent_ai_cmd = None
        self.play_retry_attempted = False

        # Metrics
        self._metrics = {
            "commands_sent": 0,
            "fallbacks": 0,
            "parse_errors": 0,
            "watchdog_pings": 0,
        }
        self._last_metrics_log = 0.0

    def _score_node(self, node_type: str, gs: GameState) -> int:
        t = (node_type or "UNKNOWN").upper()
        score = 0
        # Base preferences by HP/gold
        max_hp = max(1, int(getattr(gs, "max_hp", 0) or 1))
        hp = max(0, int(getattr(gs, "hp", 0) or 0))
        gold = max(0, int(getattr(gs, "gold", 0) or 0))
        hp_pct = (hp / max_hp) if max_hp > 0 else 0.0

        if hp_pct < 0.30 and t == "REST":
            score += 100
        if hp_pct > 0.80 and t == "ELITE":
            score += 50
        if gold >= 300 and t == "SHOP":
            score += 80

        # Mild bias: normal monsters slightly positive, unknown neutral
        if t == "MONSTER":
            score += 5
        return score

    def _choose_best_map_index(self, gs: GameState) -> int:
        # If no map choices, fallback to 0
        choices = list(getattr(gs, "map_choices", []) or [])
        if not choices:
            return 0
        nodes_by_id = {
            n.get("node_id", f"{n.get('x', 0)}:{n.get('y', 0)}"): n
            for n in (getattr(gs, "map_nodes", []) or [])
        }

        # Look ahead up to depth 4 (DAG per floor rows)
        def dfs(node_id: str, depth: int) -> int:
            node = nodes_by_id.get(node_id)
            if not node or depth == 0:
                return 0
            s = self._score_node(str(node.get("type", "UNKNOWN")), gs)
            best_child = 0
            for nxt in node.get("edges", []) or []:
                best_child = max(best_child, dfs(str(nxt), depth - 1))
            return s + best_child

        # Score each choice and pick highest cumulative
        scores = []
        for i, nid in enumerate(choices):
            try:
                total = dfs(str(nid), 4)
            except Exception:
                total = 0
            scores.append((i, total))

        scores.sort(key=lambda t: t[1], reverse=True)
        return scores[0][0] if scores else 0

    def _find_buy_command(self, state: GameState) -> str | None:
        """Return the appropriate shop purchase command based on available_commands."""
        cmds = set(state.available_commands or [])
        for cand in ("buy", "purchase", "take", "click", "key"):
            if cand in cmds:
                return cand
        return None

    def _score_shop_item(self, it: dict, gs: GameState) -> float:
        """Score a shop item using DB structured info and deck synergies."""
        try:
            name = str(it.get("name", "UNKNOWN"))
            cat = str(it.get("category", it.get("type", "UNKNOWN"))).upper()
            price = int(it.get("price", 0) or 0)
            gold = max(0, int(getattr(gs, "gold", 0) or 0))

            # Structured fetch
            info = None
            if cat == "CARD":
                info = self.rag.fetch_card_info(name)
            elif cat == "RELIC":
                info = self.rag.fetch_relic_info(name)

            deck = [d.lower() for d in (gs.deck or [])]
            has_strength = any(x in deck for x in ("demon form", "heavy blade"))
            has_poison = any(
                x in deck for x in ("catalyst", "noxious fumes", "poisoned stab")
            )

            score = 0.0
            # Use structured tags if available
            tags = (info or {}).get("tags") or ""
            tags_l = str(tags).lower()
            if tags_l:
                if "strength" in tags_l:
                    score += 3.0 if has_strength else 1.0
                if "poison" in tags_l:
                    score += 3.0 if has_poison else 1.0
                if "block" in tags_l or "dexterity" in tags_l:
                    score += 2.0
                if "draw" in tags_l:
                    score += 2.0
                if "energy" in tags_l:
                    score += 2.0

            # Fallback to description keywords from RAG
            if score == 0.0:
                desc = self.rag.search_relic(name) or self.rag.search_card(name) or ""
                s = desc.lower()
                if "strength" in s:
                    score += 3.0 if has_strength else 1.0
                if "dexterity" in s:
                    score += 1.0
                if "poison" in s:
                    score += 3.0 if has_poison else 1.0
                if "block" in s:
                    score += 2.0
                if "draw" in s or "card draw" in s:
                    score += 2.0
                if "energy" in s:
                    score += 2.0

            # Budget-aware penalty
            if price and price > gold:
                score -= 10.0
            else:
                score -= price / 200.0

            return score
        except Exception:
            return 0.0

    def _choose_best_shop_index(self, gs: GameState) -> int | None:
        """Choose best shop item index from shop_choices or fallback to shop_items."""
        items = list(getattr(gs, "shop_choices", []) or [])
        if not items:
            raw_items = list(getattr(gs, "shop_items", []) or [])
            # build simple items with index
            items = [
                {
                    "index": i,
                    "name": (it.get("name") if isinstance(it, dict) else str(it)),
                    "price": (it.get("price", 0) if isinstance(it, dict) else 0),
                }
                for i, it in enumerate(raw_items)
            ]
        if not items:
            return None

        gold = max(0, int(getattr(gs, "gold", 0) or 0))
        scores = []
        for it in items:
            sc = self._score_shop_item(it, gs)
            scores.append((int(it.get("index", 0)), sc, int(it.get("price", 0) or 0)))

        scores.sort(key=lambda t: t[1], reverse=True)
        if not scores:
            return None
        best_idx, best_sc, best_price = scores[0]
        if best_sc >= 3.0 and best_price <= gold and gold >= max(50, best_price):
            return best_idx
        return None

    def ai_thread_task(self, state: GameState):
        """Eseguito in background"""
        if self.paused:
            logger.debug("AI Thread skipped: paused")
            return
        try:
            self.is_thinking = True
            logger.debug("AI Thread: Inizio analisi...")
            action = None
            if self.rl_agent:
                action, action_id, obs = self.rl_agent.think(state)
                if action:
                    self._pending_rl_cmd = action
                    self._pending_rl_action_id = action_id
                    self._pending_rl_obs = obs
                else:
                    self._pending_rl_cmd = None
                    self._pending_rl_action_id = None
                    self._pending_rl_obs = None
            if not action:
                action = self.agent.think(state)
            self.command_queue.put(action)
        except Exception as e:
            logger.error(f"Errore thread AI: {e}")
            self.command_queue.put(None)
        finally:
            self.is_thinking = False

    def set_prefer_resume(self, prefer: bool):
        """Imposta la preferenza per riprendere una partita esistente."""
        self.prefer_resume = bool(prefer)

    def resume_available(self) -> bool:
        """Indica se 'continue' è disponibile nel menu corrente."""
        try:
            return self.last_ready_for_command and (
                "continue" in self.last_available_commands
            )
        except Exception:
            return False

    def set_autostart(self, enabled: bool):
        self.autostart_enabled = bool(enabled)
        logger.info(f"Autostart set to: {self.autostart_enabled}")

    def set_paused(self, paused: bool):
        self.paused = bool(paused)
        logger.info(f"Paused set to: {self.paused}")

    def is_paused(self) -> bool:
        return self.paused

    def get_status(self) -> dict:
        return {
            "paused": self.paused,
            "autostart": self.autostart_enabled,
            "is_thinking": self.is_thinking,
            "ready": self.last_ready_for_command,
            "available_commands": list(self.last_available_commands),
            "in_game": bool(self.last_state.in_game) if self.last_state else False,
        }

    def _execute_menu_action(self, command: str, reason: str = ""):
        if not self.autostart_enabled:
            logger.debug(
                f"MENU_SKIP: autostart disabled -> skip '{command}' ({reason})"
            )
            return
        if self.paused:
            logger.debug(f"MENU_SKIP: paused -> skip '{command}' ({reason})")
            return
        if not self.last_state:
            logger.debug("MENU_SKIP: missing state")
            return
        normalized = normalize_and_validate_command(
            command, self.last_state, default_class=self.selected_character
        )
        if not normalized:
            logger.debug(f"MENU_SKIP: invalid '{command}' ({reason})")
            return
        now = time.time()
        if self._last_menu_cmd == normalized and (now - self._last_menu_cmd_time) < 1.0:
            logger.debug(f"MENU_DUP: duplicate '{normalized}' ({reason})")
            return
        logger.info(f"CMD_SENT: {normalized} ({reason})")
        time.sleep(BotConfig.MENU_ACTION_DELAY)
        self.bridge.write(normalized)
        self.last_data_received_time = time.time()
        self._last_menu_cmd = normalized
        self._last_menu_cmd_time = now
        self._metrics["commands_sent"] += 1

    def _validate_and_send(self, cmd: str, state: GameState):
        # Gating
        if self.paused:
            logger.debug(f"AI command gating: paused -> skip '{cmd}'")
            return
        if not cmd:
            return
        normalized = normalize_and_validate_command(
            cmd, state, default_class=self.selected_character
        )
        if not normalized:
            logger.debug(
                f"CMD_INVALID: '{cmd}'. Disponibili: {state.available_commands}"
            )
            self._metrics["fallbacks"] += 1
            if cmd == self._pending_rl_cmd:
                self._pending_rl_cmd = None
                self._pending_rl_action_id = None
                self._pending_rl_obs = None
            return

        if (
            cmd == self._pending_rl_cmd
            and self.rl_trainer
            and self._pending_rl_obs is not None
            and self._pending_rl_action_id is not None
        ):
            self.rl_trainer.record(self._pending_rl_obs, self._pending_rl_action_id)
            self._pending_rl_cmd = None
            self._pending_rl_action_id = None
            self._pending_rl_obs = None

        # Invio sicuro
        logger.info(f"CMD_SENT: {normalized}")
        self.bridge.write(normalized)
        self._metrics["commands_sent"] += 1
        # Track command/potion/play
        try:
            self.session.record_command(normalized)
            parts = normalized.split()
            if parts and parts[0].lower() == "play":
                try:
                    idx1 = int(parts[1])
                    if 1 <= idx1 <= len(state.hand):
                        self.session.record_play(
                            getattr(state.hand[idx1 - 1], "name", "UNKNOWN")
                        )
                except Exception:
                    pass
            if parts and parts[0].lower() in ("use_potion", "potion", "use", "drink"):
                self.session.record_potion_use()
        except Exception:
            pass
        self.last_sent_ai_cmd = normalized
        self.play_retry_attempted = False
        self.last_data_received_time = time.time()

    def _attempt_play_correction(self, state: GameState, last_cmd: str):
        """Corregge un comando 'play' non valido scegliendo target alternativo e mantenendo card index 1-based."""
        try:
            parts = (last_cmd or "").split()
            if not parts or parts[0].lower() != "play":
                return None
            if not state:
                return None
            if len(parts) < 2:
                return None
            try:
                idx1 = int(parts[1])
            except Exception:
                return None
            if idx1 < 1 or idx1 > len(state.hand):
                return None
            card = state.hand[idx1 - 1]

            alive_targets = [
                i
                for i, m in enumerate(state.monsters)
                if not getattr(m, "is_gone", False) and getattr(m, "current_hp", 0) > 0
            ]
            needs_target = bool(getattr(card, "has_target", False))
            if not needs_target:
                return f"play {idx1}"

            prev_t = None
            if len(parts) >= 3:
                try:
                    prev_t = int(parts[2])
                except Exception:
                    prev_t = None

            for t in alive_targets:
                if prev_t is None or t != prev_t:
                    return f"play {idx1} {t}"

            return f"play {idx1}"
        except Exception:
            return None

    def run(self):

        logger.info("Orchestrator Asincrono avviato.")
        self.bridge.write("state")
        self.last_data_received_time = time.time()
        self.last_state_request_time = self.last_data_received_time

        while True:
            # 1. KILL-SWITCH
            if self.bridge.check_kill_switch():
                time.sleep(BotConfig.KILL_SWITCH_INTERVAL)
                continue

            # 2. ESECUZIONE COMANDI AI (Priorità Alta)
            # Ora questo codice verrà eseguito perché read_line_nowait non blocca!
            if not self.command_queue.empty():
                cmd = self.command_queue.get()
                if self.last_state and cmd:
                    self._validate_and_send(cmd, self.last_state)

            # 3. LETTURA DATI (NON BLOCCANTE)
            # Usiamo il nuovo metodo che controlla la coda interna del bridge
            raw_line = self.bridge.read_line_nowait()

            # --- LOGICA WATCHDOG ---
            if not raw_line:
                time_since_last_data = time.time() - self.last_data_received_time
                if (
                    time_since_last_data > self.WATCHDOG_TIMEOUT
                    and not self.is_thinking
                ):
                    now = time.time()
                    if now - self.last_state_request_time >= self.MIN_STATE_INTERVAL:
                        logger.debug(
                            f"WATCHDOG_PING: silence={time_since_last_data:.1f}s -> state"
                        )
                        self.bridge.write("state")
                        self.last_data_received_time = now
                        self.last_state_request_time = now
                        self._metrics["watchdog_pings"] += 1

                self._no_data_cycles += 1
                self._sleep_backoff = min(
                    self._max_sleep,
                    self._min_sleep * (2 ** (self._no_data_cycles / 10)),
                )
                if self._sleep_backoff >= 0.2:
                    logger.debug(
                        f"BACKOFF_SLEEP: cycles={self._no_data_cycles}, sleep={self._sleep_backoff:.2f}s"
                    )
                time.sleep(self._sleep_backoff)
                continue

            # Dati ricevuti!
            self.last_data_received_time = time.time()
            self._no_data_cycles = 0
            self._sleep_backoff = self._min_sleep

            if raw_line.startswith("{"):
                try:
                    data = json.loads(raw_line)

                    if "error" in data:
                        err = data.get("error", "")
                        logger.warning(f"Errore gioco: {err}")
                        # Se l'errore include l'elenco dei comandi possibili, aggiornalo per migliorare il gating
                        try:
                            if isinstance(err, str) and "Possible commands:" in err:
                                start = err.find("[")
                                end = err.find("]", start)
                                if start != -1 and end != -1:
                                    cmds_str = err[start + 1 : end]
                                    cmds = [
                                        c.strip()
                                        for c in cmds_str.split(",")
                                        if c.strip()
                                    ]
                                    self.last_available_commands = cmds
                        except Exception as e2:
                            logger.debug(f"Parse possibili comandi fallito: {e2}")
                        # Correzione mirata per target non valido su 'play'
                        try:
                            if (
                                isinstance(err, str)
                                and "Selected card cannot be played with the selected target"
                                in err
                            ):
                                if (
                                    self.last_sent_ai_cmd
                                    and not self.play_retry_attempted
                                ):
                                    if self.last_state:
                                        corrected = self._attempt_play_correction(
                                            self.last_state, self.last_sent_ai_cmd
                                        )
                                        if corrected:
                                            self.play_retry_attempted = True
                                            self._validate_and_send(
                                                corrected, self.last_state
                                            )
                        except Exception as e3:
                            logger.debug(f"Correzione play fallita: {e3}")
                        continue

                    prev_state = self.last_state
                    state = GameState.parse(data)

                    # metrics snapshot after successful parse
                    now = time.time()
                    if now - self._last_metrics_log >= 300:
                        self._last_metrics_log = now
                        logger.info(
                            "METRICS: sent={sent} fallback={fb} parse_errors={pe} watchdog={wd}".format(
                                sent=self._metrics["commands_sent"],
                                fb=self._metrics["fallbacks"],
                                pe=self._metrics["parse_errors"],
                                wd=self._metrics["watchdog_pings"],
                            )
                        )

                    # Session updates
                    try:
                        # Turn rollover (simple heuristic: if turn increased)
                        if prev_state and state.turn > getattr(prev_state, "turn", 0):
                            self.session.start_new_turn()
                        # Room type
                        self.session.update_room_type(state.room_type)
                        # Monsters snapshot
                        self.session.observe_monsters(
                            [m.name for m in state.monsters if not m.is_gone]
                        )
                        # Elite defeat tracking when combat ends
                        self.session.finalize_combat_if_ended(
                            bool(prev_state and prev_state.in_game), bool(state.in_game)
                        )
                    except Exception:
                        pass

                    # Log training tuple: previous state -> last action -> parse result
                    try:
                        if self.last_sent_ai_cmd:
                            self.training_logger.log(
                                state=(prev_state.model_dump() if prev_state else {}),
                                action=self.last_sent_ai_cmd,
                                result=data,
                            )
                    except Exception:
                        pass

                    # Reward tracking + RL online update
                    try:
                        event = self.reward_tracker.update(prev_state, state)
                        if event and self.rl_trainer:
                            self.rl_trainer.apply_reward(
                                reward=event.reward,
                                done=event.done,
                                reason=event.reason,
                            )
                        if event:
                            self.reward_logger.log(
                                {
                                    "reward": event.reward,
                                    "done": event.done,
                                    "reason": event.reason,
                                    "act": int(getattr(state, "act", 0) or 0),
                                    "floor": int(getattr(state, "floor", 0) or 0),
                                    "screen_type": str(
                                        getattr(state, "screen_type", "UNKNOWN")
                                    ),
                                    "room_phase": str(
                                        getattr(state, "room_phase", "UNKNOWN")
                                    ),
                                    "hp": int(getattr(state, "hp", 0) or 0),
                                    "max_hp": int(getattr(state, "max_hp", 0) or 0),
                                    "victory": getattr(state, "victory", None),
                                }
                            )
                    except Exception as e:
                        logger.debug(f"Reward tracking error: {e}")

                    # Detect newly added card(s) to the deck and ingest into DB
                    try:
                        prev_deck = (
                            list(getattr(prev_state, "deck", []) or [])
                            if prev_state
                            else []
                        )
                        curr_deck = list(getattr(state, "deck", []) or [])
                        prev_counts = {}
                        for n in prev_deck:
                            prev_counts[n] = prev_counts.get(n, 0) + 1
                        curr_counts = {}
                        for n in curr_deck:
                            curr_counts[n] = curr_counts.get(n, 0) + 1
                        for name, cnt in curr_counts.items():
                            prev_cnt = prev_counts.get(name, 0)
                            if cnt > prev_cnt:
                                # New copies added; ingest once per new copy
                                added = cnt - prev_cnt
                                for _ in range(added):
                                    desc = f"Auto-ingested: {name} (added to deck)"
                                    ok = self.rag.ensure_card(name, desc)
                                    if ok:
                                        logger.info(f"DB ingest card OK: {name}")
                                    else:
                                        logger.debug(
                                            f"DB ingest card skipped/failed: {name}"
                                        )
                    except Exception as e:
                        logger.debug(f"Deck ingest error: {e}")

                    self.last_state = state

                    # Aggiorna lo stato menu per la GUI
                    prev_commands = list(self.last_available_commands)
                    self.last_available_commands = state.available_commands
                    self.last_ready_for_command = state.ready_for_command
                    if prev_commands != list(self.last_available_commands):
                        self._last_menu_cmd = None
                        self._last_menu_cmd_time = 0.0

                    if state.ready_for_command and not self.is_thinking:
                        # Reset shop flag when room changes
                        try:
                            prev_room = (
                                getattr(prev_state, "room_type", "")
                                if prev_state
                                else ""
                            )
                            if (
                                prev_room
                                and prev_room != state.room_type
                                and self.shop_exit_attempted
                            ):
                                self.shop_exit_attempted = False
                        except Exception:
                            pass
                        # --- MENU ---
                        # Merchant handling: exit cleanly when not buying
                        try:
                            room = (state.room_type or "").upper()
                            screen = (state.screen_type or "").upper()
                            in_shop = (
                                ("SHOP" in room)
                                or ("MERCHANT" in room)
                                or ("SHOP" in screen)
                                or ("MERCHANT" in screen)
                            )
                            if in_shop:
                                if (
                                    "leave" in state.available_commands
                                    and not self.shop_exit_attempted
                                ):
                                    self._execute_menu_action("leave", "Shop Exit")
                                    self.shop_exit_attempted = True
                                    continue
                                if (
                                    "confirm" in state.available_commands
                                    and self.shop_exit_attempted
                                ):
                                    self._execute_menu_action(
                                        "confirm", "Shop Exit Confirm"
                                    )
                                    continue
                        except Exception:
                            pass
                        if (
                            "continue" in state.available_commands
                            and self.prefer_resume
                        ):
                            self._execute_menu_action("continue", "Resume Saved Run")
                        elif "start" in state.available_commands:
                            self._execute_menu_action(
                                f"start {self.selected_character}", "User Selected Char"
                            )
                        elif "choose" in state.available_commands:
                            # Strategic pathing on map choices
                            try:
                                idx = self._choose_best_map_index(self.last_state)
                                self._execute_menu_action(
                                    f"choose {idx}", "Strategic Map Pathing"
                                )
                            except Exception as e:
                                logger.debug(f"Map choose fallback: {e}")
                                self._execute_menu_action("choose 0", "Reward")
                        elif "proceed" in state.available_commands:
                            self._execute_menu_action("proceed", "Next")
                        elif "confirm" in state.available_commands:
                            self._execute_menu_action("confirm", "Confirm")
                        elif "leave" in state.available_commands:
                            self._execute_menu_action("leave", "Leave")

                        # --- COMBATTIMENTO ---
                        elif state.in_game and not self.paused:
                            threading.Thread(
                                target=self.ai_thread_task, args=(state,)
                            ).start()

                except Exception as e:
                    logger.error(f"PARSE_ERROR: {e}")
                    self._metrics["parse_errors"] += 1
