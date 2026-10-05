"""(5c) 音軌：語音、背景音樂、音效各自成檔，再混成有音樂與無音樂兩個版本。

語音音檔已經統一過音量（docs/01-architecture.md「追加 2026-10-05」），這裡只擺位置，不再調整。
"""
from __future__ import annotations

import subprocess
import wave
from array import array
from pathlib import Path


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失敗：{r.stderr.strip()[-600:]}")


def _silence(path: Path, total: float, sr: int, channels: int = 2) -> None:
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={'stereo' if channels == 2 else 'mono'}",
          "-t", f"{total:.3f}", "-c:a", "pcm_s16le", str(path)])


def render_voice(schedule: dict, root: Path, out: Path, sr: int) -> dict:
    """照時間表把每句語音放到它開口的時刻。單聲道 16 位元。"""
    total = int(round(schedule["duration"] * sr))
    buf = array("h", bytes(total * 2))
    placed, missing = 0, []
    for v in schedule["audio"]["voice"]:
        src = root / v["path"]
        if not src.exists():
            missing.append(v["path"])
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                             capture_output=True, check=True).stdout
        samples = array("h", raw[: len(raw) // 2 * 2])
        start = int(round(v["t"] * sr))
        samples = samples[: max(0, total - start)]
        buf[start:start + len(samples)] = samples
        placed += 1
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())
    return {"placed": placed, "missing": missing}


def _mix(inputs: list[str], chains: list[str], labels: list[str], out: Path, total: float, sr: int,
         post: list[str] | None = None) -> None:
    graph = ";".join(chains)
    if len(labels) > 1:
        graph += f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[m]"
        last = "[m]"
    else:
        last = labels[0]
    graph += f";{last}{','.join(['apad', f'atrim=0:{total:.3f}'] + (post or []))}[out]"
    _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
          "-ar", str(sr), "-ac", "2", "-c:a", "pcm_s16le", str(out)])


def _fmt(sr: int) -> str:
    return f"aformat=sample_fmts=fltp:sample_rates={sr}:channel_layouts=stereo"


def speech_spans(schedule: dict, bridge: float) -> list[list[float]]:
    """有人說話的時段；相隔不到 bridge 秒的併成一段（免得音樂在句與句之間忽大忽小）。"""
    spans: list[list[float]] = []
    for v in sorted(schedule["audio"]["voice"], key=lambda v: v["t"]):
        if spans and v["t"] - spans[-1][1] < bridge:
            spans[-1][1] = max(spans[-1][1], v["t"] + v["dur"])
        else:
            spans.append([v["t"], v["t"] + v["dur"]])
    return spans


def duck_filters(spans: list[list[float]], duck_db: float, attack: float, release: float, chunk: int = 12) -> list[str]:
    """說話時把音量降 duck_db：開口前 attack 秒開始退、說完後 release 秒內回來。

    每一段是一個梯形（0→1→0），各段不重疊所以直接相加；分成幾個 volume 濾鏡串接，免得單一運算式太長。
    """
    if not spans or duck_db <= 0:
        return []
    out = []
    for k in range(0, len(spans), chunk):
        terms = "+".join(f"clip(min((t-{a - attack:.3f})/{attack:.3f},({b + release:.3f}-t)/{release:.3f}),0,1)"
                         for a, b in spans[k:k + chunk])
        out.append(f"volume=eval=frame:volume='pow(10,{-duck_db / 20:.4f}*({terms}))'")
    return out


def render_bgm(schedule: dict, root: Path, out: Path, sr: int, gain_db: float = 0.0, duck: dict | None = None) -> dict:
    """每段音樂：前奏播一次，接循環段一直重複，到 stopmusic 淡出。

    gain_db 與「有人說話時退後」都直接做進輸出檔，所以 bgm.wav 就是成品裡實際的音樂音量。
    """
    total = schedule["duration"]
    inputs, chains, labels, skipped = [], [], [], []
    n = 0
    for k, m in enumerate(schedule["audio"]["music"]):
        if not m["loop_path"] or not (root / m["loop_path"]).exists():
            skipped.append(m["loop"])
            continue
        end = min(m["t1"] if m["t1"] is not None else total, total)
        dur = end - m["t0"]
        if dur <= 0:
            continue
        parts = []
        if m["intro_path"] and (root / m["intro_path"]).exists():
            inputs += ["-i", str(root / m["intro_path"])]
            chains.append(f"[{n}:a]{_fmt(sr)}[i{k}]")
            parts.append(f"[i{k}]")
            n += 1
        inputs += ["-stream_loop", "-1", "-i", str(root / m["loop_path"])]
        chains.append(f"[{n}:a]{_fmt(sr)}[l{k}]")
        parts.append(f"[l{k}]")
        n += 1
        fade = min(m["fade_out"], dur)
        chain = f"{''.join(parts)}concat=n={len(parts)}:v=0:a=1,atrim=0:{dur:.3f},volume={m['volume']}"
        if fade > 0:
            chain += f",afade=t=out:st={dur - fade:.3f}:d={fade:.3f}"
        chain += f",adelay={int(round(m['t0'] * 1000))}:all=1[m{k}]"
        chains.append(chain)
        labels.append(f"[m{k}]")
    post = [f"volume={gain_db}dB"]
    spans = []
    if duck and duck.get("duck_db", 0) > 0:
        attack, release = float(duck["attack_s"]), float(duck["release_s"])
        spans = speech_spans(schedule, max(float(duck["bridge_s"]), attack + release))
        post += duck_filters(spans, float(duck["duck_db"]), attack, release)
    if not labels:
        _silence(out, total, sr)
    else:
        _mix(inputs, chains, labels, out, total, sr, post)
    return {"segments": len(labels), "skipped": skipped, "ducked_spans": len(spans)}


def _envelope(points: list[list[float]], t0: float) -> str:
    """音量折線（絕對時間）→ ffmpeg 的 volume 運算式（以該音效開始為 0）。"""
    pts = [[max(0.0, p[0] - t0), p[1]] for p in points]
    expr = f"{pts[-1][1]}"
    for (ta, va), (tb, vb) in reversed(list(zip(pts, pts[1:]))):
        if tb <= ta:
            continue
        expr = f"if(lt(t,{tb:.3f}),{va}+({vb}-{va})*(t-{ta:.3f})/{tb - ta:.3f},{expr})"
    return expr


def render_sfx(schedule: dict, root: Path, out: Path, sr: int, gain_db: float = 0.0) -> dict:
    total = schedule["duration"]
    inputs, chains, labels, skipped = [], [], [], []
    n = 0
    for k, s in enumerate(schedule["audio"]["sounds"]):
        if not s["path"] or not (root / s["path"]).exists():
            skipped.append(s["key"])
            continue
        if s["t0"] >= total:
            continue
        inputs += (["-stream_loop", "-1"] if s["loop"] else []) + ["-i", str(root / s["path"])]
        chain = f"[{n}:a]{_fmt(sr)}"
        n += 1
        end = min(s["t1"], total) if s["t1"] is not None else None
        if end is not None and (s["loop"] or s["channel"]):
            chain += f",atrim=0:{max(0.01, end - s['t0']):.3f}"
        if len(s["vol"]) > 1:
            chain += f",volume=eval=frame:volume='{_envelope(s['vol'], s['t0'])}'"
        else:
            chain += f",volume={s['vol'][0][1]}"
        chain += f",adelay={int(round(s['t0'] * 1000))}:all=1[s{k}]"
        chains.append(chain)
        labels.append(f"[s{k}]")
    if not labels:
        _silence(out, total, sr)
    else:
        _mix(inputs, chains, labels, out, total, sr, [f"volume={gain_db}dB"])
    return {"sounds": len(labels), "skipped": skipped}


def mix_final(voice: Path, sfx: Path, bgm: Path | None, out: Path, sr: int) -> None:
    """語音＋音效（＋音樂）→ 一條立體聲音軌。三軌的音量都已各自做好，這裡只相加；
    最後過一道限幅，只擋爆音，不改變整體音量。"""
    tracks = [voice, sfx] + ([bgm] if bgm else [])
    inputs, chains, labels = [], [], []
    for n, path in enumerate(tracks):
        inputs += ["-i", str(path)]
        chains.append(f"[{n}:a]{_fmt(sr)}[t{n}]")
        labels.append(f"[t{n}]")
    graph = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[out]"
    _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
          "-ar", str(sr), "-c:a", "pcm_s16le", str(out)])


def loudness(path: Path, spans: list[list[float]] | None = None) -> float | None:
    """整合響度（LUFS）。給了 spans 就只量那些時段（例如只量有人說話的時候）。"""
    af = "ebur128"
    if spans:
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in spans)
        af = f"aselect='{sel}',asetpts=N/SR/TB,ebur128"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", af, "-f", "null", "-"],
                       capture_output=True, text=True)
    import re
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else None


def mux(video: Path, audio: Path, out: Path, bitrate: str) -> None:
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart", str(out)])
