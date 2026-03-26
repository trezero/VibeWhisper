# VibeWhisper Desktop Productization Plan

## Goal
Ship VibeWhisper as a native Ubuntu tray application that:
- runs in background,
- is launchable from Ubuntu launcher,
- supports global hotkeys (`Alt` + `Alt` start, `Alt` stop),
- injects transcribed text into the active application,
- and is installable from a single guided `install.sh` script on a clean Ubuntu 24.04 machine.

## Current Architecture (Implemented)
- Core dictation engine and hotkey control:
  - `scripts/vw_engine.py`
- Runtime configuration loader (user config + env + CLI overrides):
  - `scripts/vw_config.py`
- Structured logging helper:
  - `scripts/vw_logging.py`
- Tray runtime with AppIndicator, status states, menu actions, single-instance lock:
  - `scripts/desktop_tray.py`
- Terminal fallback runtime using shared engine:
  - `scripts/desktop_dictate.py`
- Guided installer with launcher/autostart creation:
  - `install.sh`

## Execution Plan For Clean Session

### Phase 1: Environment + Install Validation
1. Start from clean Ubuntu 24.04 user session.
2. Clone repo and run:
   - `./install.sh`
3. Validate installer output for:
   - system package install,
   - runtime copy to `~/.local/share/vibewhisper`,
   - venv creation,
   - config generation at `~/.config/vibewhisper/config.env`,
   - wrapper creation at `~/.local/bin/vibewhisper-tray`,
   - desktop entry + autostart entry creation.

### Phase 2: Runtime Functional Validation
1. Launch from Ubuntu launcher (`VibeWhisper`) and confirm tray icon appears.
2. Verify tray states:
   - Idle -> Listening -> Processing -> Success/Error.
3. Verify menu actions:
   - Start Listening, Stop Listening, Pause/Resume Hotkey, Open Logs, Quit.
4. Verify global hotkeys:
   - double `Alt` starts recording,
   - single `Alt` while listening stops recording.
5. Verify active-window typing injection in at least:
   - gedit,
   - browser textarea,
   - terminal text field.

### Phase 3: Reliability + Re-run Validation
1. Launch second instance (launcher or wrapper command) and verify single-instance behavior.
2. Re-run installer:
   - `./install.sh --yes`
3. Confirm idempotency:
   - no duplicate launcher entries,
   - no broken wrapper,
   - tray still starts.
4. Validate optional paths:
   - `./install.sh --yes --cpu-only`
   - `./install.sh --yes --skip-ollama --no-autostart`

## Acceptance Criteria
- Tray app starts from launcher and remains backgrounded.
- Global hotkeys work consistently across common desktop apps.
- Manual stop via `Alt` works while listening.
- Logs are written to `~/.local/state/vibewhisper/logs/`.
- Installer succeeds on clean system and is safe to re-run.
- Autostart enabled by default unless `--no-autostart` is passed.

## Quick Commands
- Repo tray run (dev):
  - `npm run desktop:tray`
- Terminal hotkey run (fallback):
  - `npm run desktop:dictate`
- Installed wrapper run:
  - `~/.local/bin/vibewhisper-tray`
- Tray health check:
  - `~/.local/bin/vibewhisper-tray --check`

## Known Constraints
- First-class desktop target is Ubuntu X11.
- Wayland support is best effort (`wtype`-based fallback).
- AppIndicator requires `python3-gi` + Ayatana AppIndicator system packages.
