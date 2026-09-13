from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from paths import ROOT

LOG_DIR = ROOT / "logs"
_initialized = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _initialized
    logger = logging.getLogger("letterfit")
    if _initialized:
        return logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = TimedRotatingFileHandler(LOG_DIR / "app.log", when="midnight", backupCount=7, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    logger.setLevel(level)
    _initialized = True
    return logger


def log_path():
    return LOG_DIR / "app.log"
