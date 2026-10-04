"""(3) 選角用的說話者統計。本檔目前只有 speakers.csv；選角表骨架與參考音挑選由後續 session 加。"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

NARRATOR_LABEL = "（旁白）"
SUBTITLE_LABEL = "（字幕）"
FIELDS = ["speaker", "sprite_group", "focus_group", "line_count", "scenes", "sample_lines"]


def _label(line: dict) -> str:
    if line["speaker"]:
        return line["speaker"]
    return SUBTITLE_LABEL if line["kind"] == "subtitle" else NARRATOR_LABEL


def _by_freq(counter: Counter) -> str:
    return "|".join(k for k, _ in counter.most_common())


def collect_speakers(timelines: list[dict]) -> list[dict]:
    """每個說話者一列。sprite_group = 他說話時台上出現過的所有立繪組；
    focus_group = 其中被打亮的（判斷身份最可靠的線索）。兩欄都依出現次數由多到少排。"""
    stats: dict[str, dict] = {}
    for tl in timelines:
        for ev in tl["events"]:
            if ev["cmd"] != "line":
                continue
            s = stats.setdefault(_label(ev), {
                "count": 0, "sprites": Counter(), "focus": Counter(), "scenes": [], "samples": [],
            })
            s["count"] += 1
            s["sprites"].update(ev["sprites_on_stage"])
            if ev["focus_group"]:
                s["focus"][ev["focus_group"]] += 1
            if tl["story_code"] not in s["scenes"]:
                s["scenes"].append(tl["story_code"])
            if len(s["samples"]) < 3 and ev["text"] not in s["samples"]:
                s["samples"].append(ev["text"])
    rows = [
        {
            "speaker": name,
            "sprite_group": _by_freq(s["sprites"]),
            "focus_group": _by_freq(s["focus"]),
            "line_count": s["count"],
            "scenes": "|".join(s["scenes"]),
            "sample_lines": " / ".join(s["samples"]),
        }
        for name, s in stats.items()
    ]
    rows.sort(key=lambda r: (-r["line_count"], r["speaker"]))
    return rows


def write_speakers_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：Excel 直接開啟中文不亂碼
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path
