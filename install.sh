#!/usr/bin/env bash
set -euo pipefail

APP_NAME="VibeWhisper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_PYTHON="/usr/bin/python3"
APP_HOME="$HOME/.local/share/vibewhisper"
APP_SRC_DIR="$APP_HOME/app"
APP_VENV="$APP_HOME/venv"
CONFIG_DIR="$HOME/.config/vibewhisper"
CONFIG_FILE="$CONFIG_DIR/config.env"
STATE_DIR="$HOME/.local/state/vibewhisper"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/vibewhisper-tray"
DESKTOP_FILE="$HOME/.local/share/applications/vibewhisper.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/vibewhisper.desktop"

FLAG_YES=0
FLAG_CPU_ONLY=0
FLAG_NO_AUTOSTART=0
FLAG_SKIP_OLLAMA=0

log() { printf "[install] %s\n" "$*"; }
warn() { printf "[install][warn] %s\n" "$*"; }
fail() { printf "[install][error] %s\n" "$*" >&2; exit 1; }

ask_yes_no() {
  local prompt="$1"
  local default_yes="$2"

  if [[ "$FLAG_YES" -eq 1 ]]; then
    [[ "$default_yes" -eq 1 ]] && return 0 || return 1
  fi

  local suffix="[y/N]"
  [[ "$default_yes" -eq 1 ]] && suffix="[Y/n]"

  read -r -p "$prompt $suffix " reply
  if [[ -z "$reply" ]]; then
    [[ "$default_yes" -eq 1 ]] && return 0 || return 1
  fi
  case "$reply" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

usage() {
  cat <<USAGE
Usage: ./install.sh [options]

Options:
  --yes           Non-interactive mode using defaults
  --cpu-only      Configure Whisper for CPU mode
  --no-autostart  Do not install/login-enable autostart entry
  --skip-ollama   Skip Ollama install/model setup
  -h, --help      Show this help
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes) FLAG_YES=1 ;;
      --cpu-only) FLAG_CPU_ONLY=1 ;;
      --no-autostart) FLAG_NO_AUTOSTART=1 ;;
      --skip-ollama) FLAG_SKIP_OLLAMA=1 ;;
      -h|--help) usage; exit 0 ;;
      *) fail "Unknown option: $1" ;;
    esac
    shift
  done
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
}

preflight() {
  log "Running preflight checks"

  require_cmd bash
  require_cmd python3
  require_cmd curl

  if [[ ! -x "$SYSTEM_PYTHON" ]]; then
    fail "Expected system python at $SYSTEM_PYTHON (required for PyGObject)"
  fi

  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
      warn "Detected ${ID:-unknown}; this installer targets Ubuntu 24.04."
    fi
  fi

  if [[ "${XDG_SESSION_TYPE:-unknown}" != "x11" ]]; then
    warn "Session type is ${XDG_SESSION_TYPE:-unknown}. X11 is the primary supported target."
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    fail "sudo is required for system package installation"
  fi
}

install_system_packages() {
  log "Installing system dependencies"
  sudo apt-get update
  sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-ayatanaappindicator3-0.1 \
    libayatana-appindicator3-1 \
    libportaudio2 \
    xdotool \
    ffmpeg \
    ca-certificates \
    curl
}

ensure_node() {
  if command -v node >/dev/null 2>&1; then
    local major
    major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
    if [[ "$major" -ge 20 ]]; then
      log "Node.js $(node -v) detected"
      return
    fi
    warn "Node.js $(node -v) is below required 20.x"
  fi

  if ask_yes_no "Install/upgrade Node.js 20.x now?" 1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    warn "Skipping Node.js installation. Web app commands may fail."
  fi
}

prepare_runtime_tree() {
  log "Preparing per-user runtime at $APP_HOME"
  mkdir -p "$APP_HOME" "$APP_SRC_DIR" "$BIN_DIR" "$CONFIG_DIR" "$STATE_DIR" "$HOME/.local/share/applications" "$HOME/.config/autostart"

  rm -rf "$APP_SRC_DIR"
  mkdir -p "$APP_SRC_DIR"

  cp -a "$SCRIPT_DIR/scripts" "$APP_SRC_DIR/"
  cp -a "$SCRIPT_DIR/requirements-local.txt" "$APP_SRC_DIR/"
  cp -a "$SCRIPT_DIR/requirements-desktop.txt" "$APP_SRC_DIR/"
}

install_python_runtime() {
  log "Installing Python runtime"

  local recreate_venv=0
  if [[ -d "$APP_VENV" && -f "$APP_VENV/pyvenv.cfg" ]]; then
    if ! grep -q "/usr/bin" "$APP_VENV/pyvenv.cfg"; then
      warn "Existing runtime venv is not based on system python; recreating."
      recreate_venv=1
    fi
  fi

  if [[ "$recreate_venv" -eq 1 ]]; then
    rm -rf "$APP_VENV"
  fi

  if [[ ! -d "$APP_VENV" ]]; then
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$APP_VENV"
  fi

  # shellcheck disable=SC1091
  source "$APP_VENV/bin/activate"
  python -m pip install --upgrade pip
  pip install -r "$APP_SRC_DIR/requirements-desktop.txt"
}

install_node_deps_optional() {
  if [[ -f "$SCRIPT_DIR/package.json" ]] && command -v npm >/dev/null 2>&1; then
    log "Installing project npm dependencies"
    (cd "$SCRIPT_DIR" && npm install)
  else
    warn "Skipping npm install (npm unavailable or package.json missing)"
  fi
}

ensure_ollama() {
  if [[ "$FLAG_SKIP_OLLAMA" -eq 1 ]]; then
    log "Skipping Ollama setup (--skip-ollama)"
    return
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    if ask_yes_no "Install Ollama now?" 1; then
      curl -fsSL https://ollama.com/install.sh | sh
    else
      warn "Skipping Ollama install; refinement features may be unavailable"
      return
    fi
  fi

  sudo systemctl enable --now ollama || true

  if ask_yes_no "Pull recommended local model llama3.2:3b?" 1; then
    ollama pull llama3.2:3b
  fi
}

upsert_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"

  if grep -qE "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$file"
  else
    printf '%s="%s"\n' "$key" "$value" >> "$file"
  fi
}

write_user_config() {
  log "Writing runtime config to $CONFIG_FILE"
  touch "$CONFIG_FILE"

  upsert_env_value "$CONFIG_FILE" "WHISPER_MODEL" "small"
  if [[ "$FLAG_CPU_ONLY" -eq 1 ]]; then
    upsert_env_value "$CONFIG_FILE" "WHISPER_DEVICE" "cpu"
    upsert_env_value "$CONFIG_FILE" "WHISPER_COMPUTE_TYPE" "int8"
  else
    upsert_env_value "$CONFIG_FILE" "WHISPER_DEVICE" "cuda"
    upsert_env_value "$CONFIG_FILE" "WHISPER_COMPUTE_TYPE" "float16"
  fi
  upsert_env_value "$CONFIG_FILE" "WHISPER_LANGUAGE" "en"
  upsert_env_value "$CONFIG_FILE" "DOUBLE_TAP_WINDOW" "0.35"
  upsert_env_value "$CONFIG_FILE" "SILENCE_THRESHOLD" "0.02"
  upsert_env_value "$CONFIG_FILE" "SILENCE_SECONDS" "1.0"
  upsert_env_value "$CONFIG_FILE" "MIN_RECORD_SECONDS" "0.8"
  upsert_env_value "$CONFIG_FILE" "MAX_RECORD_SECONDS" "45"
  upsert_env_value "$CONFIG_FILE" "TYPE_DELAY_MS" "1"
  upsert_env_value "$CONFIG_FILE" "SAMPLE_RATE" "16000"
  upsert_env_value "$CONFIG_FILE" "CHANNELS" "1"
  upsert_env_value "$CONFIG_FILE" "BLOCK_MS" "50"
  upsert_env_value "$CONFIG_FILE" "LOG_LEVEL" "INFO"
  upsert_env_value "$CONFIG_FILE" "OLLAMA_MODEL" "llama3.2:3b"
}

install_wrapper() {
  log "Installing wrapper executable to $WRAPPER"
  cat > "$WRAPPER" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
APP_HOME="$APP_HOME"
CONFIG_FILE="$CONFIG_FILE"
VENV_PY="\$APP_HOME/venv/bin/python"
APP_SCRIPT="\$APP_HOME/app/scripts/desktop_tray.py"

if [[ -f "\$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "\$CONFIG_FILE"
fi

exec "\$VENV_PY" "\$APP_SCRIPT" "\$@"
WRAP
  chmod +x "$WRAPPER"
}

install_desktop_entries() {
  log "Installing launcher entry"
  cat > "$DESKTOP_FILE" <<DESK
[Desktop Entry]
Type=Application
Name=VibeWhisper
Comment=Local desktop dictation tray app
Exec=$WRAPPER
Icon=audio-input-microphone-symbolic
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=false
DESK

  if [[ "$FLAG_NO_AUTOSTART" -eq 1 ]]; then
    rm -f "$AUTOSTART_FILE"
    log "Autostart disabled (--no-autostart)"
  else
    cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
    log "Autostart enabled at login"
  fi
}

post_install_checks() {
  log "Running post-install health checks"

  if [[ ! -x "$WRAPPER" ]]; then
    fail "Wrapper not executable: $WRAPPER"
  fi

  "$WRAPPER" --check

  if command -v ollama >/dev/null 2>&1 && [[ "$FLAG_SKIP_OLLAMA" -eq 0 ]]; then
    ollama list >/dev/null 2>&1 || warn "Ollama is installed but not responding"
  fi

  log "Install complete"
  cat <<DONE

Next steps:
  1. Launch from Ubuntu app grid: VibeWhisper
  2. Or run manually: $WRAPPER
  3. Hotkey: double Alt to start, Alt once to stop
  4. Logs: $STATE_DIR/logs
DONE
}

main() {
  parse_args "$@"
  preflight
  install_system_packages
  ensure_node
  prepare_runtime_tree
  install_python_runtime
  install_node_deps_optional
  ensure_ollama
  write_user_config
  install_wrapper
  install_desktop_entries
  post_install_checks
}

main "$@"
