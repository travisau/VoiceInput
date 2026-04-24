# Voice Input

Offline speech-to-text for Windows and macOS, powered by faster-whisper.

Voice Input runs quietly from the system tray / menu bar. Hold a hotkey, speak, and the transcribed text is copied to your clipboard or pasted directly into the active app.

## Features

- Offline speech-to-text using faster-whisper
- Windows and macOS support
- Tray / menu bar app with quick settings
- Hold-to-record or toggle recording mode
- Clipboard-only or auto-paste output
- Traditional / Simplified Chinese conversion
- Local model cache stored beside the app

## Author

Created by Travis Au  
Contact: contact@travis-studio.com

## Download

For normal users, download the prebuilt app from GitHub Releases.

Prebuilt releases do not require Python to be installed.

## Build From Source

Building from source is for developers or advanced users. It creates a local Python environment in `Data/`, installs the required packages, and builds the app executable.

### Windows

Requirements:

- Python 3.12
- Windows `py` launcher

Build:

```bat
install.bat
```

Output:

```text
VoiceInput.exe
```

### macOS

Requirements:

- Python 3

Build:

```bash
chmod +x install_mac.sh launch_mac.command
./install_mac.sh
```

Output:

```text
VoiceInput
```

macOS may ask for permissions in Privacy & Security:

- Microphone
- Accessibility
- Input Monitoring

## Runtime Files

After install/build, the app root should contain:

```text
VoiceInput.exe    # Windows
VoiceInput        # macOS
config.json
Data/
```

Whisper models are stored locally:

```text
Data/hf_cache
```

Install/source files are moved into:

```text
Data/install_files
```

## Default Settings

```text
Hotkey: Ctrl+F9
Mode: Hold to record
Output: Copy to clipboard
Model: large-v3
Device: CPU
```

The first model download can be large. `large-v3` is about 3GB.

## Repository Notes

Do not commit generated runtime files:

```text
VoiceInput.exe
VoiceInput
Data/
config.json
build/
dist/
*.spec
```

Publish built executables through GitHub Releases instead of committing them to the repository.
