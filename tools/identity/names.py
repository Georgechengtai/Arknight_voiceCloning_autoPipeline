"""列出每個顯示名在各場的行數與台上立繪，用來決定哪些通用名要按場次區分。"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import parse_scene, scene_list

d = defaultdict(lambda: defaultdict(Counter))
for s in scene_list():
    for line in parse_scene(s["scene"])[0]:
        if line["shown_as"]:
            d[line["shown_as"]][s["scene"].replace("level_act33side_", "")][line["speaker_sprite"] or "-"] += 1
for name, scenes in sorted(d.items(), key=lambda kv: -sum(sum(c.values()) for c in kv[1].values())):
    total = sum(sum(c.values()) for c in scenes.values())
    print(total, name, {k: dict(v) for k, v in scenes.items()})
