import sys
import os
import threading
import queue
from loguru import logger


class SpireBridge:
    def __init__(self, stop_file: str = "stop.txt"):
        # Risolve percorso assoluto dello stop file nella root del progetto
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isabs(stop_file):
            self.stop_file = os.path.join(project_root, stop_file)
        else:
            self.stop_file = stop_file

        # Coda thread-safe per i messaggi in arrivo dal gioco
        self.input_queue = queue.Queue()

        # Evento per fermare il thread pulitamente (opzionale ma buona pratica)
        self._stop_event = threading.Event()

        # Avviamo il thread "InputListener" che ascolta stdin in background
        # daemon=True significa che il thread muore se il programma principale muore
        self.listener_thread = threading.Thread(
            target=self._input_loop, daemon=True, name="InputListener"
        )
        self.listener_thread.start()

    def _input_loop(self):
        """
        Gira in background. Legge stdin (che è bloccante) e mette i dati in coda.
        Essendo in un thread a parte, il blocco qui non ferma l'Orchestratore.
        """
        logger.info("InputListener thread avviato.")
        while not self._stop_event.is_set():
            try:
                # Questa chiamata blocca QUESTO thread finché il gioco non scrive qualcosa
                line = sys.stdin.readline()

                if line:
                    # Abbiamo dati! Li mettiamo nella coda per l'orchestratore
                    self.input_queue.put(line.strip())
                else:
                    # Se readline ritorna stringa vuota, la pipe è chiusa (gioco chiuso)
                    self._stop_event.set()
                    logger.warning("PIPE_CLOSED: stdin closed")
                    break
            except Exception as e:
                logger.error(f"IO_ERROR: {e}")
                break

    def check_kill_switch(self) -> bool:
        return os.path.exists(self.stop_file)

    def write(self, command: str):
        """Scrive su stdout (thread-safe grazie al GIL di Python per I/O)"""
        if not command:
            return
        try:
            sys.stdout.write(f"{command}\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Errore scrittura stdout: {e}")

    def read_line_nowait(self) -> str | None:
        """
        NON BLOCCANTE.
        Controlla se il thread Listener ha messo qualcosa nella coda.
        Se c'è, lo ritorna subito. Se è vuota, ritorna None senza aspettare.
        """
        try:
            if not self.input_queue.empty():
                return self.input_queue.get_nowait()
        except queue.Empty:
            pass
        return None
