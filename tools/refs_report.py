"""把 config/refs/*.json（各角色的參考音摘要）彙整成一張 Markdown 表，供貼進 cluster/ENV.md。

用法： python3 tools/refs_report.py
"""
import glob
import json
import os

ORDER = [l.split("\t")[0] for l in open(os.path.join(os.path.dirname(__file__), "../cluster/ref_chars.tsv"), encoding="utf-8")
         if l.strip() and not l.startswith("#")]
EMOS = ["中立", "生气", "难过", "开心", "吃惊", "恐惧", "厌恶", "其他", "<unk>"]
data = {}
for p in glob.glob(os.path.join(os.path.dirname(__file__), "../config/refs/*.json")):
    d = json.load(open(p, encoding="utf-8"))
    data[d["char"]["key"]] = d

print("| 角色 | 短名 | 語音句數（短／中／長） | 參考音段數 | 可用（原句／切片／拼接） | 音高中位數 Hz | 語速 字/秒 | "
      + " | ".join(EMOS[:7]) + " | 音高明顯偏高的段數 |")
print("|" + "---|" * 16)
for k in ORDER:
    if k not in data:
        print(f"| （未產出） | {k} |" + " |" * 14)
        continue
    d = data[k]
    s, e = d["stats"], d["stats"]["usable_by_emotion"]
    u = s["usable_by_kind"]
    print(f"| {d['char']['name']} | {k} | {s['n_clips']}（{s['clips_short']}／{s['clips_mid']}／{s['clips_long']}） | {s['n_refs']} | "
          f"**{s['n_usable']}**（{u['原句']}／{u['切片']}／{u['拼接']}） | {d['median']['f0_median']} | {d['median']['rate']} | "
          + " | ".join(str(e.get(x, 0)) for x in EMOS[:7]) + f" | {s['usable_raised_pitch']} |")
print()
for k in ORDER:
    if k in data:
        d = data[k]
        e = d["stats"]["usable_by_emotion"]
        missing = [x for x in EMOS[:7] if not e.get(x)]
        bad = [f"{r['id']}（{r['unusable_why']}）" for r in d["refs"] if not r["usable"]]
        print(f"- **{d['char']['name']}**：情緒模型沒有任何一段歸到「{'、'.join(missing)}」。"
              f"切片對齊：逐字時間戳 {d['stats']['slices_by_align']['逐字時間戳']} 段、字數比例 {d['stats']['slices_by_align']['字數比例']} 段。"
              + (f"不可用 {len(bad)} 段：{'；'.join(bad)}。" if bad else "沒有不可用的段。")
              + (f"備註：{'；'.join(d['notes'])}" if d["notes"] else ""))
