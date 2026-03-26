#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Whisper transcription")
    parser.add_argument("--audio", required=True, help="Path to input audio file")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model name")
    parser.add_argument("--device", default="cuda", choices=["cpu", "cuda"], help="Inference device")
    parser.add_argument("--compute-type", default="float16", help="CTranslate2 compute type")
    parser.add_argument("--language", default="en", help="Language hint for transcription")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"Audio file does not exist: {audio_path}", file=sys.stderr)
        return 2

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover
        print(
            "Missing dependency 'faster-whisper'. Install with: pip install -r requirements-local.txt",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 3

    try:
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
        segments, info = model.transcribe(
            str(audio_path),
            language=args.language,
            vad_filter=True,
            beam_size=5,
        )

        text = " ".join(segment.text.strip() for segment in segments).strip()
        payload = {
            "transcription": text,
            "language": getattr(info, "language", args.language),
            "duration": getattr(info, "duration", None),
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(f"Transcription failed: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
