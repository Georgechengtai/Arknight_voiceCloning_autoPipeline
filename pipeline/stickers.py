"""字卡（Sticker）裡要配音的文字。

原設計（D7）字卡只顯示不念；專案擁有者 2026-10-05 改為：除了圖片內自帶的文字，
劇情的所有字幕都要配音，包括演出中途的字卡。

timeline 的事件與 line_id 不變（身份表以它為鍵）。字卡另用一套編號：
`<scene_id>_s<3 位序號>`，序號是該場「有文字的 sticker 事件」的出現順序。
"""
from __future__ import annotations

import re

_RICH_TAG = re.compile(r"<[^>]+>")
_SPEAKABLE = re.compile(r"[一-鿿A-Za-z0-9]")


def clean_sticker_text(raw: str, nickname: str) -> str:
    text = _RICH_TAG.sub("", str(raw)).replace("{@nickname}", nickname)
    text = text.replace("\\n", "\n")
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def sticker_lines(timeline: dict, nickname: str = "博士") -> list[dict]:
    """列出一場裡所有帶文字的字卡。`silent` 為 True 的只有標點（如「……」），不配音。"""
    out: list[dict] = []
    for ev in timeline["events"]:
        if ev.get("cmd") != "sticker":
            continue
        text = clean_sticker_text(ev.get("args", {}).get("text") or "", nickname)
        if not text:
            continue
        out.append({
            "line_id": f"{timeline['scene_id']}_s{len(out) + 1:03d}",
            "i": ev["i"],
            "sticker_id": ev.get("args", {}).get("id"),
            "text": text,
            "silent": not _SPEAKABLE.search(text),
        })
    return out
