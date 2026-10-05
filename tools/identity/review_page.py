"""把 docs/identity-review.md 轉成可以直接點選作答的網頁（發佈成 Claude artifact 用）。

輸出到 data/identity_draft/identity-review.html（含劇本原文，不入庫）。
每條的白話問題與選項寫在下面的 QUESTIONS；條數或順序變了這裡要跟著改。
用法：python3 tools/identity/review_page.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import ROOT

# 每條：ask＝白話問題；options＝選項，第一個永遠是我的判斷。
QUESTIONS = [
    {"ask": "夢裡巨人念完預言的這一句，該用誰的聲音？",
     "options": ["夢中的巨人（另一位女性，不是疤眼）", "疤眼（後面他原樣重複這句）", "旁白念就好"]},
    {"ask": "「妈的。」「远见？预言？自己的死亡？」這兩句是誰的？",
     "options": ["疤眼的心裡話（用疤眼的聲音）", "旁白念就好"]},
    {"ask": "救了好运的這位「女人的声音」是誰？",
     "options": ["好运後來的妻子（孩子的媽媽「奥达」）", "另一位不知名的巴别塔女性"]},
    {"ask": "這位「失落的巴别塔成员」和下一場被殺的「巴别塔医生」是同一個人嗎？",
     "options": ["是同一個人（用同一個聲音）", "不是，兩個不同的人"]},
    {"ask": "問孩子名字、替她取名「阿斯卡纶」的人是誰？（孩子回答的那句用幼年阿斯卡纶）",
     "options": ["特蕾西娅", "特雷西斯", "旁白念就好（四句都給旁白）"]},
    {"ask": "「真不走运，今天你的生命就要到头了。」這句是誰的？",
     "options": ["好运的心裡話（用好运的聲音）", "旁白念就好"]},
    {"ask": "石棺的門鬆動時響起的這段話（8 句），該用誰的聲音？",
     "options": ["博士", "普瑞赛斯", "旁白念就好（沒有特定說話者）"]},
    {"ask": "這一聲「凯尔希……」是誰在喚她？",
     "options": ["博士（凯尔希記憶裡的聲音）", "特蕾西娅（在旁邊提醒她）", "旁白念就好"]},
    {"ask": "「去。」「我们去。」這句該怎麼配？",
     "options": ["傭兵們的群聲（幾個人的聲音）", "旁白念就好"]},
    {"ask": "黑色字的「但源石才是保护所有生命和存在的最后办法。」是誰的聲音？",
     "options": ["博士（心裡的另一個念頭）", "普瑞赛斯"]},
    {"ask": "黑色字的「这不是一种灭绝，这是一种存续。」是誰的聲音？",
     "options": ["博士（心裡的另一個念頭）", "普瑞赛斯（博士記憶裡她的話）"]},
]

md = (ROOT / "docs" / "identity-review.md").read_text(encoding="utf-8")
items = []
for chunk in re.split(r"^## ", md, flags=re.M)[1:]:
    head = chunk.splitlines()[0]
    m = re.match(r"(\d+)\. (.+?)，(第 .+)$", head)
    reasons = re.findall(r"^- (.+)$", chunk, flags=re.M)
    lines = []
    for raw in re.search(r"```\n(.*?)```", chunk, flags=re.S).group(1).splitlines():
        lm = re.match(r"^(>>|  )\s+(\d+)  (.+?)：(.*)$", raw)
        if lm:
            lines.append({"ask": lm.group(1) == ">>", "seq": int(lm.group(2)), "who": lm.group(3), "text": lm.group(4)})
        else:
            lines.append({"skip": raw.strip()})
    items.append({"n": int(m.group(1)), "where": m.group(2), "span": m.group(3), "reasons": reasons, "lines": lines})
if len(items) != len(QUESTIONS):
    sys.exit(f"清單有 {len(items)} 條，QUESTIONS 有 {len(QUESTIONS)} 條，請同步")
for item, q in zip(items, QUESTIONS):
    item.update(q)

template = (Path(__file__).parent / "review_page.template.html").read_text(encoding="utf-8")
out = ROOT / "data" / "identity_draft" / "identity-review.html"
out.write_text(template.replace("/*ITEMS*/[]", json.dumps(items, ensure_ascii=False)), encoding="utf-8")
print(out, len(items), "條")
