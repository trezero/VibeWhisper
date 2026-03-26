#!/usr/bin/env python3
from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard

from vw_config import RuntimeConfig
from vw_logging import get_logger

StateCallback = Callable[[str, str], None]
TextCallback = Callable[[str], None]


def _which(name: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(":"):
        candidate = Path(p) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


class DictationEngine:
    def __init__(
        self,
        cfg: RuntimeConfig,
        on_state: Optional[StateCallback] = None,
        on_text: Optional[TextCallback] = None,
        notify: Optional[Callable[[str], None]] = None,
        no_type: bool = False,
    ):
        self.cfg = cfg
        self.on_state = on_state
        self.on_text = on_text
        self.notify = notify
        self.no_type = no_type

        self.log = get_logger("vibewhisper.engine")
        self.model = WhisperModel(cfg.whisper_model, device=cfg.whisper_device, compute_type=cfg.whisper_compute_type)

        self._recording_lock = threading.Lock()
        self._manual_stop_event = threading.Event()
        self._is_recording = False
        self._is_processing = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    @property
    def is_busy(self) -> bool:
        return self._is_recording or self._is_processing

    def start_recording(self) -> bool:
        if self.is_busy:
            self.log.info("start_recording ignored: busy")
            return False
        threading.Thread(target=self._record_transcribe_and_type, daemon=True).start()
        return True

    def stop_recording(self) -> bool:
        if not self._is_recording:
            return False
        self._manual_stop_event.set()
        self._emit_state("Listening", "Manual stop requested")
        if self.notify:
            self.notify("Stopping recording...")
        return True

    def _emit_state(self, state: str, detail: str) -> None:
        self.log.info("state=%s detail=%s", state, detail)
        if self.on_state:
            self.on_state(state, detail)

    def _record_transcribe_and_type(self) -> None:
        with self._recording_lock:
            self._is_recording = True
            self._emit_state("Listening", "Listening...")
            if self.notify:
                self.notify("Listening...")
            self._manual_stop_event.clear()

            try:
                audio = self._record_until_stop()
            except Exception as exc:
                self._is_recording = False
                self._emit_state("Error", f"Recording failed: {exc}")
                if self.notify:
                    self.notify(f"Recording failed: {exc}")
                return
            finally:
                self._is_recording = False

            if audio.size == 0:
                self._emit_state("Error", "No audio captured")
                if self.notify:
                    self.notify("No audio captured")
                return

            self._is_processing = True
            self._emit_state("Processing", "Transcribing audio")
            if self.notify:
                self.notify("Transcribing...")

            try:
                text = self._transcribe(audio).strip()
                if not text:
                    self._emit_state("Error", "Nothing recognized")
                    if self.notify:
                        self.notify("Nothing recognized")
                    return

                if self.on_text:
                    self.on_text(text)

                if not self.no_type:
                    self._type_into_active_app(text)
                    self._emit_state("Success", "Inserted text into active window")
                    if self.notify:
                        self.notify("Inserted transcription")
                else:
                    self._emit_state("Success", "Transcription ready (typing disabled)")
                    if self.notify:
                        self.notify(text)
            except Exception as exc:
                self._emit_state("Error", f"Processing failed: {exc}")
                if self.notify:
                    self.notify(f"Processing failed: {exc}")
            finally:
                self._is_processing = False

            self._emit_state("Idle", "Ready")

    def _record_until_stop(self) -> np.ndarray:
        blocksize = int(self.cfg.sample_rate * self.cfg.block_ms / 1000)
        chunks: list[np.ndarray] = []
        q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata: np.ndarray, _frames: int, _time_info, status) -> None:
            if status:
                self.log.warning("Audio status: %s", status)
            q.put(indata.copy())

        start = time.monotonic()
        last_voice = start

        with sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            blocksize=blocksize,
            dtype="float32",
            callback=callback,
        ):
            while True:
                chunk = q.get(timeout=2.0)
                chunks.append(chunk)

                rms = float(np.sqrt(np.mean(np.square(chunk))))
                now = time.monotonic()
                elapsed = now - start

                if rms >= self.cfg.silence_threshold:
                    last_voice = now

                enough_audio = elapsed >= self.cfg.min_record_seconds
                silence_elapsed = now - last_voice

                if enough_audio and self._manual_stop_event.is_set():
                    break
                if enough_audio and silence_elapsed >= self.cfg.silence_seconds:
                    break
                if elapsed >= self.cfg.max_record_seconds:
                    break

        if not chunks:
            return np.array([], dtype=np.float32)

        return np.concatenate(chunks, axis=0)

    def _transcribe(self, audio: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            self._write_wav(tmp_path, audio)
            segments, _ = self.model.transcribe(
                str(tmp_path),
                language=self.cfg.whisper_language,
                vad_filter=True,
                beam_size=5,
            )
            return " ".join(seg.text.strip() for seg in segments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _write_wav(self, path: Path, audio: np.ndarray) -> None:
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.cfg.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.cfg.sample_rate)
            wf.writeframes(pcm16.tobytes())

    def _type_into_active_app(self, text: str) -> None:
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session == "x11":
            self._type_x11(text)
            return

        if _which("wtype"):
            subprocess.run(["wtype", text], check=True)
            return

        raise RuntimeError("Wayland session detected but 'wtype' is not installed")

    def _type_x11(self, text: str) -> None:
        if not _which("xdotool"):
            raise RuntimeError("xdotool is required for X11 typing injection")

        subprocess.run(
            [
                "xdotool",
                "type",
                "--clearmodifiers",
                "--delay",
                str(self.cfg.type_delay_ms),
                text,
            ],
            check=True,
        )


class HotkeyController:
    def __init__(
        self,
        double_tap_window: float,
        start_fn: Callable[[], bool],
        stop_fn: Callable[[], bool],
        is_recording_fn: Callable[[], bool],
        is_busy_fn: Callable[[], bool],
        on_info: Optional[Callable[[str], None]] = None,
    ):
        self.double_tap_window = double_tap_window
        self.start_fn = start_fn
        self.stop_fn = stop_fn
        self.is_recording_fn = is_recording_fn
        self.is_busy_fn = is_busy_fn
        self.on_info = on_info
        self.log = get_logger("vibewhisper.hotkey")

        self._listener: Optional[keyboard.Listener] = None
        self._last_alt_tap = 0.0
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if self._enabled:
            return
        self._listener = keyboard.Listener(on_press=self._on_key_press)
        self._listener.start()
        self._enabled = True
        self.log.info("Hotkey listener enabled")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._enabled = False
        self.log.info("Hotkey listener disabled")

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key not in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            return

        if self.is_recording_fn():
            if self.stop_fn() and self.on_info:
                self.on_info("Stopped recording")
            return

        now = time.monotonic()
        dt = now - self._last_alt_tap
        self._last_alt_tap = now

        if dt > self.double_tap_window:
            return

        if self.is_busy_fn():
            if self.on_info:
                self.on_info("Busy processing previous dictation")
            return

        if self.start_fn() and self.on_info:
            self.on_info("Listening...")

