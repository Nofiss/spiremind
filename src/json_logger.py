import os
import sys
import time

from core.communication import SpireBridge
from utils.logger import SpireLogger


def main() -> int:
    spire_logger = SpireLogger()
    log = spire_logger.get_logger()

    log.info("--- AVVIO JSON LOGGER ---")

    bridge = SpireBridge()

    try:
        while True:
            raw_line = bridge.read_line_nowait()
            if raw_line is not None:
                sys.stdout.write(f"{raw_line}\n")
                sys.stdout.flush()
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        log.info("JSON logger interrotto da utente.")
        return 0
    except Exception as exc:
        log.error(f"Errore nel JSON logger: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
