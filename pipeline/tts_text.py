"""把顯示用的台詞轉成送去合成的文字。讀音規則都放這裡。"""
from __future__ import annotations

import re


# 畫面寫法 → 念法。Mon3tr 在凯尔希的原聲裡念作 Monster。
READINGS = {"Mon3tr": "Monster"}


def normalize_nickname(text: str, nickname: str = "博士") -> str:
    """Normalize only the placeholder and the explicitly configured display name."""
    names = [r"\{@nickname\}", re.escape(nickname)]
    if nickname != "博士":
        names.append("博士")
    token = "(?:" + "|".join(names) + ")"
    return re.sub(r"(?:(?i:Dr)\.\s*)?" + token + r"(?:博士)?", "博士", text)


def spoken_text(text: str, nickname: str = "博士") -> str:
    """`Dr.{@nickname}` 整個念成暱稱（專案擁有者 2026-10-05 決定），畫面上的字不變。"""
    text = normalize_nickname(text, nickname)
    for shown, said in READINGS.items():
        text = text.replace(shown, said)
    return text
