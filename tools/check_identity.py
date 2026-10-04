"""檢查身份表是否自洽、是否仍與劇本原文對得上。

用法：python3 tools/check_identity.py        （需要 data/ 下有劇本與 excel 表）
檢查項目：
  1. 23 場全覆蓋，每場 seq 從 1 起連續，行數與劇本重新拆出來的一致
  2. text_head、shown_as 與原文相符
  3. kind、confidence 取值合法；每行都有 identity 與 basis
  4. identity 都出現在 speakers.yaml，且 line_count 與身份表一致
  5. 沒有殘留的「？？？」或帶引號的代稱當作身份
  6. confidence: low 且要配音的行都列在 docs/identity-review.md
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "identity"))
from build import CFG, KINDS, clean
from parse import ROOT, parse_scene, scene_list

errors = []


def err(msg):
    errors.append(msg)


with (CFG / "act33side.tsv").open(encoding="utf-8", newline="") as f:
    table = list(csv.DictReader(f, delimiter="\t"))

by_scene = {}
for r in table:
    by_scene.setdefault(r["scene"], []).append(r)

scenes = scene_list()
if len(scenes) != 23:
    err(f"場次清單應有 23 場，實際 {len(scenes)}")
for s in scenes:
    name = s["scene"]
    rows = by_scene.pop(name, [])
    lines, _ = parse_scene(name)
    if not rows:
        err(f"{name}: 身份表沒有這一場")
        continue
    seqs = [int(r["seq"]) for r in rows]
    if seqs != list(range(1, len(rows) + 1)):
        err(f"{name}: seq 不是從 1 起連續")
    if len(rows) != len(lines):
        err(f"{name}: 身份表 {len(rows)} 行，劇本拆出 {len(lines)} 行")
        continue
    for r, ln in zip(rows, lines):
        where = f"{name}#{r['seq']}"
        if r["text_head"] != clean(ln["text"])[:12]:
            err(f"{where}: text_head「{r['text_head']}」與原文「{clean(ln['text'])[:12]}」不符")
        if r["shown_as"] != ln["shown_as"]:
            err(f"{where}: shown_as「{r['shown_as']}」與原文「{ln['shown_as']}」不符")
if by_scene:
    err(f"身份表有場次清單以外的場：{sorted(by_scene)}")

for r in table:
    where = f"{r['scene']}#{r['seq']}"
    if r["kind"] not in KINDS:
        err(f"{where}: kind「{r['kind']}」不合法")
    if r["confidence"] not in ("high", "low"):
        err(f"{where}: confidence「{r['confidence']}」不合法")
    if not r["identity"] or not r["basis"]:
        err(f"{where}: 缺 identity 或 basis")
    if "？？？" in r["identity"] or r["identity"].startswith("“"):
        err(f"{where}: identity「{r['identity']}」仍是假名")
    if r["kind"] == "unknown_language" and "（未知语言）" not in r["text_head"]:
        err(f"{where}: 標為 unknown_language 但原文開頭沒有「（未知语言）」")

speakers = {}
current = None
for line in (CFG / "speakers.yaml").read_text(encoding="utf-8").splitlines():
    m = re.match(r'^  "(.*)":$', line)
    if m:
        current = m.group(1).replace('\\"', '"')
        speakers[current] = None
    m = re.match(r"^    line_count: (\d+)$", line)
    if m and current:
        speakers[current] = int(m.group(1))
counts = Counter(r["identity"] for r in table)
for ident, n in counts.items():
    if ident not in speakers:
        err(f"identity「{ident}」不在 speakers.yaml")
    elif speakers[ident] != n:
        err(f"speakers.yaml 的「{ident}」line_count={speakers[ident]}，身份表實際 {n}")
for ident in speakers:
    if ident not in counts:
        err(f"speakers.yaml 的「{ident}」在身份表沒有任何行")

review = (ROOT / "docs" / "identity-review.md").read_text(encoding="utf-8")
sections = {}
for chunk in re.split(r"^## ", review, flags=re.M)[1:]:
    m = re.search(r"（場次檔：`(\w+)`）", chunk)
    listed = set()
    for a, b in re.findall(r"(\d+)(?:–(\d+))?", " ".join(re.findall(r"^- 第 ([\d–、]+) 句", chunk, flags=re.M))):
        listed.update(range(int(a), int(b or a) + 1))
    sections.setdefault(m.group(1), set()).update(listed)
low = [r for r in table if r["confidence"] == "low" and r["kind"] != "silent"]
for r in low:
    if int(r["seq"]) not in sections.get(r["scene"], set()):
        err(f"{r['scene']}#{r['seq']}: confidence 為 low 但沒有列在 identity-review.md")

kinds = Counter(r["kind"] for r in table)
print(f"場次 {len(scenes)}，行數 {len(table)}，身份 {len(counts)} 個")
print("kind：", dict(sorted(kinds.items())))
print(f"confidence low：{sum(1 for r in table if r['confidence'] == 'low')} 行（待確認清單列了 {len(low)} 行）")
if errors:
    print(f"\n發現 {len(errors)} 個問題：")
    for e in errors[:50]:
        print("  -", e)
    sys.exit(1)
print("全部通過")
