"""把一場的 timeline、身份表、字卡表併成照播放順序的逐句清單。

輸出 out/<scene_id>/lines.json（不入庫）：order（事件序）、line_id、shown、identity、kind、text、tts。
用法：python3 tools/scene_lines.py act33side_st01
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.stickers import sticker_lines
from pipeline.tts_text import spoken_text

VOICED = {"dialogue", "narration", "monologue"}


def read_tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader((l for l in f if not l.startswith("#")), delimiter="\t"))


def build(scene_id):
    timeline = json.loads((ROOT / "out" / scene_id / "timeline.json").read_text(encoding="utf-8"))
    level = "level_" + scene_id
    ident = {int(r["seq"]): r for r in read_tsv(ROOT / "config/identity/act33side.tsv") if r["scene"] == level}
    cards = {r["line_id"]: r for r in read_tsv(ROOT / "config/identity/act33side_stickers.tsv") if r["scene"] == level}
    rows = []
    for ev in timeline["events"]:
        if ev.get("cmd") != "line":
            continue
        r = ident[int(ev["line_id"].rsplit("_", 1)[1])]
        if not ev["text"].startswith(r["text_head"]):
            sys.exit(f"{ev['line_id']}: 身份表與 timeline 文字對不上")
        rows.append({"order": ev["i"], "line_id": ev["line_id"], "shown": ev["speaker"] or "",
                     "identity": r["identity"], "kind": r["kind"], "text": ev["text"]})
    for s in sticker_lines(timeline):
        r = cards[s["line_id"]]
        rows.append({"order": s["i"], "line_id": s["line_id"], "shown": "", "identity": r["identity"],
                     "kind": r["kind"], "text": s["text"]})
    rows.sort(key=lambda x: x["order"])
    for r in rows:
        r["tts"] = spoken_text(r["text"]) if r["kind"] in VOICED else None
    return rows


if __name__ == "__main__":
    scene = sys.argv[1]
    rows = build(scene)
    out = ROOT / "out" / scene / "lines.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    voiced = [r for r in rows if r["tts"]]
    print(f"{scene}: {len(rows)} 行，要配音 {len(voiced)} 行 -> {out.relative_to(ROOT)}")
