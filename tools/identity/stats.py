"""身份表的統計摘要（寫完成記錄用）：python3 tools/identity/stats.py"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build import CFG

with (CFG / "act33side.tsv").open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))
voiced = [r for r in rows if r["kind"] in ("dialogue", "narration", "monologue")]
print("總行數", len(rows), "要配音", len(voiced))
print("kind", dict(Counter(r["kind"] for r in rows)))
print("「？？？」→", Counter(r["identity"] for r in rows if r["shown_as"] == "？？？").most_common())
unnamed = [r for r in rows if not r["shown_as"]]
print("無名行", len(unnamed), "→ 非旁白", Counter(r["identity"] for r in unnamed if r["identity"] != "旁白").most_common())
print("無名行 kind", dict(Counter(r["kind"] for r in unnamed)))

roles, ops, same = {}, {}, {}
cur = None
for line in (CFG / "speakers.yaml").read_text(encoding="utf-8").splitlines():
    m = re.match(r'^  "(.*)":$', line)
    if m:
        cur = m.group(1)
    m = re.match(r"^    role: (\w+)$", line)
    if m:
        roles[cur] = m.group(1)
    if line.startswith("    operator_char_id:"):
        ops[cur] = line.split(": ")[1]
    if line.startswith("    same_person_as:"):
        same[cur] = line.split(": ")[1].strip('"')
print("role 身份數", dict(Counter(roles.values())))
print("role 配音行數", dict(Counter(roles[r["identity"]] for r in voiced)))
print("幹員本人（可直接用原聲）", sum(1 for r in voiced if r["identity"] in ops),
      Counter(r["identity"] for r in voiced if r["identity"] in ops).most_common())
print("幹員的變體", Counter(r["identity"] for r in voiced if same.get(r["identity"]) in ops).most_common())
print("npc_major", Counter(r["identity"] for r in voiced if roles[r["identity"]] == "npc_major").most_common())
