import customtkinter as ctk
import os
from loguru import logger

# Percorso del file di stop nella root del progetto
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP_FILE_PATH = os.path.join(PROJECT_ROOT, "stop.txt")


class SpireDashboard(ctk.CTk):
    def __init__(self, orchestrator):
        super().__init__()
        self.orchestrator = orchestrator

        # Configurazione Finestra
        self.title("SpireMind AI • Control Panel")
        self.geometry("900x1100")
        self.attributes("-topmost", True)
        ctk.set_appearance_mode("dark")

        # Theme palette
        self.COLORS = {
            "bg": "#0d1117",
            "surface": "#111827",
            "primary": "#5B8DEF",
            "accent": "#6EE7B7",
            "text": "#E5E7EB",
            "muted": "#9CA3AF",
            "chip_on": "#16A34A",
            "chip_off": "#374151",
            "chip_warn": "#F59E0B",
        }

        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # Header with accent bar
        self.header_frame = ctk.CTkFrame(self, fg_color=self.COLORS["surface"])
        self.header_frame.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)
        header = ctk.CTkLabel(
            self.header_frame, text="SpireMind AI", font=("Segoe UI", 24, "bold")
        )
        header.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="w")
        subtitle = ctk.CTkLabel(
            self.header_frame,
            text="Hybrid Heuristics • LLM • Pathing • Draft",
            font=("Segoe UI", 14),
        )
        subtitle.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
        accent_bar = ctk.CTkFrame(
            self.header_frame, height=4, fg_color=self.COLORS["primary"]
        )
        accent_bar.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="ew")

        # 1. CHARACTER
        self.char_label = ctk.CTkLabel(
            self, text="Character", font=("Segoe UI", 13, "bold")
        )
        self.char_label.grid(row=1, column=0, padx=20, pady=(8, 4), sticky="w")

        self.char_var = ctk.StringVar(value="ironclad")
        self.char_menu = ctk.CTkOptionMenu(
            self,
            values=["ironclad", "silent", "defect", "watcher", "hermit"],
            variable=self.char_var,
        )
        self.char_menu.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        # 2. CONTROLS
        self.button_frame = ctk.CTkFrame(self, fg_color=self.COLORS["surface"])
        self.button_frame.grid(row=2, column=0, padx=20, pady=12, sticky="nsew")
        # Layout a griglia per i pulsanti
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=1)
        self.button_frame.grid_columnconfigure(2, weight=1)
        self.button_frame.grid_columnconfigure(3, weight=1)
        self.button_frame.grid_columnconfigure(4, weight=1)
        self.button_frame.grid_rowconfigure(0, weight=1, minsize=44)
        self.button_frame.grid_rowconfigure(1, minsize=36)

        # Impostazioni tema/scaling per massima compatibilità
        ctk.set_default_color_theme("dark-blue")
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

        self.start_btn = ctk.CTkButton(
            self.button_frame,
            text="Start",
            command=self.start_bot,
            width=160,
            height=36,
        )
        self.start_btn.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.stop_btn = ctk.CTkButton(
            self.button_frame, text="Stop", command=self.stop_bot, width=160, height=36
        )
        self.stop_btn.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Fine-grained controls
        self.pause_btn = ctk.CTkButton(
            self.button_frame,
            text="Pause",
            command=self.toggle_pause,
            width=160,
            height=36,
        )
        self.pause_btn.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        self.resume_now_btn = ctk.CTkButton(
            self.button_frame,
            text="Resume",
            command=self.resume_now,
            width=180,
            height=36,
        )
        self.resume_now_btn.grid(row=0, column=3, padx=10, pady=10, sticky="ew")

        self.new_run_btn = ctk.CTkButton(
            self.button_frame,
            text="New Run",
            command=self.new_run,
            width=160,
            height=36,
        )
        self.new_run_btn.grid(row=0, column=4, padx=10, pady=10, sticky="ew")

        # Switch preferenza ripresa
        self.resume_switch = ctk.CTkSwitch(
            self.button_frame, text="Prefer Resume When Available"
        )
        self.resume_switch.select()  # di default ON
        self.resume_switch.grid(
            row=1, column=0, columnspan=2, padx=10, pady=10, sticky="w"
        )

        # Stato ripresa
        self.resume_status_label = ctk.CTkLabel(
            self.button_frame, text="Resume Status: ..."
        )
        self.resume_status_label.grid(
            row=1, column=3, columnspan=2, padx=10, pady=10, sticky="e"
        )

        # Status panel with chips
        self.status_frame = ctk.CTkFrame(self, fg_color=self.COLORS["surface"])
        self.status_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.av_cmds_label = ctk.CTkLabel(
            self.status_frame, text="Available commands: []"
        )
        self.av_cmds_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        # DB status label
        self.db_status_label = ctk.CTkLabel(self.status_frame, text="DB: unknown")
        self.db_status_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        # Preview panel (Enemies, Hand, Deck, Map)
        self.preview_frame = ctk.CTkFrame(self, fg_color=self.COLORS["surface"])
        self.preview_frame.grid(row=4, column=0, padx=20, pady=10, sticky="nsew")
        self.preview_frame.grid_columnconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(1, weight=1)
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_rowconfigure(1, weight=1)
        self.preview_frame.grid_rowconfigure(2, weight=1)

        self.enemies_frame = ctk.CTkScrollableFrame(self.preview_frame)
        self.enemies_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(
            self.enemies_frame, text="Enemies", font=("Segoe UI", 13, "bold")
        ).grid(row=0, column=0, padx=6, pady=(6, 4), sticky="w")

        self.hand_frame = ctk.CTkScrollableFrame(self.preview_frame)
        self.hand_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.hand_frame, text="Hand", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, padx=6, pady=(6, 4), sticky="w"
        )

        self.deck_frame = ctk.CTkScrollableFrame(self.preview_frame)
        self.deck_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.deck_frame, text="Deck", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, padx=6, pady=(6, 4), sticky="w"
        )

        self.map_frame = ctk.CTkScrollableFrame(self.preview_frame)
        self.map_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(
            self.map_frame, text="Map Choices", font=("Segoe UI", 13, "bold")
        ).grid(row=0, column=0, padx=6, pady=(6, 4), sticky="w")

        # Shop panel
        self.shop_frame = ctk.CTkScrollableFrame(self.preview_frame)
        self.shop_frame.grid(
            row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew"
        )
        ctk.CTkLabel(self.shop_frame, text="Shop", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, padx=6, pady=(6, 4), sticky="w"
        )

        # 3. CONSOLE LOGS
        self.log_textbox = ctk.CTkTextbox(self, width=760, height=220)
        self.log_textbox.grid(row=5, column=0, padx=20, pady=12, sticky="nsew")
        self.log_textbox.insert("0.0", "Welcome to SpireMind AI...\nReady to play.\n")

        # Aggiornamento periodico dello stato
        self.after(500, self.update_status)

    def start_bot(self):
        # Comunichiamo all'orchestratore il personaggio scelto
        selected_char = self.char_var.get()
        self.orchestrator.selected_character = selected_char

        # Imposta preferenza ripresa in orchestrator
        prefer = (
            bool(self.resume_switch.get()) if hasattr(self, "resume_switch") else True
        )
        if hasattr(self.orchestrator, "set_prefer_resume"):
            self.orchestrator.set_prefer_resume(prefer)

        # Se esiste il file stop.txt, lo rimuoviamo
        if os.path.exists(STOP_FILE_PATH):
            os.remove(STOP_FILE_PATH)

        # Abilita autostart e toglie pausa
        try:
            if hasattr(self.orchestrator, "set_autostart"):
                self.orchestrator.set_autostart(True)
            if hasattr(self.orchestrator, "set_paused"):
                self.orchestrator.set_paused(False)
        except Exception:
            pass

        # Log differenziato
        if (
            prefer
            and hasattr(self.orchestrator, "resume_available")
            and self.orchestrator.resume_available()
        ):
            self.add_log("Tentativo di ripresa della partita (continue)...")
        else:
            self.add_log(f"Bot avviato con: {selected_char.upper()}")

        self.start_btn.configure(state="disabled")

    def stop_bot(self):
        # Creiamo il file stop.txt per fermare il bot
        try:
            with open(STOP_FILE_PATH, "w", encoding="utf-8") as f:
                f.write("STOP\n")
            self.add_log("Bot fermato. (Kill-switch attivo)")
        except Exception as e:
            logger.error(f"Errore creazione stop file: {e}")
            self.add_log("Errore nel fermare il bot.")
        # Mette in pausa e disabilita autostart
        try:
            if hasattr(self.orchestrator, "set_paused"):
                self.orchestrator.set_paused(True)
            if hasattr(self.orchestrator, "set_autostart"):
                self.orchestrator.set_autostart(False)
        except Exception:
            pass
        self.start_btn.configure(state="normal")

    def update_status(self):
        # Disponibilità ripresa
        try:
            available = (
                self.orchestrator.resume_available()
                if hasattr(self.orchestrator, "resume_available")
                else False
            )
        except Exception:
            available = False
        text = "Resume available" if available else "Resume NOT available"
        color = "green" if available else "gray"
        try:
            self.resume_status_label.configure(text=text, text_color=color)
        except Exception:
            pass
        # Disabilita selezione personaggio se si preferisce ripresa e disponibile
        try:
            prefer = bool(self.resume_switch.get())
            if prefer and available:
                self.char_menu.configure(state="disabled")
            else:
                self.char_menu.configure(state="normal")
        except Exception:
            pass
        # Stato run/AI
        try:
            status = (
                self.orchestrator.get_status()
                if hasattr(self.orchestrator, "get_status")
                else {}
            )
            av = status.get("available_commands") or []
            self.av_cmds_label.configure(text=f"Available commands: {av}")
            # Aggiorna testo bottone pausa secondo stato corrente
            self.pause_btn.configure(text="Resume" if status.get("paused") else "Pause")

            # Status chips (create lazily)
            if not hasattr(self, "chips_frame"):
                self.chips_frame = ctk.CTkFrame(
                    self.status_frame, fg_color="transparent"
                )
                self.chips_frame.grid(row=0, column=1, padx=10, pady=5, sticky="e")
                self.chip_paused = ctk.CTkLabel(
                    self.chips_frame,
                    text="PAUSED",
                    fg_color=self.COLORS["chip_off"],
                    corner_radius=8,
                )
                self.chip_paused.grid(row=0, column=0, padx=6, pady=4)
                self.chip_autostart = ctk.CTkLabel(
                    self.chips_frame,
                    text="AUTOSTART",
                    fg_color=self.COLORS["chip_off"],
                    corner_radius=8,
                )
                self.chip_autostart.grid(row=0, column=1, padx=6, pady=4)
                self.chip_thinking = ctk.CTkLabel(
                    self.chips_frame,
                    text="THINKING",
                    fg_color=self.COLORS["chip_off"],
                    corner_radius=8,
                )
                self.chip_thinking.grid(row=0, column=2, padx=6, pady=4)

            self.chip_paused.configure(
                fg_color=self.COLORS["chip_on"]
                if status.get("paused")
                else self.COLORS["chip_off"]
            )
            self.chip_autostart.configure(
                fg_color=self.COLORS["chip_on"]
                if status.get("autostart")
                else self.COLORS["chip_off"]
            )
            self.chip_thinking.configure(
                fg_color=self.COLORS["chip_warn"]
                if status.get("is_thinking")
                else self.COLORS["chip_off"]
            )
            # Update DB connection status
            try:
                from utils.rag import GameRAG

                rag = GameRAG()
                self.db_status_label.configure(
                    text=f"DB: {'connected' if rag.is_connected() else 'not connected'}"
                )
            except Exception:
                self.db_status_label.configure(text="DB: unknown")
        except Exception:
            pass

        # Preview content
        try:
            self._update_preview()
        except Exception:
            pass
        # Pianifica prossimo aggiornamento
        self.after(500, self.update_status)

    def toggle_pause(self):
        try:
            paused = (
                bool(self.orchestrator.is_paused())
                if hasattr(self.orchestrator, "is_paused")
                else False
            )
            if hasattr(self.orchestrator, "set_paused"):
                self.orchestrator.set_paused(not paused)
            self.add_log(f"Pause: {'enabled' if not paused else 'disabled'}")
            self.pause_btn.configure(text="Resume" if paused else "Pause")
        except Exception as e:
            logger.error(f"Errore toggle pausa: {e}")

    def resume_now(self):
        try:
            if hasattr(self.orchestrator, "set_prefer_resume"):
                self.orchestrator.set_prefer_resume(True)
            if hasattr(self.orchestrator, "set_autostart"):
                self.orchestrator.set_autostart(True)
            if hasattr(self.orchestrator, "set_paused"):
                self.orchestrator.set_paused(False)
            if os.path.exists(STOP_FILE_PATH):
                os.remove(STOP_FILE_PATH)
            self.add_log("Forcing resume at next available state.")
        except Exception as e:
            logger.error(f"Errore resume_now: {e}")

    def new_run(self):
        try:
            if hasattr(self.orchestrator, "set_prefer_resume"):
                self.orchestrator.set_prefer_resume(False)
            if hasattr(self.orchestrator, "set_autostart"):
                self.orchestrator.set_autostart(True)
            if hasattr(self.orchestrator, "set_paused"):
                self.orchestrator.set_paused(False)
            if os.path.exists(STOP_FILE_PATH):
                os.remove(STOP_FILE_PATH)
            self.add_log(f"New run with: {self.char_var.get().upper()}")
        except Exception as e:
            logger.error(f"Errore new_run: {e}")

    def add_log(self, message):
        self.log_textbox.insert("end", f"> {message}\n")
        self.log_textbox.see("end")

    def _clear_children(self, frame):
        try:
            for w in frame.winfo_children()[1:]:  # keep section label
                w.destroy()
        except Exception:
            pass

    def _update_preview(self):
        state = getattr(self.orchestrator, "last_state", None)
        if not state:
            return

        # Enemies
        self._clear_children(self.enemies_frame)
        row = 1
        for i, m in enumerate(state.monsters or []):
            if getattr(m, "is_gone", False):
                continue
            label = ctk.CTkLabel(
                self.enemies_frame,
                text=f"{i}: {getattr(m, 'name', '?')}  HP={getattr(m, 'current_hp', 0)}  Intent={getattr(m, 'intent', '?')}",
            )
            label.grid(row=row, column=0, padx=6, pady=2, sticky="w")
            row += 1

        # Hand
        self._clear_children(self.hand_frame)
        row = 1
        for i, card in enumerate(state.hand or []):
            idx = i + 1
            label = ctk.CTkLabel(
                self.hand_frame,
                text=f"{idx}: {getattr(card, 'name', '?')}  ({getattr(card, 'cost', 0)}E)",
            )
            label.grid(row=row, column=0, padx=6, pady=2, sticky="w")
            row += 1

        # Deck
        self._clear_children(self.deck_frame)
        row = 1
        counts = {}
        for name in state.deck or []:
            counts[name] = counts.get(name, 0) + 1
        for name, cnt in counts.items():
            label = ctk.CTkLabel(self.deck_frame, text=f"{name} x{cnt}")
            label.grid(row=row, column=0, padx=6, pady=2, sticky="w")
            row += 1

        # Map choices
        self._clear_children(self.map_frame)
        row = 1
        hint = ctk.CTkLabel(
            self.map_frame,
            text="Click to choose a path",
            text_color=self.COLORS.get("muted", "gray"),
        )
        hint.grid(row=row, column=0, padx=6, pady=(2, 6), sticky="w")
        row += 1
        for i, nid in enumerate(state.map_choices or []):
            btn = ctk.CTkButton(
                self.map_frame,
                text=f"{i}: {str(nid)}",
                width=220,
                height=30,
                fg_color=self.COLORS.get("chip_off", "#374151"),
                hover_color=self.COLORS.get("primary", "#5B8DEF"),
                command=lambda idx=i: self._choose_map(idx),
            )
            btn.grid(row=row, column=0, padx=6, pady=4, sticky="w")
            row += 1

        # Shop items view with predicted scores
        self._clear_children(self.shop_frame)
        shop_row = 1
        try:
            from utils.rag import GameRAG

            rag = GameRAG()
            shop_choices = getattr(state, "shop_choices", []) or []
            gold = getattr(state, "gold", 0) or 0
            for it in shop_choices:
                name = str(it.get("name", "UNKNOWN"))
                price = it.get("price", None)
                cat = str(it.get("category", "UNKNOWN"))
                desc = rag.search_relic(name) or rag.search_card(name) or ""
                s = desc.lower()
                score = 0.0
                for kw, w in (
                    ("strength", 2.0),
                    ("poison", 2.0),
                    ("block", 1.0),
                    ("dexterity", 1.0),
                    ("draw", 1.0),
                    ("energy", 1.0),
                ):
                    if kw in s:
                        score += w
                if price:
                    score -= price / 200.0
                label = ctk.CTkLabel(
                    self.shop_frame,
                    text=f"{it.get('index', '?')}: {name} [{cat}] - {price if price is not None else 'n/a'}g | score~{score:.1f}",
                )
                label.grid(row=shop_row, column=0, padx=6, pady=2, sticky="w")
                shop_row += 1
        except Exception:
            pass

    def _choose_map(self, idx: int):
        try:
            # Route through orchestrator gating to send the command safely
            if hasattr(self.orchestrator, "_execute_menu_action"):
                self.orchestrator._execute_menu_action(f"choose {idx}", "GUI Map Click")
            else:
                if hasattr(self.orchestrator, "bridge"):
                    self.orchestrator.bridge.write(f"choose {idx}")
            self.add_log(f"Map choice sent: choose {idx}")
        except Exception as e:
            logger.error(f"Map choose failed: {e}")
            self.add_log("Failed to send map choice.")
