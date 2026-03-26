<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# VibeWhisper

Local-first voice capture app that records from your browser microphone, transcribes speech on your machine, and optionally rewrites output style with a local LLM.

## What Runs Locally

- Frontend: React + Vite (`http://localhost:3000`)
- API: Express (`http://127.0.0.1:5174`)
- Speech-to-text: `faster-whisper` (GPU when `WHISPER_DEVICE=cuda`)
- Style refinement (optional): Ollama (`OLLAMA_MODEL`)

No cloud API key is required.

## Requirements

- Node.js `20+`
- Python `3.10+`
- `ffmpeg` available in `PATH`
- For GPU: NVIDIA driver + CUDA runtime compatible with your system
- Optional: Ollama installed locally

## Quick Start

1. Install JavaScript dependencies.

```bash
npm install
```

2. Create local environment config.

```bash
cp .env.example .env.local
```

3. Create Python venv and install local transcription dependency.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-local.txt
```

4. (Optional) Start Ollama and pull model used for refinement.

```bash
ollama pull llama3.2:3b
ollama serve
```

5. Start app (frontend + local API together).

```bash
source .venv/bin/activate
npm run dev
```

6. Open the app.

```text
http://localhost:3000
```

## Environment Variables

Copy from `.env.example` and adjust in `.env.local`.

- `LOCAL_API_PORT`: Local backend port (default `5174`)
- `LOCAL_API_PROXY_TARGET`: Vite proxy target for `/api`
- `WHISPER_MODEL`: Whisper model name (default `small`)
- `WHISPER_DEVICE`: `cuda` or `cpu`
- `WHISPER_COMPUTE_TYPE`: e.g. `float16` for GPU, `int8` for CPU
- `WHISPER_LANGUAGE`: language hint (default `en`)
- `DOUBLE_TAP_WINDOW`: seconds allowed between Alt taps to trigger start
- `SILENCE_THRESHOLD`: RMS threshold for silence fallback stop
- `SILENCE_SECONDS`: consecutive silence before fallback auto-stop
- `MIN_RECORD_SECONDS`: minimum capture time before stop conditions are honored
- `MAX_RECORD_SECONDS`: hard cap on recording duration
- `TYPE_DELAY_MS`: per-character typing delay for text injection
- `LOG_LEVEL`: logging level for desktop daemons
- `OLLAMA_URL`: Ollama base URL
- `OLLAMA_MODEL`: local model used for rewriting styles

## Behavior Notes

- If Ollama is not available, transcription still works and output falls back to transcription text.
- First run may take longer because Whisper model weights are downloaded.
- Browser microphone permission must be granted.

## Scripts

```bash
npm run dev      # run frontend + local API
npm run dev:web  # run frontend only
npm run dev:api  # run local API only
npm run desktop:dictate # terminal-based global hotkey dictation
npm run desktop:tray    # tray-based desktop app
npm run lint     # TypeScript check
npm run build    # production build
```

## Desktop Dictation (Global Hotkey)

This project includes a desktop daemon that works outside the browser:

- Hotkey: double-tap `Alt`
- Action: starts listening from your mic
- Stop: press `Alt` once while listening (silence auto-stop remains fallback)
- Output: types transcription into the currently focused text field in any app

### Install desktop dependencies

```bash
sudo apt-get install -y xdotool libportaudio2
source .venv/bin/activate
pip install -r requirements-desktop.txt
```

### Run

```bash
npm run desktop:dictate
```

### Tray Runtime (Primary Desktop UX)

```bash
npm run desktop:tray
```

If this fails with a `PyGObject/AppIndicator is unavailable` error, recreate your venv with system site packages:

```bash
rm -rf .venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements-desktop.txt
```

Tray menu includes:
- Start Listening
- Stop Listening
- Pause Hotkey / Resume Hotkey
- Open Logs
- Quit

### Notes

- On Ubuntu X11 (your current session), typing injection uses `xdotool`.
- On Wayland, install `wtype` and run with proper permissions for virtual keyboard input.
- If dictation is too eager or too slow to stop, tune:
  - `--silence-threshold`
  - `--silence-seconds`
  - `--double-tap-window`

## Installer (Clean Machine)

Use the guided installer to set up dependencies, tray app launcher, autostart, and config:

```bash
./install.sh
```

Non-interactive examples:

```bash
./install.sh --yes
./install.sh --yes --cpu-only
./install.sh --yes --skip-ollama --no-autostart
```

## Troubleshooting

### 1) Vite/Tailwind startup errors on Node 18

Use Node `20+` (recommended). This project targets modern Vite/Tailwind runtime.

### 2) Whisper fails or uses CPU unexpectedly

- Verify CUDA is available (`nvidia-smi`)
- Confirm `WHISPER_DEVICE=cuda`
- Try a smaller model if VRAM is limited

### 3) No refined output style changes

- Ensure Ollama is running (`ollama serve`)
- Confirm model exists (`ollama list`)
- Check `OLLAMA_MODEL` in `.env.local`

## Project Layout

```text
src/                 React frontend
server/local-api.mjs Local processing API
scripts/transcribe.py Whisper transcription entrypoint
scripts/desktop_tray.py Tray runtime
scripts/vw_engine.py Shared desktop dictation engine
install.sh Guided installer
requirements-local.txt Python dependency list
```
