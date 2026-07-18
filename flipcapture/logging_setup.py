from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent.parent


def setup_logging() -> Path:
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"flipcapture_{datetime.now():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )
    logging.info("startup log: %s", path)

    def exception_hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        logging.critical("uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = exception_hook
    return path


def log_event(event: str, **details: Any) -> None:
    payload = {"event": event, "time": datetime.now().isoformat(timespec="seconds"), **details}
    logging.info("EVENT %s", json.dumps(payload, ensure_ascii=False, default=str))

