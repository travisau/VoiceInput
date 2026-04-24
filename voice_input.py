"""
VoiceInput v1.0
Offline speech-to-text tool powered by faster-whisper
Author : Travis Au
Contact: contact@travis-studio.com
"""

import platform as _platform

_OS          = _platform.system()   # "Windows" / "Darwin" / "Linux"
_IS_WIN      = _OS == "Windows"
_IS_MAC      = _OS == "Darwin"

_OS_LABEL    = "for Windows" if _IS_WIN else "for Mac" if _IS_MAC else "for Linux"
APP_NAME     = f"Voice Input {_OS_LABEL}"
APP_VERSION  = "1.0"
APP_AUTHOR   = "Travis Au"
APP_EMAIL    = "contact@travis-studio.com"

import threading
import json
import os
import tempfile
import time

if _IS_WIN:
    import ctypes

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import keyboard
import pyperclip
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import pystray
import tkinter as tk
from tkinter import ttk, messagebox

# ── Config ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import sys as _sys
if getattr(_sys, "frozen", False):
    BASE_DIR = os.path.dirname(_sys.executable)

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Always store model cache next to the exe / script
_hf_cache = os.path.join(BASE_DIR, "Data", "hf_cache")
os.makedirs(_hf_cache, exist_ok=True)
# Force-set regardless of existing env vars so models stay next to the exe / script.
os.environ["HF_HOME"] = _hf_cache
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(_hf_cache, "hub")

DEFAULT_CONFIG = {
    "model":          "large-v3",
    "language":       "auto",
    "paste_mode":     "clipboard",
    "device":         "cpu",
    "hotkey_mode":    "hold",
    "hotkey":         "ctrl+f9",
    "chinese_output": "traditional",  # traditional / simplified / none
    "cpu_threads":    0               # 0 = auto (use all cores)
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        # Migrate old "none" value to "traditional"
        if cfg.get("chinese_output") == "none":
            cfg["chinese_output"] = "traditional"
        return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ── Chinese conversion ────────────────────────────────────────
_opencc_converter = {}

def convert_chinese(text, mode):
    """mode: 'traditional' | 'simplified' | 'none'"""
    if mode == "none" or not text:
        return text
    try:
        import opencc
        key = mode
        if key not in _opencc_converter:
            cfg_map = {
                "traditional": "s2twp.json",   # Simplified → Traditional (Taiwan)
                "simplified":  "tw2sp.json",    # Traditional → Simplified
            }
            _opencc_converter[key] = opencc.OpenCC(cfg_map[key])
        return _opencc_converter[key].convert(text)
    except Exception:
        return text   # fallback: return as-is if opencc not installed

# ── Global state ─────────────────────────────────────────────
config        = load_config()
is_recording  = False
audio_chunks  = []
sample_rate   = 16000
stream        = None
tray_icon     = None
whisper_model = None
model_lock    = threading.Lock()

# ── Load Whisper model ────────────────────────────────────────
def ensure_model():
    global whisper_model
    with model_lock:
        if whisper_model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            set_icon("loading")
            if tray_icon:
                hf_home    = os.environ.get("HF_HOME", os.path.join(os.path.expanduser("~"), ".cache", "huggingface"))
                model_path = os.path.join(hf_home, "hub", f"models--Systran--faster-whisper-{config['model']}")
                if os.path.exists(model_path):
                    tray_icon.notify(f"Model: {config['model']}", "Loading into memory, please wait...")
                else:
                    tray_icon.notify(f"Model: {config['model']}", "Downloading (~3GB), please wait...")
            cpu_threads = config.get("cpu_threads", 0)
            if cpu_threads == 0:
                cpu_threads = os.cpu_count() or 4   # use all available threads
            whisper_model = WhisperModel(
                config["model"],
                device=config["device"],
                compute_type="float16" if config["device"] == "cuda" else "int8",
                cpu_threads=cpu_threads,
                num_workers=1
            )
            set_icon("idle")
            return True
        except Exception as e:
            set_icon("idle")
            if tray_icon:
                tray_icon.notify(APP_NAME, str(e)[:100])
            return False

# ── Tray icons ────────────────────────────────────────────────
def make_icon(bg_color, dot=None):
    """Draw a microphone icon with coloured background."""
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Background circle
    d.ellipse([2, 2, S-2, S-2], fill=bg_color)

    # Microphone body (rounded rect)
    mic_x0, mic_y0, mic_x1, mic_y1 = 22, 10, 42, 34
    d.rounded_rectangle([mic_x0, mic_y0, mic_x1, mic_y1], radius=9, fill="white")

    # Arc (stand arc)
    d.arc([15, 22, 49, 46], start=0, end=180, fill="white", width=3)

    # Stem
    d.line([32, 46, 32, 54], fill="white", width=3)

    # Base
    d.line([24, 54, 40, 54], fill="white", width=3)

    # Optional dot overlay (for loading state)
    if dot:
        d.ellipse([38, 38, 54, 54], fill=dot, outline=bg_color, width=2)

    return img

ICONS = {
    "idle":      make_icon("#22c55e"),
    "recording": make_icon("#ef4444"),
    "busy":      make_icon("#f59e0b"),
    "loading":   make_icon("#6366f1", "white"),
}

def _fmt_hotkey(hk):
    """ctrl+f9  →  Ctrl+F9"""
    return "+".join(p.capitalize() for p in hk.split("+"))

def _get_title():
    hk   = _fmt_hotkey(config.get("hotkey", "ctrl+f9"))
    mode = config.get("hotkey_mode", "hold")
    if mode == "hold":
        return f"Voice Input - Hold {hk} to record"
    else:
        return f"Voice Input - Press {hk} to start/stop"

def set_icon(state):
    if tray_icon is None:
        return
    titles = {
        "idle":      _get_title(),
        "recording": "Recording... (release / press again to stop)",
        "busy":      "Transcribing...",
        "loading":   "Loading Whisper model...",
    }
    try:
        tray_icon.icon  = ICONS.get(state, ICONS["idle"])
        tray_icon.title = titles.get(state, "")
    except Exception:
        pass

# ── Recording ────────────────────────────────────────────────
def _audio_callback(indata, frames, time_info, status):
    if is_recording:
        audio_chunks.append(indata.copy())

def start_recording():
    global is_recording, audio_chunks, stream
    if is_recording:
        return
    if not ensure_model():
        return
    audio_chunks = []
    is_recording = True
    set_icon("recording")
    stream = sd.InputStream(
        samplerate=sample_rate, channels=1,
        dtype="float32", callback=_audio_callback
    )
    stream.start()

def stop_and_transcribe():
    global is_recording, stream
    if not is_recording:
        return
    is_recording = False
    if stream:
        stream.stop()
        stream.close()
    set_icon("busy")

    if not audio_chunks:
        set_icon("idle")
        return

    audio_np  = np.concatenate(audio_chunks, axis=0)
    audio_i16 = (audio_np * 32767).astype(np.int16)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav.write(tmp.name, sample_rate, audio_i16)
    tmp.close()

    try:
        lang = None if config["language"] == "auto" else config["language"]
        t_start = time.time()
        segments, _ = whisper_model.transcribe(
            tmp.name, language=lang, beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300)
        )
        text    = "".join(seg.text for seg in segments).strip()
        elapsed = time.time() - t_start
        text    = convert_chinese(text, config.get("chinese_output", "traditional"))

        device_label = "GPU" if config["device"] == "cuda" else "CPU"
        notify_sub   = f"{device_label}  ·  {elapsed:.1f}s"

        if text:
            pyperclip.copy(text)
            if config["paste_mode"] == "autopaste":
                time.sleep(0.15)
                pyautogui.hotkey("command" if _IS_MAC else "ctrl", "v")
            else:
                if tray_icon:
                    tray_icon.notify(notify_sub, text[:64])
    except Exception as e:
        if tray_icon:
            tray_icon.notify(APP_NAME, str(e)[:100])
    finally:
        os.unlink(tmp.name)
        set_icon("idle")

# ── Hotkey handling ───────────────────────────────────────────
_hotkey_hook = None

def toggle_recording():
    """Used by tray click and hotkey toggle mode."""
    if not is_recording:
        threading.Thread(target=start_recording, daemon=True).start()
    else:
        threading.Thread(target=stop_and_transcribe, daemon=True).start()

def _parse_hotkey(hk_str):
    """Split 'ctrl+f9' into modifier keys and main key."""
    parts = [p.strip().lower() for p in hk_str.split("+")]
    main_key  = parts[-1]
    modifiers = parts[:-1]
    return main_key, modifiers

def _modifiers_held(modifiers):
    for m in modifiers:
        if not keyboard.is_pressed(m):
            return False
    return True

def _make_hook(hotkey_str, mode):
    main_key, modifiers = _parse_hotkey(hotkey_str)

    def on_event(e):
        if e.name != main_key:
            return
        if mode == "hold":
            if e.event_type == keyboard.KEY_DOWN and _modifiers_held(modifiers) and not is_recording:
                threading.Thread(target=start_recording, daemon=True).start()
            elif e.event_type == keyboard.KEY_UP and is_recording:
                threading.Thread(target=stop_and_transcribe, daemon=True).start()
        else:  # toggle
            if e.event_type == keyboard.KEY_DOWN and _modifiers_held(modifiers):
                toggle_recording()

    return on_event

def register_hotkey():
    global _hotkey_hook
    if _hotkey_hook:
        keyboard.unhook(_hotkey_hook)
    _hotkey_hook = keyboard.hook(_make_hook(config["hotkey"], config["hotkey_mode"]))

# ── Settings window ───────────────────────────────────────────
MODEL_INFO = {
    "tiny":     "Fastest, lower accuracy (~75MB)",
    "base":     "Fast, basic accuracy (~145MB)",
    "small":    "Balanced (~460MB)",
    "medium":   "Recommended for Cantonese (~1.5GB)",
    "large-v2": "High accuracy (~3GB)",
    "large-v3": "Best & latest (~3GB)",
}

def open_settings():
    win = tk.Tk()
    win.title("Voice Input Settings")
    win.geometry("520x920")
    win.resizable(False, True)
    win.configure(bg="#f8f8f8")

    # ── Scrollable area (top) ──
    canvas    = tk.Canvas(win, bg="#f8f8f8", highlightthickness=0)
    scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="top", fill="both", expand=True)

    inner     = tk.Frame(canvas, bg="#f8f8f8")
    inner_id  = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))
    def _on_canvas_configure(e):
        canvas.itemconfig(inner_id, width=e.width)
    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

    f = inner   # parent for all setting widgets

    def section(text):
        tk.Label(f, text=text, font=("Arial", 10, "bold"),
                 bg="#f8f8f8", anchor="w").pack(fill="x", padx=24, pady=(16, 4))

    def sep():
        ttk.Separator(f, orient="horizontal").pack(fill="x", padx=24, pady=4)

    # ── Model ──
    section("Whisper Model")
    model_var = tk.StringVar(value=config["model"])
    info_var  = tk.StringVar(value=MODEL_INFO.get(config["model"], ""))
    row = tk.Frame(f, bg="#f8f8f8")
    row.pack(fill="x", padx=24)
    model_menu = ttk.Combobox(row, textvariable=model_var,
                               values=list(MODEL_INFO.keys()), state="readonly", width=14)
    model_menu.pack(side="left")
    tk.Label(row, textvariable=info_var, bg="#f8f8f8", fg="#555",
             font=("Arial", 9)).pack(side="left", padx=10)
    def on_model_change(e=None):
        global whisper_model
        info_var.set(MODEL_INFO.get(model_var.get(), ""))
        whisper_model = None
        update_dl_status()
    model_menu.bind("<<ComboboxSelected>>", on_model_change)

    # ── Download section ──
    dl_frame = tk.Frame(f, bg="#f8f8f8")
    dl_frame.pack(fill="x", padx=24, pady=(6, 0))

    # Row 1: Downloading text
    dl_status_var = tk.StringVar(value="")
    dl_status_lbl = tk.Label(dl_frame, textvariable=dl_status_var,
                              bg="#f8f8f8", fg="#555", font=("Arial", 9), anchor="w")
    dl_status_lbl.pack(fill="x")

    # Row 2: Download progress bar (hidden until started)
    dl_progress = ttk.Progressbar(dl_frame, orient="horizontal",
                                   length=400, mode="determinate")
    dl_progress_visible = [False]

    # Row 3: Fetching text
    dl_status2_var = tk.StringVar(value="")
    dl_status2_lbl = tk.Label(dl_frame, textvariable=dl_status2_var,
                               bg="#f8f8f8", fg="#333", font=("Arial", 9), anchor="w")
    dl_status2_lbl.pack(fill="x")

    # Row 4: Fetching progress bar (hidden until started)
    dl_progress2 = ttk.Progressbar(dl_frame, orient="horizontal",
                                    length=400, mode="determinate")
    dl_progress2_visible = [False]

    # Row 5: Buttons
    btn_row = tk.Frame(dl_frame, bg="#f8f8f8")
    btn_row.pack(anchor="w", pady=(6, 0))

    dl_btn_var = tk.StringVar(value="Download")
    dl_btn = tk.Button(btn_row, textvariable=dl_btn_var,
                       bg="#3b82f6", fg="white", font=("Arial", 9, "bold"),
                       relief="flat", padx=10, pady=3, cursor="hand2")
    dl_btn.pack(side="left")

    del_btn = tk.Button(btn_row, text="Delete Model",
                        bg="#ef4444", fg="white", font=("Arial", 9, "bold"),
                        relief="flat", padx=10, pady=3, cursor="hand2")
    del_btn.pack(side="left", padx=(8, 0))

    MODEL_SIZES_BYTES = {
        "tiny":     78_000_000,
        "base":    148_000_000,
        "small":   484_000_000,
        "medium":  1_528_000_000,
        "large-v2":3_090_000_000,
        "large-v3":3_090_000_000,
    }

    def get_model_cache_path(name):
        hf_home = os.environ.get(
            "HF_HOME",
            os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
        )
        return os.path.join(hf_home, "hub", f"models--Systran--faster-whisper-{name}")

    def get_cached_size(name):
        path       = get_model_cache_path(name)
        blobs_path = os.path.join(path, "blobs")
        check      = blobs_path if os.path.exists(blobs_path) else path
        if not os.path.exists(check):
            return 0
        total = 0
        for dp, _, files in os.walk(check):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except Exception:
                    pass
        return total

    def fmt_size(b):
        if b < 1024**3:
            return f"{b/1024**2:.0f} MB"
        return f"{b/1024**3:.2f} GB"

    def update_dl_status():
        name     = model_var.get()
        cached   = get_cached_size(name)
        expected = MODEL_SIZES_BYTES.get(name, 0)
        if expected and cached >= expected * 0.97:
            dl_status_var.set(f"Already downloaded  ({fmt_size(cached)})")
            dl_btn_var.set("Re-download")
            dl_btn.config(bg="#6b7280")
        elif cached > 0:
            dl_status_var.set(
                f"Partial download ({fmt_size(cached)} / {fmt_size(expected)}) - will resume"
            )
            dl_btn_var.set("Resume Download")
            dl_btn.config(bg="#f59e0b")
        else:
            dl_status_var.set(f"Not downloaded yet  (~{fmt_size(expected)})")
            dl_btn_var.set("Download")
            dl_btn.config(bg="#3b82f6")

    update_dl_status()

    _dl_running = [False]

    def do_delete():
        if _dl_running[0]:
            messagebox.showwarning("Download in progress", "Please wait for the download to finish first.")
            return
        name = model_var.get()
        path = get_model_cache_path(name)
        if not os.path.exists(path):
            messagebox.showinfo("Not found", f"{name} is not downloaded.")
            return
        size = get_cached_size(name)
        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Delete {name} model?\n\nPath:\n{path}\n\nSize: {fmt_size(size)}\n\nThis cannot be undone."
        )
        if not confirmed:
            return
        try:
            import shutil
            shutil.rmtree(path)
            global whisper_model
            whisper_model = None
            update_dl_status()
            dl_status_var.set(f"{name} deleted successfully.")
            dl_status2_var.set("")
            if dl_progress_visible[0]:
                dl_progress["value"] = 0
            if dl_progress2_visible[0]:
                dl_progress2["value"] = 0
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))

    del_btn.config(command=do_delete)

    def do_download():
        if _dl_running[0]:
            return
        _dl_running[0] = True
        name     = model_var.get()

        if not dl_progress_visible[0]:
            dl_progress.pack(fill="x", pady=(2, 2), after=dl_status_lbl)
            dl_progress_visible[0] = True

        dl_btn.config(state="disabled")
        dl_status_var.set("Starting download...")
        dl_status2_var.set("")

        def _run():
            import queue as _queue
            import sys as _sys
            import re as _re

            msg_q = _queue.Queue()

            class _Capture:
                """Intercept tqdm stderr output"""
                def write(self, txt):
                    for chunk in txt.replace('\r', '\n').split('\n'):
                        chunk = chunk.strip()
                        if chunk:
                            msg_q.put(chunk)
                def flush(self):
                    pass
                def isatty(self):
                    return True   # tell tqdm it's a real terminal

            old_stderr = _sys.stderr
            _sys.stderr = _Capture()
            done = [False]
            err  = [None]

            def _download():
                try:
                    from huggingface_hub import snapshot_download
                    snapshot_download(
                        repo_id=f"Systran/faster-whisper-{name}",
                        cache_dir=os.environ["HUGGINGFACE_HUB_CACHE"],
                        local_files_only=False,
                    )
                except Exception as e:
                    err[0] = str(e)
                finally:
                    done[0] = True
                    _sys.stderr = old_stderr

            threading.Thread(target=_download, daemon=True).start()

            last_dl    = [""]
            last_fetch = [""]

            def clean_line(line):
                import re as _r
                # Remove "(incomplete total...)" and variants
                cleaned = _r.sub(r'\s*\(incomplete total[^)]*\)', '', line)
                # Remove |####...####| bar portion
                cleaned = _r.sub(r'\|[^|]*\|\s*', '  ', cleaned, count=1)
                # Reformat "Fetching N files: XX%  stats" → "Fetching: N files  XX%  stats"
                m = _r.match(r'Fetching (\d+ files):\s*(.*)', cleaned)
                if m:
                    return f"Fetching:  {m.group(1)}  {m.group(2).strip()}"
                return cleaned.strip()

            while not done[0] or not msg_q.empty():
                while not msg_q.empty():
                    try:
                        line = msg_q.get_nowait()
                        if "Fetching" in line:
                            last_fetch[0] = clean_line(line)
                            m = _re.search(r'(\d+)%', line)
                            if m:
                                if not dl_progress2_visible[0]:
                                    dl_progress2.pack(fill="x", pady=(2, 2), after=dl_status2_lbl)
                                    dl_progress2_visible[0] = True
                                dl_progress2["value"] = int(m.group(1))
                        elif "%" in line or "Downloading" in line:
                            last_dl[0] = clean_line(line)
                            m = _re.search(r'(\d+)%', line)
                            if m:
                                dl_progress["value"] = int(m.group(1))
                    except Exception:
                        pass

                if last_dl[0]:
                    dl_status_var.set(last_dl[0])
                if last_fetch[0]:
                    dl_status2_var.set(last_fetch[0])
                time.sleep(0.25)

            if err[0]:
                dl_status_var.set(f"Error: {err[0][:70]}")
                dl_status2_var.set("")
                dl_btn.config(bg="#ef4444")
            else:
                dl_progress["value"] = 100
                if dl_progress2_visible[0]:
                    dl_progress2["value"] = 100
                final = get_cached_size(name)
                dl_status_var.set(f"Download complete!  ({fmt_size(final)})")
                dl_status2_var.set("")
                dl_btn_var.set("Re-download")
                dl_btn.config(bg="#6b7280")

            _dl_running[0] = False
            dl_btn.config(state="normal")

        threading.Thread(target=_run, daemon=True).start()

    dl_btn.config(command=do_download)

    sep()

    # ── Language ──
    section("Language")
    lang_var = tk.StringVar(value=config["language"])
    lang_row = tk.Frame(f, bg="#f8f8f8")
    lang_row.pack(anchor="w", padx=24)
    for label, val in [("Auto detect (recommended)", "auto"), ("Chinese / Cantonese", "zh"), ("English", "en")]:
        tk.Radiobutton(lang_row, text=label, variable=lang_var, value=val,
                       bg="#f8f8f8", font=("Arial", 10)).pack(side="left", padx=(0, 10))

    sep()

    # ── Chinese output ──
    section("Chinese Output")
    chinese_var = tk.StringVar(value=config.get("chinese_output", "traditional"))
    chinese_row = tk.Frame(f, bg="#f8f8f8")
    chinese_row.pack(anchor="w", padx=24)
    for label, val in [("正體字 Traditional", "traditional"), ("简体字 Simplified", "simplified"), ("No conversion", "none")]:
        tk.Radiobutton(chinese_row, text=label, variable=chinese_var, value=val,
                       bg="#f8f8f8", font=("Arial", 10)).pack(side="left", padx=(0, 12))

    sep()

    # ── Paste mode ──
    section("After transcription")
    paste_var = tk.StringVar(value=config["paste_mode"])
    paste_row = tk.Frame(f, bg="#f8f8f8")
    paste_row.pack(anchor="w", padx=24)
    for label, val in [("Auto-paste to cursor", "autopaste"), ("Copy to clipboard only", "clipboard")]:
        tk.Radiobutton(paste_row, text=label, variable=paste_var, value=val,
                       bg="#f8f8f8", font=("Arial", 10)).pack(side="left", padx=(0, 14))

    sep()

    # ── Hotkey mode ──
    section("Hotkey Mode")
    hkmode_var = tk.StringVar(value=config["hotkey_mode"])
    hkmode_row = tk.Frame(f, bg="#f8f8f8")
    hkmode_row.pack(anchor="w", padx=24)
    tk.Radiobutton(hkmode_row, text="Hold to record (release to stop)",
                   variable=hkmode_var, value="hold",
                   bg="#f8f8f8", font=("Arial", 10)).pack(anchor="w")
    tk.Radiobutton(hkmode_row, text="Press once to start / press again to stop",
                   variable=hkmode_var, value="toggle",
                   bg="#f8f8f8", font=("Arial", 10)).pack(anchor="w")

    sep()

    # ── Hotkey ──
    section("Hotkey")
    tk.Label(f, text="Type below, or click Capture and press your keys:",
             bg="#f8f8f8", fg="#555", font=("Arial", 9)).pack(anchor="w", padx=24)

    hk_frame  = tk.Frame(f, bg="#f8f8f8")
    hk_frame.pack(anchor="w", padx=24, pady=4)
    hk_var    = tk.StringVar(value=_fmt_hotkey(config["hotkey"]))
    hk_entry  = tk.Entry(hk_frame, textvariable=hk_var, font=("Arial", 11), width=18)
    hk_entry.pack(side="left")
    hk_status = tk.StringVar(value="")
    tk.Label(hk_frame, textvariable=hk_status, bg="#f8f8f8",
             fg="#22c55e", font=("Arial", 9)).pack(side="left", padx=8)

    captured_keys = []
    capturing     = [False]

    def start_capture():
        capturing[0] = True
        captured_keys.clear()
        hk_var.set("")
        hk_status.set("Press your keys now...")
        hk_entry.focus_set()

    def on_key_capture(e):
        if not capturing[0]:
            return
        if e.event_type != keyboard.KEY_DOWN:
            return
        if e.name == "escape":
            capturing[0] = False
            hk_status.set("Cancelled")
            return
        if e.name not in captured_keys:
            captured_keys.append(e.name)
        hk_var.set("+".join(captured_keys))

    def stop_capture(e=None):
        if capturing[0]:
            capturing[0] = False
            hk_status.set("Hotkey set!")

    capture_hook = keyboard.hook(on_key_capture)
    hk_entry.bind("<KeyRelease>", stop_capture)

    tk.Button(hk_frame, text="Capture",
              command=start_capture,
              bg="#6366f1", fg="white", font=("Arial", 9, "bold"),
              relief="flat", padx=8, pady=3, cursor="hand2").pack(side="left", padx=4)

    tk.Label(f, text="Examples:  ctrl+f9   alt+z   f8   ctrl+shift+space",
             bg="#f8f8f8", fg="#888", font=("Arial", 8)).pack(anchor="w", padx=24, pady=(0, 4))

    sep()

    # ── Device ──
    section("Compute Device")
    device_var = tk.StringVar(value=config["device"])
    dev_row = tk.Frame(f, bg="#f8f8f8")
    dev_row.pack(anchor="w", padx=24)
    for label, val in [("CPU (universal)", "cpu"), ("CUDA GPU (NVIDIA only)", "cuda")]:
        tk.Radiobutton(dev_row, text=label, variable=device_var, value=val,
                       bg="#f8f8f8", font=("Arial", 10)).pack(side="left", padx=(0, 14))

    # CPU threads slider
    max_threads = os.cpu_count() or 8
    thread_val  = config.get("cpu_threads", 0)
    cpu_var = tk.IntVar(value=thread_val if thread_val > 0 else max_threads)
    thread_row = tk.Frame(f, bg="#f8f8f8")
    thread_row.pack(anchor="w", padx=24, pady=(6, 0))
    tk.Label(thread_row, text="CPU Threads:", bg="#f8f8f8", font=("Arial", 9)).pack(side="left")
    thread_label = tk.Label(thread_row, text=str(cpu_var.get()), bg="#f8f8f8",
                            font=("Arial", 9, "bold"), width=3)
    thread_label.pack(side="left", padx=4)
    def on_thread_slide(val):
        thread_label.config(text=str(int(float(val))))
    tk.Scale(thread_row, from_=1, to=max_threads, orient="horizontal",
             variable=cpu_var, command=on_thread_slide,
             bg="#f8f8f8", length=200, showvalue=False).pack(side="left")
    tk.Label(thread_row, text=f"(max {max_threads})", bg="#f8f8f8",
             fg="#888", font=("Arial", 8)).pack(side="left", padx=6)

    tk.Label(f, text="", bg="#f8f8f8").pack(pady=4)  # spacer

    # ── Save button — PINNED at bottom, outside scroll area ──
    bottom = tk.Frame(win, bg="#f8f8f8", pady=10)
    bottom.pack(side="bottom", fill="x")
    ttk.Separator(bottom, orient="horizontal").pack(fill="x", padx=0, pady=(0, 10))

    def save_and_close():
        keyboard.unhook(capture_hook)
        config["model"]          = model_var.get()
        config["language"]       = lang_var.get()
        config["chinese_output"] = chinese_var.get()
        config["paste_mode"]     = paste_var.get()
        config["hotkey_mode"]    = hkmode_var.get()
        config["hotkey"]         = hk_var.get().strip().lower()
        config["device"]         = device_var.get()
        config["cpu_threads"]    = cpu_var.get()
        global whisper_model
        whisper_model = None   # force reload with new thread count
        save_config(config)
        register_hotkey()
        messagebox.showinfo("Saved", "Settings saved!")
        win.destroy()

    tk.Button(bottom, text="Save Settings", command=save_and_close,
              bg="#22c55e", fg="white", font=("Arial", 11, "bold"),
              relief="flat", padx=24, pady=8, cursor="hand2").pack()

    win.mainloop()

# ── Tray ─────────────────────────────────────────────────────
def quit_app(icon, item=None):
    keyboard.unhook_all()
    icon.stop()
    os._exit(0)

def show_about():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        f"{APP_NAME} v{APP_VERSION}",
        f"{APP_NAME}  v{APP_VERSION}\n\n"
        f"Offline speech-to-text\npowered by faster-whisper\n\n"
        f"Author : {APP_AUTHOR}\n"
        f"Email  : {APP_EMAIL}"
    )
    root.destroy()

def on_tray_click(icon, item):
    """Left-click on tray icon = toggle recording"""
    threading.Thread(target=toggle_recording, daemon=True).start()

def run_ui_action(fn):
    if _IS_MAC:
        fn()
    else:
        threading.Thread(target=fn, daemon=True).start()

def build_tray():
    global tray_icon
    # Windows: set taskbar/notification app name via registry
    if _IS_WIN:
        try:
            import winreg
            app_id = "VoiceInputForWindows"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            key_path = rf"SOFTWARE\Classes\AppUserModelId\{app_id}"
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.CloseKey(key)
        except Exception:
            pass

    menu = pystray.Menu(
        pystray.MenuItem(
            "Start / Stop Recording",
            on_tray_click,
            default=True      # triggers on left-click
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Settings",
            lambda icon, item: run_ui_action(open_settings)
        ),
        pystray.MenuItem(
            f"About {APP_NAME}",
            lambda icon, item: run_ui_action(show_about)
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app)
    )
    tray_icon = pystray.Icon(
        APP_NAME,
        ICONS["idle"],
        _get_title(),
        menu
    )
    return tray_icon

# ── Main ─────────────────────────────────────────────────────
def main():
    register_hotkey()
    icon = build_tray()
    # Pre-load model in background so first keypress is instant
    threading.Thread(target=ensure_model, daemon=True).start()
    icon.run()

if __name__ == "__main__":
    main()
