"""語音清單還沒出來時用的佔位清單。格式與正式的 voice_manifest.json 相同，換檔就能用。

每句用 macOS 的 `say` 念出來（沒有 `say` 就用同樣長度的靜音），只為了有長度可排時間、有聲音可對字幕。
佔位音檔不是配音成品，不入庫，也不要寫到正式清單的位置。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

SR = 44100
SECONDS_PER_CHAR = 0.22     # 靜音佔位：每字的長度
MIN_SECONDS = 0.6


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _write_silence(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(int(seconds * SR) * 2))


def _say(text: str, path: Path, voice: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "a.aiff"
        r = subprocess.run(["say", "-v", voice, "-o", str(aiff), text], capture_output=True)
        if r.returncode != 0 or not aiff.exists():
            return False
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(aiff), "-ar", str(SR), "-ac", "1",
                            "-c:a", "pcm_s16le", str(path)], capture_output=True)
        return r.returncode == 0


def build_placeholder(lines: list[dict], scene_id: str, out_dir: Path, *, use_say: bool = True,
                      voice: str = "Tingting") -> dict:
    """lines：tools/scene_lines.py 的逐句清單（lines.json）。回傳清單並寫到 out_dir/voice_manifest.json。"""
    (out_dir / "voice").mkdir(parents=True, exist_ok=True)
    use_say = use_say and shutil.which("say") is not None and shutil.which("ffmpeg") is not None
    items = []
    for r in lines:
        item = {"line_id": r["line_id"], "speaker": r.get("identity") or "", "engine": None,
                "path": None, "dur": 0, "gap_before": None}
        if r.get("tts"):
            rel = f"voice/{r['line_id']}.wav"
            wav = out_dir / rel
            if not (use_say and _say(r["tts"], wav, voice)):
                _write_silence(wav, max(MIN_SECONDS, len(r["tts"]) * SECONDS_PER_CHAR))
            item.update(engine="placeholder", path=rel, dur=round(_duration(wav), 3))
        items.append(item)
    manifest = {"scene": scene_id, "sample_rate": SR, "placeholder": True, "lines": items}
    (out_dir / "voice_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest
