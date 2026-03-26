#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


DEFAULTS: Dict[str, str] = {
    "WHISPER_MODEL": "small",
    "WHISPER_DEVICE": "cuda",
    "WHISPER_COMPUTE_TYPE": "float16",
    "WHISPER_LANGUAGE": "en",
    "DOUBLE_TAP_WINDOW": "0.35",
    "SILENCE_THRESHOLD": "0.02",
    "SILENCE_SECONDS": "1.0",
    "MIN_RECORD_SECONDS": "0.8",
    "MAX_RECORD_SECONDS": "45.0",
    "TYPE_DELAY_MS": "1",
    "SAMPLE_RATE": "16000",
    "CHANNELS": "1",
    "BLOCK_MS": "50",
    "LOG_LEVEL": "INFO",
}


@dataclass
class RuntimeConfig:
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    whisper_language: str
    double_tap_window: float
    silence_threshold: float
    silence_seconds: float
    min_record_seconds: float
    max_record_seconds: float
    type_delay_ms: int
    sample_rate: int
    channels: int
    block_ms: int
    log_level: str


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
            continue
        key, raw = striped.split("=", 1)
        key = key.strip()
        val = raw.strip().strip('"').strip("'")
        values[key] = val
    return values


def config_dir() -> Path:
    return Path.home() / ".config" / "vibewhisper"


def state_dir() -> Path:
    return Path.home() / ".local" / "state" / "vibewhisper"


def load_raw_values(repo_env_path: Optional[Path] = None) -> Dict[str, str]:
    values = dict(DEFAULTS)

    user_cfg = config_dir() / "config.env"
    values.update(_parse_env_file(user_cfg))

    if repo_env_path:
        values.update(_parse_env_file(repo_env_path))
    else:
        maybe_repo_env = Path.cwd() / ".env.local"
        values.update(_parse_env_file(maybe_repo_env))

    for key in values.keys():
        if key in os.environ and os.environ[key] != "":
            values[key] = os.environ[key]

    return values


def build_runtime_config(values: Dict[str, str]) -> RuntimeConfig:
    return RuntimeConfig(
        whisper_model=values["WHISPER_MODEL"],
        whisper_device=values["WHISPER_DEVICE"],
        whisper_compute_type=values["WHISPER_COMPUTE_TYPE"],
        whisper_language=values["WHISPER_LANGUAGE"],
        double_tap_window=float(values["DOUBLE_TAP_WINDOW"]),
        silence_threshold=float(values["SILENCE_THRESHOLD"]),
        silence_seconds=float(values["SILENCE_SECONDS"]),
        min_record_seconds=float(values["MIN_RECORD_SECONDS"]),
        max_record_seconds=float(values["MAX_RECORD_SECONDS"]),
        type_delay_ms=int(values["TYPE_DELAY_MS"]),
        sample_rate=int(values["SAMPLE_RATE"]),
        channels=int(values["CHANNELS"]),
        block_ms=int(values["BLOCK_MS"]),
        log_level=values["LOG_LEVEL"],
    )


def apply_cli_overrides(values: Dict[str, str], args: argparse.Namespace) -> None:
    mapping = {
        "model": "WHISPER_MODEL",
        "device": "WHISPER_DEVICE",
        "compute_type": "WHISPER_COMPUTE_TYPE",
        "language": "WHISPER_LANGUAGE",
        "log_level": "LOG_LEVEL",
    }
    for arg_key, env_key in mapping.items():
        arg_val = getattr(args, arg_key, None)
        if arg_val:
            values[env_key] = str(arg_val)


def load_runtime_config(args: Optional[argparse.Namespace] = None, repo_env_path: Optional[Path] = None) -> RuntimeConfig:
    values = load_raw_values(repo_env_path=repo_env_path)
    if args is not None:
        apply_cli_overrides(values, args)
    return build_runtime_config(values)

