#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def setup_logging(log_dir: Path, level_name: str, console: bool = True) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tray.log"

    root = logging.getLogger()
    root.setLevel(_level(level_name))

    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        root.addHandler(stream_handler)

    return log_file


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name or "vibewhisper")

