import os
import sys
import threading

from utils.logger import SpireLogger

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

spire_logger = SpireLogger()
log = spire_logger.get_logger()

# 2. Ora possiamo importare il resto
from core.orchestrator import SpireOrchestrator
from gui.dashboard import SpireDashboard


def create_stop_file():
    """Crea il file stop.txt nella root del progetto per fermare il bot all'avvio."""
    stop_path = os.path.join(project_root, "stop.txt")
    try:
        with open(stop_path, "w", encoding="utf-8") as f:
            f.write("STOP\n")
        log.info(f"File di stop creato: {stop_path}")
    except Exception as e:
        log.error(f"Errore nella creazione del file di stop: {e}")


def start_logic(orchestrator):
    """Esegue l'orchestratore in un thread separato"""
    try:
        orchestrator.run()
    except Exception as e:
        log.error(f"Errore nell'orchestratore: {e}")


if __name__ == "__main__":
    log.info("--- AVVIO SISTEMA SPIREMIND ---")
    create_stop_file()
    try:
        orchestrator = SpireOrchestrator()

        # Avviamo l'orchestratore in background
        logic_thread = threading.Thread(
            target=start_logic, args=(orchestrator,), daemon=True
        )
        logic_thread.start()

        # Avviamo la GUI nel thread principale
        app = SpireDashboard(orchestrator)

        log.info("Interfaccia Desktop avviata.")
        app.mainloop()

    except Exception as e:
        log.critical(f"Errore fatale all'avvio: {e}")
        sys.exit(1)
