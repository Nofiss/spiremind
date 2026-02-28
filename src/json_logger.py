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

    last_line: str | None = None

    try:
        sys.stdout.write("ping\n")
        sys.stdout.flush()
    except Exception as exc:
        log.error(f"Errore invio ping iniziale: {exc}")
        return 1

    try:
        while True:
            raw_line = bridge.read_line_nowait()
            if raw_line is not None:
                log.debug(f"RX: {raw_line}")
                if raw_line != last_line:
                    try:
                        sys.stdout.write("ping\n")
                        sys.stdout.flush()
                    except Exception as exc:
                        log.error(f"Errore invio ping: {exc}")
                        return 1
                    last_line = raw_line
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
