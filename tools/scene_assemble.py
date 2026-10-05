"""把一場的各段配音照播放順序接成一條音軌。

輸入（都在 out/<scene>/，不入庫）：
  lines.json          tools/scene_lines.py 產生的逐句清單
  director_el.json    ElevenLabs 的分段（同一人連續的幾句合成一段），音檔 el/<block>.mp3
  idx/<line_id>.wav   IndexTTS-2 合成的幹員台詞（director_idx.json 裡帶 block_last 的，一個檔含連續幾句）
輸出：scene.mp3（單聲道 64 kbps）、cues.json（每段的起訖秒數、說話者、原文）
用法：python3 tools/scene_assemble.py act33side_st01

間隔：同一人接著說的下一句 0.8 秒（遊戲裡是另一個對話框；兩句帶感情的話緊貼著會像棒讀）；換人說話 0.6 秒；不配音的行（「……」、叫聲描述）留 1.0 秒；分段與幹員逐句都可用 gap_before 指定（換場、需要留白的告別）。
句尾：保留 0.08 秒餘音並淡出 0.06 秒，避免聲音硬生生斷掉。
音量：每段先量平均音量，統一拉到 -20 dB，峰值不超過 -1.5 dB。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SR, TARGET, PEAK = 44100, -20.0, -1.5
GAP, GAP_TURN, GAP_SILENT = 0.8, 0.6, 1.0


def measure(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mean = float(re.search(r"mean_volume: (-?[\d.]+)", err).group(1))
    peak = float(re.search(r"max_volume: (-?[\d.]+)", err).group(1))
    return mean, peak


def main(scene):
    d = ROOT / "out" / scene
    lines = json.loads((d / "lines.json").read_text(encoding="utf-8"))
    blocks = json.loads((d / "director_el.json").read_text(encoding="utf-8"))
    sid = lambda r: r["line_id"].rsplit("_", 1)[1]
    order = [sid(r) for r in lines]
    first = {b["first"]: b for b in blocks}
    idx_path = d / "director_idx.json"      # 幹員逐句的導演表，可帶 gap_before
    idx_gap = {l["line_id"]: l.get("gap_before") for l in json.loads(idx_path.read_text(encoding="utf-8"))["lines"]} if idx_path.exists() else {}
    # 幹員台詞也可以幾句共用一個音檔：第一句帶 block_last，音檔放在第一句的檔名
    blocks = blocks + [dict(block=None, first=l["line_id"].rsplit("_", 1)[1], last=l["block_last"])
                       for l in (json.loads(idx_path.read_text(encoding="utf-8"))["lines"] if idx_path.exists() else []) if l.get("block_last")]
    first = {b["first"]: b for b in blocks}
    covered = {}
    for b in blocks:
        for s in order[order.index(b["first"]):order.index(b["last"]) + 1]:
            covered[s] = b["block"]

    segs, pending_gap, missing = [], 0.0, []
    for r in lines:
        s = sid(r)
        if not r["tts"]:
            if s not in covered:        # 段落內的無聲行已由段內的停頓標記處理
                pending_gap += GAP_SILENT
            continue
        if s in covered and s not in first:
            segs[-1]["lines"].append(r)
            continue
        if s in first and first[s]["block"]:
            b = first[s]
            seg = dict(key=b["block"], path=d / "el" / f"{b['block']}.mp3", gap=b.get("gap_before"))
        else:
            seg = dict(key=s, path=d / "idx" / f"{r['line_id']}.wav", gap=idx_gap.get(r["line_id"]))
        seg.update(speaker=r["identity"], lines=[r], extra=pending_gap)
        pending_gap = 0.0
        if not seg["path"].exists():
            missing.append(seg["key"])
        segs.append(seg)
    if missing:
        sys.exit(f"缺音檔：{missing}")

    tmp = d / "_asm"
    tmp.mkdir(exist_ok=True)
    parts, cues, t, prev = [], [], 0.0, None
    for n, seg in enumerate(segs):
        gap = seg["gap"] if seg["gap"] is not None else (0.0 if prev is None else GAP_TURN if prev != seg["speaker"] else GAP)
        gap += seg["extra"]
        mean, peak = measure(seg["path"])
        gain = min(TARGET - mean, PEAK - peak)
        wav = tmp / f"{n:03d}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(seg["path"]),
                        "-af", f"silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                               f"silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.08,afade=t=in:d=0.06,areverse,"   # 倒著做：等於句尾淡出
                               f"volume={gain:.2f}dB,adelay={int(gap * 1000)}:all=1",
                        "-ar", str(SR), "-ac", "1", str(wav)], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
                                   capture_output=True, text=True).stdout)
        cues.append(dict(key=seg["key"], speaker=seg["speaker"], start=round(t + gap, 2), end=round(t + dur, 2),
                         lines=[dict(id=sid(r), shown=r["shown"], text=r["text"]) for r in seg["lines"]]))
        t += dur
        parts.append(wav)
        prev = seg["speaker"]
    (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-af", "apad=pad_dur=1", "-c:a", "libmp3lame", "-b:a", "64k", str(d / "scene.mp3")], check=True)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    (d / "cues.json").write_text(json.dumps(cues, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{scene}: {len(segs)} 段，{t / 60:.1f} 分鐘 -> {(d / 'scene.mp3').relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1])
