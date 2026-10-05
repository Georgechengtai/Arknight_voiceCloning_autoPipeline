#!/usr/bin/env python3
"""字卡的身份表：config/identity/act33side_stickers.tsv。

用法： .venv/bin/python tools/identity/stickers.py      （需先跑過 `python -m pipeline parse`）
判定規則寫在下面的 RULES（依場次與文字），是 Claude 逐張看過上下文後定的。
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.stickers import sticker_lines  # noqa: E402

TIME = re.compile(r"^(.{1,6}年前|\d+年.{0,2}|倒计时|\d+时\d+分\d+秒|\d+分\d+秒|巴别塔离开卡兹戴尔的前夕)$")
PRTS = re.compile(r"^(内部序列开始检索|已验证|欢迎您|已进入|是否确认|已选择|Loading|倒计时已归零)")
# (場次, 文字條件) → (身份, 類別, 把握, 理由)；由上而下取第一個符合的
RULES = [
    (None, TIME.match, ("旁白", "narration", "high", "年份、地點、倒數計時的字卡")),
    ("act33side_st01", None, ("梦中的巨人", "dialogue", "high", "開場的預言詩，SA 身份表完成記錄已判定為夢中的巨人")),
    ("act33side_01_end", None, ("旁白", "narration", "high", "接續旁白「他们从魔王的双眼中看到了毁灭，看…」的句子")),
    ("act33side_03_end", None, ("旁白", "narration", "high", "旁白描寫街上人群對魔王的兩種看法")),
    ("act33side_04_end", None, ("博士", "monologue", "high", "博士「我……」說不下去之後出現的兩張字卡，是他沒說出口的念頭（專案擁有者 2026-10-05 確認）")),
    ("act33side_06_end", None, ("博士", "monologue", "high", "特蕾西娅以魔王之力看見的博士記憶，前後的字幕在身份表已判為博士")),
    ("act33side_08_end", PRTS.match, ("PRTS", "dialogue", "high", "艦船系統的提示文字")),
    ("act33side_08_end", lambda t: t.startswith(("如何评价", "有人称之为", "可这样的名号", "当短暂的和平", "听故事的孩子")),
     ("旁白", "narration", "high", "場末的旁白式議論")),
    ("act33side_08_end", None, ("博士", "monologue", "high", "字幕「看吧。」引出的一串字卡，SA 已判定為博士的回憶")),
    ("act33side_10_end", None, ("特蕾西娅", "dialogue", "high", "接在特蕾西娅「我会向所有萨卡兹宣誓……」之後，是誓詞本身")),
    ("act33side_st02", None, ("博士", "dialogue", "high", "前文明時期的博士說的話（對普瑞赛斯的回答、對凯尔希的囑咐）")),
]


def judge(scene, text):
    core = text.strip("“”\"")
    for sc, cond, verdict in RULES:
        if sc not in (None, scene):
            continue
        if cond is None or cond(core):
            return verdict
    return ("旁白", "narration", "low", "沒有對應規則，暫定旁白")


def main():
    rows = []
    for p in sorted(glob.glob(str(ROOT / "out" / "act33side_*" / "timeline.json"))):
        tl = json.load(open(p, encoding="utf-8"))
        for i, s in enumerate(sticker_lines(tl), 1):
            if s["silent"] or s["text"] == "？？？":
                v = ("", "silent", "high", "只有標點，不配音")
            else:
                v = judge(tl["scene_id"], s["text"])
            rows.append(("level_" + tl["scene_id"], i, s["line_id"], s["text"][:12], *v))
    out = ROOT / "config" / "identity" / "act33side_stickers.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write("scene\tsseq\tline_id\ttext_head\tidentity\tkind\tconfidence\tbasis\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    from collections import Counter
    print(len(rows), "張字卡 →", out.relative_to(ROOT))
    print("類別", dict(Counter(r[5] for r in rows)), "身份", dict(Counter(r[4] for r in rows if r[4])))
    print("把握低", [(r[2], r[3]) for r in rows if r[6] == "low"])


if __name__ == "__main__":
    main()
