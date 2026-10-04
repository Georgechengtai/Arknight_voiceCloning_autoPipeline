"""產出供人工通讀的初稿：data/identity_draft/<scene>.txt（不入庫）。"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import ROOT, parse_scene, scene_list, sprite_group

OUT = ROOT / "data" / "identity_draft"
OUT.mkdir(parents=True, exist_ok=True)

pairs = defaultdict(Counter)
kinds = Counter()
for s in scene_list():
    lines, events = parse_scene(s["scene"])
    buf = [f"# {s['scene']}  {s['code']} {s['name']}（{s['tag']}） lines={len(lines)}"]
    last_stage = None
    for e in events:
        if e["type"] == "ctx":
            buf.append(f"      <{e['what']}> {e['text']}")
            continue
        stage = ",".join(f"{k}={sprite_group(v)}" for k, v in sorted(e["stage"].items()))
        key = (stage, e["focus"])
        if key != last_stage:
            buf.append(f"      @ {stage or '（空台）'} focus={e['focus']}")
            last_stage = key
        tag = {"subtitle": "[SUB]", "multiline": "[ML]"}.get(e["src"], "")
        buf.append(f"{e['seq']:04d} {tag}{e['shown_as'] or '∅'}｜{e['text']}")
        pairs[e["shown_as"]][e["speaker_sprite"]] += 1
        kinds[e["auto_kind"]] += 1
    (OUT / f"{s['scene']}.txt").write_text("\n".join(buf) + "\n", encoding="utf-8")

with (OUT / "_names.txt").open("w", encoding="utf-8") as f:
    for name, c in sorted(pairs.items(), key=lambda kv: -sum(kv[1].values())):
        f.write(f"{sum(c.values()):5d} {name or '∅'}  " + "  ".join(f"{k or '-'}:{v}" for k, v in c.most_common()) + "\n")
print(dict(kinds), sum(kinds.values()))
