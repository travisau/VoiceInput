#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR"

if [ "$(basename "$SCRIPT_DIR")" = "install_files" ] && [ "$(basename "$(dirname "$SCRIPT_DIR")")" = "Data" ]; then
    APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

cd "$APP_DIR"
INSTALL_FILES="Data/install_files"
SOURCE_PY="voice_input.py"
if [ ! -f "$SOURCE_PY" ] && [ -f "$INSTALL_FILES/voice_input.py" ]; then
    SOURCE_PY="$INSTALL_FILES/voice_input.py"
fi

echo "================================================"
echo " Voice Input for Mac - Install and Build"
echo "================================================"
echo ""

if [ ! -d "Data" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv Data
else
    echo "[1/3] Data/ already exists, skipping..."
fi
source Data/bin/activate

echo ""
echo "[2/3] Installing packages..."
python -m pip install --upgrade pip
python -m pip install faster-whisper sounddevice scipy numpy pyperclip pyautogui pystray pillow keyboard opencc-python-reimplemented pyinstaller

echo ""
echo "[3/3] Building VoiceInput..."
pyinstaller \
  --noconsole \
  --onefile \
  --name "VoiceInput" \
  --distpath "." \
  --collect-data opencc \
  --collect-data faster_whisper \
  --hidden-import "scipy.signal" \
  --hidden-import "scipy.io.wavfile" \
  "$SOURCE_PY"

echo ""
echo "================================================"
if [ -f "VoiceInput" ]; then
    echo " Done! VoiceInput is ready here."
    echo " Cleaning up build files..."
    rm -rf build dist VoiceInput.spec
    if [ ! -f "config.json" ]; then
        echo " Creating default config.json..."
        cat > config.json <<'JSON'
{
  "model": "large-v3",
  "language": "auto",
  "paste_mode": "clipboard",
  "device": "cpu",
  "hotkey_mode": "hold",
  "hotkey": "ctrl+f9",
  "chinese_output": "traditional",
  "cpu_threads": 0,
  "start_at_login": false,
  "app_language": "en"
}
JSON
    else
        echo " config.json already exists, keeping current settings."
    fi
    echo " Moving install files into $INSTALL_FILES..."
    mkdir -p "$INSTALL_FILES"
    [ -f "voice_input.py" ] && mv -f "voice_input.py" "$INSTALL_FILES/"
    [ -f "install.bat" ] && mv -f "install.bat" "$INSTALL_FILES/"
    [ -f "launch_mac.command" ] && mv -f "launch_mac.command" "$INSTALL_FILES/"
    if [ "$0" != "$APP_DIR/$INSTALL_FILES/install_mac.sh" ]; then
        mv -f "$0" "$APP_DIR/$INSTALL_FILES/"
    fi
    echo " Cleanup complete."
else
    echo " Something went wrong. Check the output above."
fi
echo "================================================"
