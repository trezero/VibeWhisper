#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from vw_config import config_dir, load_runtime_config, state_dir
from vw_engine import DictationEngine, HotkeyController
from vw_logging import get_logger, setup_logging

GLib = None
Gtk = None
AppIndicator3 = None


ICON_BY_STATE = {
    "Idle": "audio-input-microphone-symbolic",
    "Listening": "media-record-symbolic",
    "Processing": "system-run-symbolic",
    "Success": "emblem-ok-symbolic",
    "Error": "dialog-error-symbolic",
    "Disabled": "process-stop-symbolic",
}


class SingleInstance:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fd: Optional[int] = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        os.ftruncate(self.fd, 0)
        os.write(self.fd, str(os.getpid()).encode("utf-8"))
        return True

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None


class TrayApp:
    def __init__(self, args: argparse.Namespace):
        global GLib, Gtk, AppIndicator3
        GLib, Gtk, AppIndicator3 = load_gtk()

        self.cfg = load_runtime_config(args=args)
        self.log_file = setup_logging(state_dir() / "logs", self.cfg.log_level, console=False)
        self.log = get_logger("vibewhisper.tray")

        self.instance = SingleInstance(state_dir() / "tray.lock")
        if not self.instance.acquire():
            raise RuntimeError("VibeWhisper tray is already running.")

        self.state = "Idle"
        self.detail = "Ready"

        self.engine = DictationEngine(
            self.cfg,
            on_state=self.on_engine_state,
            on_text=self.on_engine_text,
            notify=self.notify,
            no_type=False,
        )

        self.hotkey = HotkeyController(
            double_tap_window=self.cfg.double_tap_window,
            start_fn=self.engine.start_recording,
            stop_fn=self.engine.stop_recording,
            is_recording_fn=lambda: self.engine.is_recording,
            is_busy_fn=lambda: self.engine.is_busy,
            on_info=self.notify,
        )

        if not args.no_hotkey:
            self.hotkey.start()

        self.indicator = AppIndicator3.Indicator.new(
            "vibewhisper-tray",
            ICON_BY_STATE["Idle"],
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("VibeWhisper")

        self.menu = Gtk.Menu()
        self.start_item = Gtk.MenuItem(label="Start Listening")
        self.stop_item = Gtk.MenuItem(label="Stop Listening")
        self.hotkey_toggle_item = Gtk.MenuItem(label="Pause Hotkey")
        self.open_logs_item = Gtk.MenuItem(label="Open Logs")
        self.quit_item = Gtk.MenuItem(label="Quit")

        self.start_item.connect("activate", self._on_start)
        self.stop_item.connect("activate", self._on_stop)
        self.hotkey_toggle_item.connect("activate", self._on_toggle_hotkey)
        self.open_logs_item.connect("activate", self._on_open_logs)
        self.quit_item.connect("activate", self._on_quit)

        self.menu.append(self.start_item)
        self.menu.append(self.stop_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self.hotkey_toggle_item)
        self.menu.append(self.open_logs_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self.quit_item)
        self.menu.show_all()

        self.indicator.set_menu(self.menu)
        self._refresh_ui()

        self.log.info("tray_started log_file=%s", self.log_file)

    def on_engine_state(self, state: str, detail: str) -> None:
        GLib.idle_add(self._set_state, state, detail)

    def on_engine_text(self, text: str) -> None:
        self.log.info("transcribed_text=%s", text)

    def _set_state(self, state: str, detail: str) -> bool:
        self.state = state
        self.detail = detail
        self._refresh_ui()
        return False

    def _refresh_ui(self) -> None:
        icon = ICON_BY_STATE.get(self.state, ICON_BY_STATE["Idle"])
        self.indicator.set_icon_full(icon, f"VibeWhisper {self.state}")

        self.start_item.set_sensitive(not self.engine.is_busy)
        self.stop_item.set_sensitive(self.engine.is_recording)

        if self.hotkey.enabled:
            self.hotkey_toggle_item.set_label("Pause Hotkey")
            if self.state == "Disabled":
                self.state = "Idle"
        else:
            self.hotkey_toggle_item.set_label("Resume Hotkey")
            if self.state == "Idle":
                self.indicator.set_icon_full(ICON_BY_STATE["Disabled"], "VibeWhisper Disabled")

    def notify(self, message: str) -> None:
        self.log.info("notify=%s", message)
        if shutil_which("notify-send"):
            subprocess.run(["notify-send", "VibeWhisper", message], check=False)

    def _on_start(self, _widget) -> None:
        if not self.engine.start_recording():
            self.notify("Cannot start while busy")

    def _on_stop(self, _widget) -> None:
        if not self.engine.stop_recording():
            self.notify("Not currently recording")

    def _on_toggle_hotkey(self, _widget) -> None:
        if self.hotkey.enabled:
            self.hotkey.stop()
            self.state = "Disabled"
            self.detail = "Hotkey paused"
            self.notify("Hotkey paused")
        else:
            self.hotkey.start()
            self.state = "Idle"
            self.detail = "Hotkey active"
            self.notify("Hotkey active")
        self._refresh_ui()

    def _on_open_logs(self, _widget) -> None:
        log_dir = state_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["xdg-open", str(log_dir)], check=False)

    def _on_quit(self, _widget) -> None:
        Gtk.main_quit()

    def run(self) -> None:
        signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
        signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
        Gtk.main()

    def close(self) -> None:
        try:
            self.hotkey.stop()
        finally:
            self.instance.release()


def shutil_which(name: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(":"):
        candidate = Path(p) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def load_gtk():
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib as glib_mod, Gtk as gtk_mod

        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as appindicator_mod
        except ValueError:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3 as appindicator_mod

        return glib_mod, gtk_mod, appindicator_mod
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PyGObject/AppIndicator is unavailable. Install system packages "
            "(python3-gi, gir1.2-ayatanaappindicator3-0.1) and use a venv "
            "created with --system-site-packages."
        ) from exc


def run_check(args: argparse.Namespace) -> int:
    try:
        cfg = load_runtime_config(args=args)
        load_gtk()
        log_file = setup_logging(state_dir() / "logs", cfg.log_level, console=False)
        print(f"CHECK_OK config_dir={config_dir()} state_log={log_file}")
        return 0
    except Exception as exc:
        print(f"CHECK_FAILED {exc}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VibeWhisper tray app")
    parser.add_argument("--model")
    parser.add_argument("--device")
    parser.add_argument("--compute-type", dest="compute_type")
    parser.add_argument("--language")
    parser.add_argument("--log-level")
    parser.add_argument("--no-hotkey", action="store_true")
    parser.add_argument("--check", action="store_true", help="Validate dependencies/config and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        return run_check(args)

    app: Optional[TrayApp] = None
    try:
        app = TrayApp(args)
        app.run()
        return 0
    except Exception as exc:
        if shutil_which("notify-send"):
            subprocess.run(["notify-send", "VibeWhisper", f"Tray failed: {exc}"], check=False)
        print(f"Tray startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
