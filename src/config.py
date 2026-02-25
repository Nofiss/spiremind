from utils.config_loader import get, get_int, get_float, get_bool


class BotConfig:
    # --- TIME SETTINGS ---

    # Heartbeat: ogni quanto dire "sono vivo" (frame di gioco)
    WAIT_COMMAND_FRAMES = get_int("WAIT_COMMAND_FRAMES", 60)

    # Risparmio CPU: sleep mentre l'AI pensa (secondi)
    AI_THINKING_INTERVAL = get_float("AI_THINKING_INTERVAL", 0.5)

    # Kill-switch: sleep se il bot è stoppato (secondi)
    KILL_SWITCH_INTERVAL = get_float("KILL_SWITCH_INTERVAL", 2.0)

    # --- HUMANIZATION ---
    # Ritardo artificiale per le azioni di menu (Start, Choose, Confirm)
    # 1.5 secondi è un buon compromesso per far vedere cosa succede
    MENU_ACTION_DELAY = get_float("MENU_ACTION_DELAY", 1.5)

    # --- RL SETTINGS ---
    USE_RL_AGENT = get_bool("USE_RL_AGENT", False)
    RL_MODEL_PATH = "data/rl_models/spire_ppo.zip"

    # --- REWARD SETTINGS (RL) ---
    REWARD_FIGHT_WIN_BASE = get_float("REWARD_FIGHT_WIN_BASE", 1.0)
    REWARD_FIGHT_HP_LOSS_SCALE = get_float("REWARD_FIGHT_HP_LOSS_SCALE", 1.0)
    REWARD_FIGHT_MIN = get_float("REWARD_FIGHT_MIN", -1.0)
    REWARD_FIGHT_MAX = get_float("REWARD_FIGHT_MAX", 1.0)
    REWARD_ACT1 = get_float("REWARD_ACT1", 10.0)
    REWARD_ACT2 = get_float("REWARD_ACT2", 20.0)
    REWARD_ACT3 = get_float("REWARD_ACT3", 40.0)
    REWARD_RUN_WIN = get_float("REWARD_RUN_WIN", 100.0)
    REWARD_RUN_LOSS = get_float("REWARD_RUN_LOSS", -100.0)

    # --- LORA SETTINGS ---
    USE_LORA_AGENT = get_bool("USE_LORA_AGENT", False)
    LORA_MODEL_PATH = get("LORA_MODEL_PATH", "spiremind_lora_model")
    LORA_MAX_NEW_TOKENS = get_int("LORA_MAX_NEW_TOKENS", 64)
    LORA_MAX_SEQ_LENGTH = get_int("LORA_MAX_SEQ_LENGTH", 2048)
