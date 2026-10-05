"""(5a) timeline + 語音清單 + 素材清單 → 絕對時間表 schedule.json。

渲染器與混音都只讀這份時間表，不自己算節奏。純函式，不碰檔案系統。
節奏規則見 docs/01-architecture.md「追加 2026-10-05」與本 session 追加的一節。
"""
from __future__ import annotations

import re

from ..stickers import sticker_lines

_SLOT_ALIASES = {"left": "l", "middle": "m", "right": "r", "none": "n", "a": "all"}
_SLOTS = ("l", "m", "r")
_EMPTY_SPRITES = {"", "char_empty"}
_RICH_TAG = re.compile(r"</?[A-Za-z@][^<>]*>")
# 只做近似、沒有照遊戲精確還原的指令
_APPROX = {"camerashake", "backgroundtween", "imagetween"}
# 已處理（或刻意不處理）的指令；其餘出現時記進 warnings
_HANDLED = {"line", "delay", "blocker", "dialog", "subtitle", "sticker", "stickerclear", "charslot",
            "background", "image", "backgroundtween", "imagetween", "camerashake",
            "playmusic", "stopmusic", "playsound", "stopsound", "soundvolume", "musicvolume", "header"}


def _alias(v) -> str:
    v = str(v).lower()
    return _SLOT_ALIASES.get(v, v)


def _xy(v, default=(0.0, 0.0)) -> list[float]:
    """`"200,0"` → [200.0, 0.0]"""
    if v is None:
        return list(default)
    if isinstance(v, (int, float)):
        return [float(v), 0.0]
    parts = [p.strip() for p in str(v).split(",")]
    return [float(parts[0] or 0), float(parts[1] or 0) if len(parts) > 1 else 0.0]


def display_text(raw: str, nickname: str) -> str:
    """字卡顯示用的文字：去掉標籤、代入暱稱、保留換行。"""
    text = _RICH_TAG.sub("", str(raw)).replace("{@nickname}", nickname)
    return "\n".join(p.strip() for p in text.replace("\\n", "\n").splitlines() if p.strip())


def line_gaps(disp: list[dict], between: list[float], cfg: dict) -> list[float]:
    """每個「要顯示文字的行」說完之後，畫面再停多久才往下走。

    disp[k]：{voiced, speaker, gap_before}；between[k]：第 k−1 行結束到第 k 行之間，
    腳本自己佔掉的時間（Delay、會等待的 Blocker、前一行不配音時的停留）。
    回傳 post[k]：第 k 行結束後的停留。開口前的間隔因此落在「上一句的字還留在畫面上」的時候，
    下一句的字與聲音同時出現。
    """
    same, turn, hold = cfg["same_speaker_s"], cfg["turn_s"], cfg["min_hold_after_line_s"]
    absorb = cfg.get("absorb_script_time", True)
    post = [0.0] * len(disp)
    prev_speaker = None
    for k, d in enumerate(disp):
        if d["gap_before"] is not None:
            gap = float(d["gap_before"])
        elif k == 0:
            gap = 0.0
        else:
            gap = same if d["speaker"] and d["speaker"] == prev_speaker else turn
        d["gap"] = gap
        if k > 0:
            s = between[k]
            if not absorb:
                post[k - 1] = gap
            elif s <= 0:
                post[k - 1] = gap
            elif disp[k - 1]["voiced"]:
                post[k - 1] = max(hold, gap - s)
            else:
                post[k - 1] = max(0.0, gap - s)
        if d["voiced"]:
            prev_speaker = d["speaker"]
    if disp:
        post[-1] = hold
    return post


class _Stage:
    """台上的立繪。每個「實例」是同一個立繪組在同一個位置連續停留的一段。"""

    def __init__(self, sprites: dict, cfg: dict, coord_h: float, warn) -> None:
        self.assets = sprites
        self.cfg = cfg
        self.h = coord_h
        self.warn = warn
        self.slots: dict[str, dict] = {}
        self.done: list[dict] = []
        self.focus: list[tuple[float, str | None]] = [(0.0, None)]

    def _src(self, name: str, group: str, face, body) -> str | None:
        entry = self.assets.get(group) or self.assets.get(group + "_1")
        if not entry or not entry.get("variants"):
            self.warn(f"缺素材（立繪）：{name}，以佔位顯示")
            return None
        variants = entry.get("variants") or {}
        for key in (name, f"{group}#{face or 1}${body or 1}", f"{group}#{face or 1}", group):
            if key in variants:
                return variants[key].get("path")
        self.warn(f"立繪 {name} 沒有對應的變體，改用同組第一張")
        return next(iter(variants.values())).get("path")

    def _new(self, t: float, slot: str, args: dict, fade_in: float) -> dict:
        group = args["group"]
        entry = self.assets.get(group) or self.assets.get(group + "_1") or {}
        pos = entry.get("pos") or self.cfg["default_pos"]
        size = (entry.get("size") or {}).get("y") or self.cfg["default_size"]
        return {
            "slot": slot, "group": group,
            "x": self.cfg["slot_x"][slot] + float(pos.get("x", 0)),
            "cy": self.h - float(pos.get("y", 0)),      # pos.y：圖片中心離畫面底邊的高度
            "size": float(size),
            "t0": t, "t1": None, "fade_in": fade_in, "fade_out": 0.0,
            "images": [], "moves": [], "alphas": [], "shakes": [],
        }

    def _close(self, slot: str, t: float, fade: float = 0.0) -> None:
        inst = self.slots.pop(slot, None)
        if inst:
            inst["t1"], inst["fade_out"] = t + fade, fade
            self.done.append(inst)

    def charslot(self, t: float, args: dict) -> None:
        dur = float(args.get("duration", 0) or 0)
        if "slot" not in args:
            # [charslot] 與只有 duration 的 [charslot(duration=1)] 都是清空（後者淡出）
            for slot in list(self.slots):
                self._close(slot, t, dur)
            self.focus.append((t, None))
            return
        slot = _alias(args["slot"])
        if slot not in _SLOTS:
            self.warn(f"charslot 的位置 {args['slot']!r} 不認得，略過")
            return
        if "name" in args:
            group = args.get("group", "")
            cur = self.slots.get(slot)
            if group in _EMPTY_SPRITES:
                self._close(slot, t)
            else:
                if not (cur and cur["group"] == group):
                    self._close(slot, t)
                    for other, inst in list(self.slots.items()):
                        if inst["group"] == group:
                            self._close(other, t)
                    fade = dur if "duration" in args else self.cfg["sprite_default_fade_s"]
                    cur = self.slots[slot] = self._new(t, slot, args, fade)
                cur["images"].append({"t": t, "name": args["name"],
                                      "src": self._src(args["name"], group, args.get("face"), args.get("body"))})
        inst = self.slots.get(slot)
        if inst:
            if "posfrom" in args or "posto" in args:
                last = inst["moves"][-1]["to"] if inst["moves"] else [0.0, 0.0]
                to = _xy(args.get("posto"), last)
                if "posfrom" not in args:       # 只寫 posto：從目前位置再移動這麼多
                    to = [last[0] + to[0], last[1] + to[1]]
                inst["moves"].append({"t": t, "dur": dur, "from": _xy(args.get("posfrom"), last), "to": to})
            if "afrom" in args or "ato" in args:
                a_to = float(args.get("ato", 1))
                inst["alphas"].append({"t": t, "dur": dur, "from": float(args.get("afrom", 1)), "to": a_to})
                if a_to == 0:
                    self._close(slot, t + dur)
            if args.get("action") == "shake":
                inst["shakes"].append({"t": t, "dur": dur, "power": float(args.get("power", 10)),
                                       "times": float(args.get("times", 10))})
        if "focus" in args:
            self.focus.append((t, _alias(args["focus"])))
        elif "name" in args:
            self.focus.append((t, slot))    # 換上新立繪而沒寫 focus：亮的是這個位置（PRTS 播放器同此）

    def finish(self, t_end: float) -> list[dict]:
        for slot in list(self.slots):
            self._close(slot, t_end)
        out = sorted(self.done, key=lambda s: (s["t0"], _SLOTS.index(s["slot"])))
        for inst in out:
            # 打亮／壓暗：清空後或 all → 全亮；指定位置 → 只有該位置亮；n → 全暗
            lit: list[list] = []
            for t, f in self.focus:
                on = f in (None, "all") or f == inst["slot"]
                if t <= inst["t0"]:
                    lit = [[inst["t0"], on]]
                elif t < inst["t1"] - inst["fade_out"] and lit[-1][1] != on:   # 淡出途中不再變亮暗
                    lit.append([t, on])
            inst["lit"] = lit
        return out


def build_schedule(timeline: dict, voice: dict, assets: dict | None, settings: dict, *,
                   voice_dir: str = "", intro_card: bool = False) -> dict:
    """把事件序列排成絕對時間。`voice_dir`：語音清單裡的相對路徑要接在哪個目錄後面。"""
    cfg = settings["render"]
    gaps_cfg = cfg["gaps"]
    video = settings["video"]
    nickname = settings["parse"]["doctor_nickname"]
    default_fade = settings["pacing"]["blocker_default_fadetime_s"]
    assets = assets or {}
    coord = timeline.get("coord_system") or video["coord_system"]
    events = timeline["events"]
    warnings: list[str] = []
    warn = lambda m: warnings.append(m) if m not in warnings else None  # noqa: E731

    def asset_path(kind: str, key: str | None) -> str | None:
        if not key:
            return None
        table = assets.get(kind) or {}
        for k in (key, "bg_" + key):
            if k in table and table[k].get("path"):
                return table[k]["path"]
        warn(f"缺素材（{kind}）：{key}，以佔位顯示或靜音")
        return None

    # ── 一、哪些事件是「要顯示文字的行」，各自的語音 ──
    stickers = {s["i"]: s for s in sticker_lines(timeline, nickname)}
    vmap = {l["line_id"]: l for l in voice["lines"]}
    disp: list[dict] = []
    disp_at: dict[int, dict] = {}
    for ev in events:
        if ev["cmd"] == "line":
            lid = ev["line_id"]
        elif ev["i"] in stickers:
            lid = stickers[ev["i"]]["line_id"]
        else:
            continue
        v = vmap.get(lid)
        if v is None:
            warn(f"語音清單沒有 {lid}，當作不配音")
            v = {}
        voiced = bool(v.get("path")) and float(v.get("dur") or 0) > 0
        d = {"i": ev["i"], "line_id": lid, "voiced": voiced, "dur": float(v.get("dur") or 0) if voiced else 0.0,
             "speaker": v.get("speaker") or "", "gap_before": v.get("gap_before"),
             "path": (f"{voice_dir.rstrip('/')}/{v['path']}" if voice_dir else v["path"]) if voiced else None}
        disp.append(d)
        disp_at[ev["i"]] = d

    def blocking(ev: dict) -> float:
        a = ev.get("args") or {}
        if ev["cmd"] == "delay":
            return float(a.get("time", 0) or 0)
        if ev["cmd"] == "blocker" and a.get("block"):
            return float(a.get("fadetime", default_fade))
        return 0.0

    # ── 二、每行之間腳本自己佔掉的時間 → 每行說完後的停留 ──
    between, acc = [], 0.0
    for ev in events:
        if ev["i"] in disp_at:
            between.append(acc)
            acc = 0.0 if disp_at[ev["i"]]["voiced"] else gaps_cfg["silent_line_s"]
        else:
            acc += blocking(ev)
    post = line_gaps(disp, between, gaps_cfg)
    for d, p in zip(disp, post):
        d["post"] = p

    # ── 三、照順序排時間，同時整理各圖層 ──
    intro = None
    t = 0.0
    if intro_card:
        ic = cfg["intro_card"]
        intro = {"dur": float(ic["duration_s"]), "fade": float(ic["fade_s"]), "lines": list(ic["lines"])}
        t = intro["dur"]
    t_start = t

    stage = _Stage(assets.get("sprites") or {}, cfg["stage"], coord["h"], warn)
    stage.focus = [(t_start, None)]
    ev_times: list[dict] = []
    lines_out: list[dict] = []
    dialogs: list[dict] = []
    subtitles: list[dict] = []
    stickers_out: list[dict] = []
    open_stickers: dict[str, dict] = {}
    backgrounds: list[dict] = []
    images: list[dict] = []
    blockers: list[dict] = []
    blocker_state = [0.0, 0.0, 0.0, 0.0]
    shakes: list[dict] = []
    music: list[dict] = []
    sounds: list[dict] = []
    channels: dict[str, dict] = {}
    approx: set[str] = set()

    def close(track: list[dict], when: float) -> None:
        if track and track[-1]["t1"] is None:
            track[-1]["t1"] = when

    def close_sticker(sid: str, when: float, fade: float = 0.0) -> None:
        s = open_stickers.pop(sid, None)
        if s:
            s["t1"], s["fade_out"] = when + fade, fade

    def text_box(a: dict) -> dict:
        return {"x": float(a.get("x", 0)), "y": float(a.get("y", 0)), "width": float(a.get("width", coord["w"])),
                "size": float(a.get("size", 24)), "alignment": str(a.get("alignment", "left")).lower(),
                "char_s": float(a.get("delay", cfg["typewriter_char_s"]))}

    def layer(args: dict, kind: str) -> dict:
        key = args.get("image")
        return {"t": t, "key": key, "src": asset_path(kind, key),
                "fade": float(args.get("fadetime", 0) or 0),
                "x": float(args.get("x", 0)), "y": float(args.get("y", 0)),
                "xscale": float(args.get("xscale", 1)), "yscale": float(args.get("yscale", 1)), "tweens": []}

    def tween(track: list[dict], a: dict) -> None:
        if not track or not track[-1]["key"]:
            return
        cur = track[-1]
        last = cur["tweens"][-1]["to"] if cur["tweens"] else [cur["x"], cur["y"], cur["xscale"], cur["yscale"]]
        names = ("x", "y", "xscale", "yscale")
        cur["tweens"].append({"t": t, "dur": float(a.get("duration", 0) or 0),
                              "from": [float(a.get(n + "from", last[k])) for k, n in enumerate(names)],
                              "to": [float(a.get(n + "to", last[k])) for k, n in enumerate(names)]})

    def stop_music(when: float, fade: float) -> None:
        if music and music[-1]["t1"] is None:
            music[-1]["t1"], music[-1]["fade_out"] = when + fade, fade

    def stop_sound(snd: dict, when: float, fade: float) -> None:
        snd["vol"] += [[when, snd["vol"][-1][1]], [when + fade, 0.0]]
        snd["t1"] = when + fade

    for ev in events:
        cmd, a = ev["cmd"], ev.get("args") or {}
        ev_times.append({"i": ev["i"], "cmd": cmd, "t": t})
        if cmd in _APPROX:
            approx.add(cmd)
            ev_times[-1]["approx"] = True

        d = disp_at.get(ev["i"])
        if d:
            t_voice_end = t + (d["dur"] if d["voiced"] else gaps_cfg["silent_line_s"])
            rec = {"line_id": d["line_id"], "i": ev["i"], "speaker": d["speaker"], "voiced": d["voiced"],
                   "gap": round(d["gap"], 3), "t": t, "t_voice_end": t_voice_end, "t_end": t_voice_end + d["post"],
                   "audio": d["path"]}
            if cmd == "line":
                rec["kind"] = ev["kind"]
                if ev["kind"] == "subtitle":
                    close(subtitles, t)
                    subtitles.append({"line_id": d["line_id"], "t0": t, "t1": None, "text": ev["text"],
                                      **text_box(ev.get("args") or {})})
                else:
                    text, type_from = ev["text"], 0
                    ml = ev.get("multiline")
                    if ml and dialogs and dialogs[-1]["t1"] is None and dialogs[-1].get("block") == ml["block"]:
                        type_from = len(dialogs[-1]["text"])
                        text = dialogs[-1]["text"] + text
                    close(dialogs, t)
                    dialogs.append({"line_id": d["line_id"], "t0": t, "t1": None, "name": ev.get("speaker") or "",
                                    "text": text, "type_from": type_from, "char_s": cfg["typewriter_char_s"],
                                    **({"block": ml["block"]} if ml else {})})
            else:
                rec["kind"] = "sticker"
            lines_out.append(rec)

        if cmd == "sticker":
            sid = str(a.get("id", ""))
            if a.get("text"):
                close_sticker(sid, t)
                s = {"id": sid, "line_id": d["line_id"] if d else None, "t0": t, "t1": None, "fade_out": 0.0,
                     "text": display_text(a["text"], nickname), **text_box(a)}
                open_stickers[sid] = s
                stickers_out.append(s)
            else:
                close_sticker(sid, t, float(a.get("duration", 0) or 0))
        elif cmd == "stickerclear":
            for sid in list(open_stickers):
                close_sticker(sid, t)
        elif cmd == "dialog":
            close(dialogs, t)
        elif cmd == "subtitle":
            close(subtitles, t)
        elif cmd == "charslot":
            stage.charslot(t, a)
        elif cmd == "background":
            backgrounds.append(layer(a, "backgrounds"))
        elif cmd == "image":
            images.append(layer(a, "images"))
        elif cmd == "backgroundtween":
            tween(backgrounds, a)
        elif cmd == "imagetween":
            tween(images, a)
        elif cmd == "blocker":
            target = [float(a.get(k, 0)) for k in ("r", "g", "b")] + [float(a.get("a", 0))]
            src = list(blocker_state)
            if src[3] == 0:
                src[:3] = target[:3]        # 從全透明淡入：直接用目標顏色
            if target[3] == 0:
                target[:3] = src[:3]        # 淡出到全透明：顏色不變，只變透明度
            blockers.append({"t": t, "dur": float(a.get("fadetime", default_fade)), "from": src, "to": target})
            blocker_state = target
        elif cmd == "camerashake":
            shakes.append({"t": t, "dur": float(a.get("duration", 0) or 0), "xs": float(a.get("xstrength", 0)),
                           "ys": float(a.get("ystrength", 0)), "vibrato": float(a.get("vibrato", 10)),
                           "fadeout": bool(a.get("fadeout", False))})
        elif cmd == "playmusic":
            stop_music(t, float(a.get("crossfade", 0) or 0))
            music.append({"t0": t, "t1": None, "fade_out": 0.0, "volume": float(a.get("volume", 1)),
                          "intro": a.get("intro"), "loop": a.get("key"),
                          "intro_path": asset_path("music", a.get("intro")), "loop_path": asset_path("music", a.get("key"))})
        elif cmd == "stopmusic":
            stop_music(t, float(a.get("fadetime", 0) or 0))
        elif cmd == "musicvolume":
            warn("musicvolume 尚未實作，音量維持不變")
        elif cmd == "playsound":
            ch = a.get("channel")
            if ch and ch in channels:
                stop_sound(channels.pop(ch), t, 0.0)
            meta = (assets.get("sounds") or {}).get(a.get("key")) or {}
            snd = {"key": a.get("key"), "path": asset_path("sounds", a.get("key")), "t0": t, "t1": None,
                   "loop": bool(a.get("loop", False)), "channel": ch, "src_dur": meta.get("dur"),
                   "vol": [[t, float(a.get("volume", 1))]]}
            sounds.append(snd)
            if ch:
                channels[ch] = snd
        elif cmd == "soundvolume":
            snd = channels.get(a.get("channel"))
            if snd:
                snd["vol"] += [[t, snd["vol"][-1][1]], [t + float(a.get("fadetime", 0) or 0), float(a.get("volume", 1))]]
        elif cmd == "stopsound":
            fade = float(a.get("fadetime", 0) or 0)
            for ch in ([a["channel"]] if a.get("channel") else list(channels)):
                if ch in channels:
                    stop_sound(channels.pop(ch), t, fade)
        elif cmd not in _HANDLED:
            warn(f"指令 {cmd} 尚未實作，已略過")

        # 這個事件佔多少時間
        if d:
            t = lines_out[-1]["t_end"]
        else:
            t += blocking(ev)

    # 片尾：等還在進行的淡出（音樂、黑幕、字卡）跑完，再多留 tail_s
    pending = [m["t1"] for m in music if m["t1"]] + [b["t"] + b["dur"] for b in blockers] \
        + [s["t1"] for s in stickers_out if s["t1"]] + [s["t1"] for s in sounds if s["loop"] and s["t1"]]
    t = max([t] + pending)
    total = t + cfg["tail_s"]
    close(dialogs, total)
    close(subtitles, total)
    for sid in list(open_stickers):
        close_sticker(sid, total)
    stop_music(total - cfg["tail_s"], min(1.0, cfg["tail_s"]))
    for snd in sounds:
        if snd["t1"] is None:
            if snd["loop"]:
                stop_sound(snd, total - cfg["tail_s"], min(1.0, cfg["tail_s"]))
            else:
                snd["t1"] = snd["t0"] + snd["src_dur"] if snd["src_dur"] else None

    schedule = {
        "scene_id": timeline["scene_id"],
        "story_code": timeline.get("story_code"), "story_name": timeline.get("story_name"),
        "fps": video["fps"], "width": video["width"], "height": video["height"],
        "coord": {"w": coord["w"], "h": coord["h"]},
        "duration": total, "frames": int(round(total * video["fps"])),
        "intro": intro,
        "style": {"dialog": cfg["dialog"], "dim_brightness": cfg["stage"]["dim_brightness"], "fonts": cfg["fonts"]},
        "events": ev_times,
        "lines": lines_out,
        "layers": {"backgrounds": backgrounds, "images": images, "sprites": stage.finish(total),
                   "blockers": blockers, "shakes": shakes, "stickers": stickers_out,
                   "subtitles": subtitles, "dialogs": dialogs},
        "audio": {"voice": [{"line_id": l["line_id"], "t": l["t"], "dur": round(l["t_voice_end"] - l["t"], 3),
                             "path": l["audio"]} for l in lines_out if l["voiced"]],
                  "music": music, "sounds": sounds},
        "approx": sorted(approx),
        "warnings": warnings,
    }
    return _rounded(schedule)


def _rounded(o):
    """時間一律取到毫秒，讓輸出穩定、好比對。"""
    if isinstance(o, float):
        return round(o, 3)
    if isinstance(o, dict):
        return {k: _rounded(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_rounded(v) for v in o]
    return o
