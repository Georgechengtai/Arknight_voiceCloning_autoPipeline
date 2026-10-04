"""把 storyTxt 劇本拆成「要配音的行」：對白（name / multiline）、旁白、Subtitle。

seq 的定義與 docs/01-architecture.md 的 line_id 相同：對白＋旁白＋Subtitle 依序，從 1 起，Sticker 不算。
每行附帶台上立繪（供判斷身份），以及夾在行與行之間的字卡、選項、背景等上下文。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORY_DIR = ROOT / "data" / "story"
EXCEL_DIR = ROOT / "data" / "excel"
EVENT = "act33side"

CMD_RE = re.compile(r"^\[\s*([A-Za-z]+)\s*(?:\((.*)\))?\s*\](.*)$")
NAME_RE = re.compile(r"^\[\s*name\s*=\s*\"([^\"]*)\"[^\]]*\](.*)$", re.I)
ARG_RE = re.compile(r"(\w+)\s*=\s*(?:\"([^\"]*)\"|([^,\s\)]+))")
SILENT_RE = re.compile(r"^[\s…—\-－.。·！？!?、，,~～“”\"‘’（）()]*$")
# 整句只有一組括號且括號內沒有標點（「（愤怒的嘶吼）」「（警惕地靠近）」）：叫聲或動作描述，沒有可念的字。
# 括號內帶標點的（「（是博士……拒绝了我？还是……）」）是心裡話，不算。
STAGE_ONLY_RE = re.compile(r"^（[^（）…？！，。、—]*）$")


def scene_list():
    table = json.loads((EXCEL_DIR / "story_review_table.json").read_text(encoding="utf-8"))
    return [
        {"scene": d["storyTxt"].split("/")[-1], "code": d["storyCode"], "name": d["storyName"], "tag": d["avgTag"]}
        for d in table[EVENT]["infoUnlockDatas"]
    ]


def sprite_group(name):
    return re.split(r"[#$]", name)[0]


def auto_kind(text, named):
    if "（未知语言）" in text:
        return "unknown_language"
    if SILENT_RE.match(text) or STAGE_ONLY_RE.match(text):
        return "silent"
    return "dialogue" if named else "narration"


def parse_scene(scene):
    """回傳 (lines, events)。events 是含上下文標記的完整序列，lines 是其中要配音的行。"""
    path = STORY_DIR / EVENT / f"{scene}.txt"
    stage = {}  # slot -> sprite name
    focus = None
    events = []
    seq = 0

    def add_line(shown_as, text, src):
        nonlocal seq
        seq += 1
        on = {k: sprite_group(v) for k, v in stage.items()}
        if focus in on:
            speaker_sprite = on[focus]
        elif len(on) == 1:
            speaker_sprite = next(iter(on.values()))
        else:
            speaker_sprite = ""
        events.append({
            "type": "line", "seq": seq, "shown_as": shown_as, "text": text, "src": src,
            "stage": dict(stage), "focus": focus, "speaker_sprite": speaker_sprite,
            "auto_kind": auto_kind(text, bool(shown_as)),
        })

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = NAME_RE.match(line)
        if m:
            add_line(m.group(1), m.group(2).strip(), "name")
            continue
        if not line.startswith("["):
            add_line("", line, "narration")
            continue
        m = CMD_RE.match(line)
        if not m:
            events.append({"type": "ctx", "what": "unparsed", "text": line})
            continue
        cmd = m.group(1).lower()
        args = {k.lower(): quoted or bare for k, quoted, bare in ARG_RE.findall(m.group(2) or "")}
        tail = m.group(3).strip()
        if cmd == "multiline":
            add_line(args.get("name", ""), tail, "multiline")
        elif cmd == "subtitle":
            if args.get("text"):
                add_line("", args["text"], "subtitle")
        elif cmd == "charslot":
            if not args:
                stage.clear()
                focus = None
            else:
                slot = args.get("slot", "")[:1]
                if "name" in args and slot:
                    stage[slot] = args["name"]
                    focus = slot
                if "focus" in args:
                    focus = args["focus"][:1]
        elif cmd == "sticker":
            if args.get("text"):
                events.append({"type": "ctx", "what": "sticker", "text": args["text"]})
        elif cmd == "decision":
            events.append({"type": "ctx", "what": "decision", "text": args.get("options", "")})
        elif cmd in ("background", "image", "charactercutin"):
            val = args.get("image") or args.get("name")
            if val:
                events.append({"type": "ctx", "what": cmd, "text": val})
    return [e for e in events if e["type"] == "line"], events


def text_head(text, n=12):
    return text[:n]
