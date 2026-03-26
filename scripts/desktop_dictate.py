#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from vw_config import load_runtime_config, state_dir
from vw_engine import DictationEngine, HotkeyController
from vw_logging import get_logger, setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global Alt+Alt desktop dictation")
    parser.add_argument("--model")
    parser.add_argument("--device")
    parser.add_argument("--compute-type", dest="compute_type")
    parser.add_argument("--language")
    parser.add_argument("--log-level")
    parser.add_argument("--no-type", action="store_true", help="Print transcription only")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable global hotkey listener")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_runtime_config(args=args)

    log_file = setup_logging(state_dir() / "logs", cfg.log_level, console=True)
    log = get_logger("vibewhisper.desktop_dictate")
    log.info("desktop_dictate_start")

    engine = DictationEngine(
        cfg,
        on_state=lambda state, detail: log.info("state=%s detail=%s", state, detail),
        on_text=lambda text: log.info("transcribed_text=%s", text),
        notify=None,
        no_type=args.no_type,
    )

    hotkey = None
    if not args.no_hotkey:
        hotkey = HotkeyController(
            double_tap_window=cfg.double_tap_window,
            start_fn=engine.start_recording,
            stop_fn=engine.stop_recording,
            is_recording_fn=lambda: engine.is_recording,
            is_busy_fn=lambda: engine.is_busy,
            on_info=lambda msg: log.info("hotkey_info=%s", msg),
        )
        hotkey.start()

    print("[desktop-dictate] Ready. Double-tap Alt to start; Alt once to stop.")
    print(f"[desktop-dictate] Logging to: {log_file}")

    should_exit = False

    def _signal_handler(_signum, _frame):
        nonlocal should_exit
        should_exit = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while not should_exit:
            time.sleep(0.2)
    finally:
        if hotkey:
            hotkey.stop()

    print("[desktop-dictate] Exiting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
