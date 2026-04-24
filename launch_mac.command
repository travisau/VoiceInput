#!/bin/bash
# Voice Input for Mac - launcher
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR"

if [ "$(basename "$SCRIPT_DIR")" = "install_files" ] && [ "$(basename "$(dirname "$SCRIPT_DIR")")" = "Data" ]; then
    APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

cd "$APP_DIR"
export HF_HOME="$APP_DIR/Data/hf_cache"
export HUGGINGFACE_HUB_CACHE="$APP_DIR/Data/hf_cache/hub"

PY_SCRIPT="voice_input.py"
if [ ! -f "$PY_SCRIPT" ] && [ -f "Data/install_files/voice_input.py" ]; then
    PY_SCRIPT="Data/install_files/voice_input.py"
fi

Data/bin/python "$PY_SCRIPT" &
