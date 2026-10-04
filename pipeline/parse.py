"""(1) 劇情腳本 → timeline.json。契約見 docs/01-architecture.md。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import jsonschema

from .common.paths import OUT_DIR, SCHEMA_DIR
from .common.settings import load_settings
from .gamedata import Scene
from .tokenizer import Token, tokenize_line

# 已知語義的指令（來源：docs/02-data-sources.md 的腳本語法與 akgcc story.js 的指令表）。
# 不在表內的指令照原樣保留並附 raw，不報錯。
KNOWN_COMMANDS = frozenset("""
    animtext background backgroundtween bgeffect blocker cameraeffect camerashake cgitem
    character characteraction charactercutin charslot curtain decision delay dialog effect
    focusin focusout gridbg hidecgitem hideitem image imagerotate imagetween imgeffect
    interlude largebg largebgtween multiline musicvolume playmusic playsound predicate
    showitem soundvolume sticker stickerclear stopmusic stopsound subtitle theater
    timersticker verticalbg video warp
""".split())

# 音訊指令中，值是音訊鍵的參數；去掉 $ 前綴（@ 開頭的直接路徑保留）
_AUDIO_KEY_ARGS = {"playmusic": ("intro", "key"), "playsound": ("key",)}

_RICH_TAG = re.compile(r"</?[A-Za-z@][^<>]*>")
_EMPTY_SPRITES = {"", "char_empty"}
_SLOT_ORDER = {"l": 0, "m": 1, "r": 2}
_POSITION_ALIASES = {"left": "l", "middle": "m", "right": "r", "none": "n"}


def _alias(v) -> str:
    v = str(v).lower()
    return _POSITION_ALIASES.get(v, v)


def split_sprite_name(name: str) -> dict:
    """`avg_npc_1305_1#8$1` → group avg_npc_1305_1, face 8, body 1。face/body 可省略。"""
    group, face, body = name, None, None
    if "$" in group:
        group, body = group.split("$", 1)
    if "#" in group:
        group, face = group.split("#", 1)
    return {"group": group, "face": _maybe_int(face), "body": _maybe_int(body)}


def _maybe_int(s: str | None):
    if s is None:
        return None
    return int(s) if s.isdigit() else s


class Stage:
    """當前台上的立繪。供選角以「說話者＋立繪」判斷身份。"""

    def __init__(self) -> None:
        self.slots: dict[str, str] = {}    # charslot 的 slot（或舊語法的 "1"/"2"）→ group
        self.cutins: dict[str, str] = {}   # charactercutin 的 widgetid → group
        self.focus: str | None = None      # 最近一次明示的 focus；None = 未指定

    def clear(self) -> None:
        self.slots.clear()
        self.focus = None

    def charslot(self, args: dict) -> None:
        slot = args.get("slot")
        if slot is None:
            # [charslot] 與只有 duration 的 [charslot(duration=1)] 都是清空
            self.clear()
            return
        slot = _alias(slot)   # 腳本裡 l 與 left、r 與 right 混用
        if "name" in args:
            group = args["group"]
            if group in _EMPTY_SPRITES:
                self.slots.pop(slot, None)
            else:
                self.slots[slot] = group
        if args.get("ato") == 0:
            # 淡出到全透明：畫面上已經看不到
            self.slots.pop(slot, None)
        if "focus" in args:
            self.focus = _alias(args["focus"])
        elif "name" in args:
            self.focus = None

    def character(self, args: dict) -> None:
        self.slots = {}
        for n, ch in enumerate(args.get("chars", []), start=1):
            if ch["group"] not in _EMPTY_SPRITES:
                self.slots[str(n)] = ch["group"]
        self.focus = str(args["focus"]) if "focus" in args else None

    def cutin(self, args: dict) -> None:
        wid = str(args.get("widgetid", ""))
        if "name" in args and args["group"] not in _EMPTY_SPRITES:
            self.cutins[wid] = args["group"]
        else:
            self.cutins.pop(wid, None)

    def on_stage(self) -> list[str]:
        slots = sorted(self.slots.items(), key=lambda kv: (_SLOT_ORDER.get(kv[0], 9), kv[0]))
        seen: list[str] = []
        for g in [g for _, g in slots] + list(self.cutins.values()):
            if g not in seen:
                seen.append(g)
        return seen

    def focus_group(self) -> str | None:
        """被打亮的那一個立繪（多半就是說話者）；無法確定時為 None。

        focus 明示 l/m/r 且該位置有人 → 該立繪；明示 n（全暗，說話者不在台上）→ None；
        未指定或 all → 台上恰好一個立繪時取它，否則 None。
        """
        if self.focus in self.slots:
            return self.slots[self.focus]
        if self.focus == "n":
            return None
        on = self.on_stage()
        return on[0] if len(on) == 1 else None


def _clean_text(text: str, nickname: str) -> str:
    return _RICH_TAG.sub("", text.replace("{@nickname}", nickname)).strip()


def _normalize_args(cmd: str, args: dict) -> dict:
    for key in _AUDIO_KEY_ARGS.get(cmd, ()):
        v = args.get(key)
        if isinstance(v, str) and v.startswith("$"):
            args[key] = v[1:]
    if cmd in ("charslot", "charactercutin") and isinstance(args.get("name"), str):
        args.update(split_sprite_name(args["name"]))
    elif cmd == "character":
        names = [args[k] for k in sorted(k for k in args if re.fullmatch(r"name\d*", k))]
        args["chars"] = [{"name": n, **split_sprite_name(n)} for n in names if isinstance(n, str)]
    elif cmd == "decision":
        for key in ("options", "values"):
            if key in args:
                args[key] = str(args[key]).split(";")
    return args


def parse_script(text: str, scene: Scene, nickname: str | None = None) -> dict:
    if nickname is None:
        nickname = load_settings()["parse"]["doctor_nickname"]
    events: list[dict] = []
    stage = Stage()
    header: dict | None = None
    n_lines = 0
    multiline_block = 0
    multiline_open = False

    def emit(ev: dict) -> None:
        events.append({"i": len(events), **ev})

    def emit_line(kind: str, speaker: str | None, raw_text: str, **extra) -> None:
        nonlocal n_lines
        n_lines += 1
        ev = {
            "cmd": "line",
            "line_id": f"{scene.scene_id}_{n_lines:04d}",
            "kind": kind,
            "speaker": speaker,
            "sprites_on_stage": stage.on_stage(),
            "focus_group": stage.focus_group(),
            "text": _clean_text(raw_text, nickname),
            "tts_text": None,
            "emotion": None,
        }
        if ev["text"] != raw_text.strip():
            ev["rich_text"] = raw_text.strip()   # 含 <color> 標籤或 {@nickname} 的原文，給渲染器
        ev.update(extra)
        emit(ev)

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        tok: Token = tokenize_line(raw_line)
        if tok.kind in ("blank", "comment"):
            continue
        if tok.kind == "text":
            emit_line("narration", None, tok.text)
            continue

        cmd = tok.cmd
        if cmd == "_unparsed":
            emit({"cmd": cmd, "args": {}, "raw": tok.raw, "error": tok.error, "src_line": lineno})
            continue
        args = _normalize_args(cmd, tok.args)

        if cmd == "header":
            header = args
        elif cmd == "name":
            multiline_open = False
            speaker = str(args.pop("name", "")) or None
            extra = {"args": args} if args else {}
            emit_line("dialogue", speaker, tok.text, **extra)
        elif cmd == "multiline":
            # 遊戲裡同一區塊的各段接續顯示在同一個對話框。各段之間常夾著立繪、
            # 震動、音效指令，合併會打亂事件順序，所以每段各自成一個 line，
            # 以 multiline.block 標出同組，end 標出該組最後一段。
            if not multiline_open:
                multiline_block += 1
                multiline_open = True
            end = bool(args.get("end", False))
            emit_line("dialogue", str(args.get("name", "")) or None, tok.text,
                      multiline={"block": multiline_block, "end": end})
            if end:
                multiline_open = False
        elif cmd == "subtitle" and "text" in args:
            text_arg = str(args.pop("text"))
            emit_line("subtitle", None, text_arg, args=args)
        else:
            if cmd == "dialog":
                multiline_open = False   # 有些區塊沒寫 end=true，靠 [dialog] 收尾
            if cmd == "charslot":
                stage.charslot(args)
            elif cmd == "character":
                stage.character(args)
            elif cmd == "charactercutin":
                stage.cutin(args)
            ev = {"cmd": cmd, "args": args}
            if cmd not in KNOWN_COMMANDS:
                ev["raw"] = tok.raw
            emit(ev)
            if tok.text:
                # 非對白指令後面跟著文字：不丟棄，當旁白
                emit_line("narration", None, tok.text)

    lines = [e for e in events if e["cmd"] == "line"]
    by_kind = {k: sum(e["kind"] == k for e in lines) for k in ("dialogue", "narration", "subtitle")}
    n_multiline = sum("multiline" in e for e in lines)
    timeline = {
        "scene_id": scene.scene_id,
        "story_code": scene.story_code,
        "story_name": scene.story_name,
        "avg_tag": scene.avg_tag,
        "source": scene.story_txt,
        "coord_system": dict(load_settings()["video"]["coord_system"]),
        "header": header,
        "stats": {
            "events": len(events),
            "lines": len(lines),
            **by_kind,
            "multiline": n_multiline,
            # docs/00-decisions.md 的統計口徑：[name=...] 行 + 非 [ 開頭的非空行
            "planning_count": by_kind["dialogue"] - n_multiline + by_kind["narration"],
        },
        "events": events,
    }
    return timeline


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    with open(SCHEMA_DIR / "timeline.schema.json", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_timeline(timeline: dict) -> None:
    errors = sorted(_validator().iter_errors(timeline), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path)
        raise ValueError(f"timeline 不符合 schema（共 {len(errors)} 處）：{where}: {e.message}")


def parse_scene(scene: Scene) -> dict:
    if not scene.path.exists():
        raise FileNotFoundError(f"找不到 {scene.path}，請先執行 python -m pipeline fetch-gamedata")
    timeline = parse_script(scene.path.read_text(encoding="utf-8"), scene)
    validate_timeline(timeline)
    return timeline


def write_timeline(timeline: dict, out_dir: Path = OUT_DIR) -> Path:
    path = out_dir / timeline["scene_id"] / "timeline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path
