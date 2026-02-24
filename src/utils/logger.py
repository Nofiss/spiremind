import os
import sys
from loguru import logger

class SpireLogger:
    def __init__(self, log_name: str = "spire_mind.log"):
        # 1. Troviamo la root del progetto in modo robusto
        # __file__ è src/utils/logger.py
        # Livello 1: src/utils/
        # Livello 2: src/
        # Livello 3: root/
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))

        # 2. Definiamo la cartella logs nella root
        log_dir = os.path.join(project_root, "logs")
        self.log_path = os.path.join(log_dir, log_name)

        # Assicuriamoci che la cartella esista
        os.makedirs(log_dir, exist_ok=True)

        # 3. Configurazione Loguru
        self._configure()

    def _configure(self):
        # Rimuoviamo il logger standard per evitare che scriva su stdout (fondamentale!)
        logger.remove()

        # Aggiungiamo il sink per il file
        logger.add(
            self.log_path,
            rotation="10 MB",
            retention="5 days",
            level="DEBUG",
            # Formato pulito per debugging senior
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {thread.name} | {module}:{function}:{line} - {message}",
            encoding="utf-8",
            enqueue=True, # Thread-safe
            compression="zip" # Comprime i vecchi log per risparmiare spazio
        )

        # Logging iniziale per conferma nel file
        logger.info(f"Logger inizializzato. Root progetto rilevata: {os.path.dirname(os.path.dirname(self.log_path))}")

    def get_logger(self):
        return logger
