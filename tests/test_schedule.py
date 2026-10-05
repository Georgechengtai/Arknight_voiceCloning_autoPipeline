"""時間表展開：給定音訊長度，檢查每個事件的時刻與各圖層。"""
import copy
import json

import pytest

from pipeline.common.paths import OUT_DIR
from pipeline.common.settings import load_settings
from pipeline.render.schedule import build_schedule, line_gaps

SCENE = "t_scene"


def settings(**gaps):
    s = copy.deepcopy(load_settings())
    s["render"]["gaps"].update({"same_speaker_s": 0.8, "turn_s": 0.6, "silent_line_s": 1.0,
                                "min_hold_after_line_s": 0.3, "absorb_script_time": True, **gaps})
    s["render"]["tail_s"] = 1.0
    s["render"]["intro_card"].update(duration_s=4.0, fade_s=0.5)
    s["pacing"]["blocker_default_fadetime_s"] = 0.25
    return s


class Script:
    """小型 timeline 產生器。say() 同時登記語音清單。"""

    def __init__(self):
        self.events, self.voice, self.n_lines, self.n_stickers = [], [], 0, 0

    def cmd(self, cmd, **args):
        self.events.append({"i": len(self.events), "cmd": cmd, "args": args})
        return self

    def say(self, speaker, dur, text="台词", gap=None, kind="dialogue", **extra):
        self.n_lines += 1
        lid = f"{SCENE}_{self.n_lines:04d}"
        self.events.append({"i": len(self.events), "cmd": "line", "line_id": lid, "kind": kind,
                            "speaker": speaker if kind == "dialogue" else None, "text": text, **extra})
        self.voice.append({"line_id": lid, "speaker": speaker or "", "path": f"voice/{lid}.wav" if dur else None,
                           "dur": dur, "gap_before": gap})
        return self

    def card(self, sid, text, dur, speaker="旁白", gap=None, **args):
        self.n_stickers += 1
        lid = f"{SCENE}_s{self.n_stickers:03d}"
        self.cmd("sticker", id=sid, text=text, **args)
        self.voice.append({"line_id": lid, "speaker": speaker, "path": f"voice/{lid}.wav" if dur else None,
                           "dur": dur, "gap_before": gap})
        return self

    def build(self, assets=None, cfg=None, **kw):
        tl = {"scene_id": SCENE, "coord_system": {"w": 1280, "h": 720}, "events": self.events}
        return build_schedule(tl, {"scene": SCENE, "lines": self.voice}, assets, cfg or settings(), **kw)


def times(schedule):
    return {l["line_id"][-4:]: (l["t"], l["t_voice_end"], l["t_end"]) for l in schedule["lines"]}


def test_gap_same_speaker_turn_and_explicit():
    s = Script().say("甲", 2.0).say("甲", 1.0).say("乙", 1.0).say("乙", 1.0, gap=0.2).build()
    t = times(s)
    assert t["0001"][0] == 0                       # 全場第一句不留間隔
    assert t["0002"][0] == pytest.approx(2.8)      # 同一人接著說 0.8
    assert t["0003"][0] == pytest.approx(4.4)      # 換人 0.6
    assert t["0004"][0] == pytest.approx(5.6)      # 清單指定的 gap_before 優先
    assert s["duration"] == pytest.approx(6.6 + 0.3 + 1.0)   # 最後一句＋停留＋片尾


def test_script_delay_counts_toward_gap():
    long = Script().say("甲", 2.0).cmd("delay", time=1).say("乙", 1.0).build()
    assert times(long)["0002"][0] == pytest.approx(2.0 + 0.3 + 1.0)    # 等待已超過間隔：字只多留 0.3
    short = Script().say("甲", 2.0).cmd("delay", time=0.2).say("乙", 1.0).build()
    assert times(short)["0002"][0] == pytest.approx(2.6)               # 不足的部分補滿到 0.6
    added = Script().say("甲", 2.0).cmd("delay", time=1).say("乙", 1.0).build(cfg=settings(absorb_script_time=False))
    assert times(added)["0002"][0] == pytest.approx(3.6)               # 關掉吸收：間隔與等待相加


def test_unvoiced_line_holds_one_second():
    s = Script().say("甲", 2.0).say("乙", 0, text="……").say("甲", 1.0).build()
    t = times(s)
    assert t["0002"] == (pytest.approx(2.6), pytest.approx(3.6), pytest.approx(3.6))
    assert t["0003"][0] == pytest.approx(3.6)
    assert [v["line_id"][-4:] for v in s["audio"]["voice"]] == ["0001", "0003"]


def test_blocker_blocks_only_when_asked():
    s = (Script().cmd("blocker", a=1, fadetime=2, block=True).cmd("blocker", a=0, fadetime=3, block=False)
         .cmd("blocker", a=1, block=True).say("甲", 1.0).build())
    assert [e["t"] for e in s["events"]] == [0, 2, 2, 2.25]
    b = s["layers"]["blockers"]
    assert b[0]["from"][3] == 0 and b[0]["to"][3] == 1 and b[2]["dur"] == 0.25


def test_voice_and_text_start_together():
    s = Script().say("甲", 2.0).cmd("charslot").cmd("delay", time=0.5).say(None, 1.5, kind="narration").build()
    d = s["layers"]["dialogs"]
    assert [x["t0"] for x in d] == [l["t"] for l in s["lines"]] == [v["t"] for v in s["audio"]["voice"]]
    assert d[0]["t1"] == d[1]["t0"] and d[0]["name"] == "甲" and d[1]["name"] == ""


def test_dialog_cleared_by_dialog_command():
    s = Script().say("甲", 2.0).cmd("dialog").cmd("delay", time=1).build()
    assert s["layers"]["dialogs"][0]["t1"] == pytest.approx(2.3)


def test_sticker_stays_until_voice_is_done():
    s = (Script().card("st1", "第一行", 2.0).card("st2", "第二行", 3.0)
         .cmd("sticker", id="st1").cmd("sticker", id="st2", duration=1).cmd("delay", time=1.5)
         .card("st1", "……", 0).build())
    a, b, c = s["layers"]["stickers"]
    assert a["t0"] == 0 and b["t0"] == pytest.approx(2.8)
    assert a["t1"] >= b["t0"] + 3.0                       # 腳本的移除排在語音之後
    assert b["fade_out"] == 1 and b["t1"] == pytest.approx(a["t1"] + 1)
    assert [l["kind"] for l in s["lines"]] == ["sticker"] * 3
    assert s["lines"][2]["voiced"] is False and c["t1"] == pytest.approx(s["duration"])


def test_subtitle_replaced_and_cleared():
    s = (Script().say(None, 1.0, kind="subtitle", args={"x": 300, "y": 370, "width": 700, "alignment": "center", "delay": 0.04})
         .say(None, 1.0, kind="subtitle", args={}).cmd("subtitle").build())
    a, b = s["layers"]["subtitles"]
    assert a["t1"] == b["t0"] and a["alignment"] == "center" and a["char_s"] == 0.04
    assert b["t1"] == pytest.approx(b["t0"] + 1.0 + 0.3)
    assert s["layers"]["dialogs"] == []


ASSETS = {"sprites": {"g1": {"pos": {"x": 30, "y": 180}, "size": {"x": 970, "y": 970},
                             "variants": {"g1#1$1": {"path": "assets/char/g1_1_1.png"},
                                          "g1#3$1": {"path": "assets/char/g1_3_1.png"}}}},
          "backgrounds": {"bg_x": {"path": "assets/bg/bg_x.png"}},
          "music": {"m_intro": {"path": "a/m_intro.mp3"}, "m_loop": {"path": "a/m_loop.mp3"}},
          "sounds": {"snd": {"path": "a/snd.mp3", "dur": 0.5}, "wind": {"path": "a/wind.mp3", "dur": 9}}}


def test_sprites_fade_swap_focus_and_clear():
    s = (Script()
         .cmd("charslot", slot="l", name="g1#1$1", group="g1", face=1, body=1, duration=1.5)
         .cmd("delay", time=2)
         .cmd("charslot", slot="r", name="g2#1$1", group="g2", face=1, body=1)
         .cmd("charslot", slot="right", focus="right")
         .say("乙", 1.0)
         .cmd("charslot", slot="l", name="g1#3$1", group="g1", face=3, body=1, focus="l")
         .say("甲", 1.0)
         .cmd("charslot", slot="l", posfrom="0,0", posto="200,0", duration=0.3, afrom=1, ato=0)
         .cmd("delay", time=1)
         .cmd("charslot", duration=0.5)
         .cmd("delay", time=1)
         .build(assets=ASSETS))
    left, right = s["layers"]["sprites"]
    assert (left["slot"], left["fade_in"], left["x"], left["cy"], left["size"]) == ("l", 1.5, 470, 540, 970)
    assert [im["src"] for im in left["images"]] == ["assets/char/g1_1_1.png", "assets/char/g1_3_1.png"]   # 換表情不換實例
    assert left["lit"] == [[0, True], [2, False], [3.6, True]]
    assert right["lit"] == [[2, True], [3.6, False]]
    assert right["images"][0]["src"] is None and any("g2#1$1" in w for w in s["warnings"])   # 素材清單沒有的立繪
    assert left["moves"][0]["to"] == [200, 0] and left["t1"] == pytest.approx(left["moves"][0]["t"] + 0.3)
    assert right["fade_out"] == 0.5 and right["t1"] == pytest.approx(left["moves"][0]["t"] + 1 + 0.5)


def test_background_tween_and_missing_asset_warning():
    s = (Script().cmd("background", image="bg_x").cmd("backgroundtween", xfrom=0, xto=20, xscaleto=1.1, yscaleto=1.1, duration=30)
         .cmd("image", image="cg_none").cmd("delay", time=1).cmd("image").build(assets=ASSETS))
    bg = s["layers"]["backgrounds"][0]
    assert bg["src"] == "assets/bg/bg_x.png"
    assert bg["tweens"][0]["from"] == [0, 0, 1, 1] and bg["tweens"][0]["to"] == [20, 0, 1.1, 1.1]
    assert [i["key"] for i in s["layers"]["images"]] == ["cg_none", None]
    assert any("cg_none" in w for w in s["warnings"]) and "backgroundtween" in s["approx"]


def test_music_and_sound_segments():
    s = (Script().cmd("playsound", key="wind", loop=True, channel="bgs", volume=0)
         .cmd("soundvolume", channel="bgs", volume=0.6, fadetime=3)
         .cmd("playmusic", intro="m_intro", key="m_loop", volume=0.6)
         .cmd("delay", time=5).cmd("playsound", key="snd")
         .cmd("stopsound", channel="bgs", fadetime=2).cmd("stopmusic", fadetime=1).cmd("delay", time=4)
         .cmd("playmusic", key="m_loop").cmd("delay", time=1).build(assets=ASSETS))
    m1, m2 = s["audio"]["music"]
    assert (m1["t0"], m1["t1"], m1["fade_out"], m1["intro_path"]) == (0, 6, 1, "a/m_intro.mp3")
    assert m2["t0"] == 9 and m2["intro_path"] is None and m2["t1"] == pytest.approx(10 + 1)   # 沒停的音樂在片尾淡出
    wind, snd = s["audio"]["sounds"]
    assert wind["vol"] == [[0, 0], [0, 0], [3, 0.6], [5, 0.6], [7, 0]] and wind["t1"] == 7
    assert (snd["t0"], snd["t1"], snd["loop"]) == (5, 5.5, False)


def test_intro_card_shifts_everything():
    plain = Script().say("甲", 2.0).say("乙", 1.0)
    a, b = plain.build(), plain.build(intro_card=True)
    assert b["intro"]["dur"] == 4.0 and a["intro"] is None
    assert b["duration"] == pytest.approx(a["duration"] + 4.0)
    assert [l["t"] for l in b["lines"]] == [pytest.approx(l["t"] + 4.0) for l in a["lines"]]


def test_multiline_appends_in_same_box():
    s = (Script().say("甲", 1.0, text="前半，", multiline={"block": 1, "end": False})
         .say("甲", 1.0, text="后半。", multiline={"block": 1, "end": True}).build())
    a, b = s["layers"]["dialogs"]
    assert b["text"] == "前半，后半。" and b["type_from"] == 3 and a["type_from"] == 0


def test_missing_voice_entry_is_warned_not_fatal():
    sc = Script().say("甲", 1.0)
    sc.voice.clear()
    s = sc.build()
    assert s["lines"][0]["voiced"] is False and any("0001" in w for w in s["warnings"])


def test_line_gaps_pure():
    disp = [{"voiced": True, "speaker": "甲", "gap_before": None}, {"voiced": True, "speaker": "甲", "gap_before": 0.0},
            {"voiced": True, "speaker": "乙", "gap_before": 2.0}]
    cfg = settings()["render"]["gaps"]
    assert line_gaps(disp, [0, 0, 3.0], cfg) == [0.0, 0.3, 0.3]      # 打斷不留空；換場的 2 秒被轉場吃掉


# ── 真實場景（資料不入庫，沒有就跳過） ──

REAL = OUT_DIR / "act33side_st01"


@pytest.mark.skipif(not (REAL / "voice_manifest.json").exists() or not (REAL / "timeline.json").exists(),
                    reason="沒有 BB-ST-1 的 timeline 或語音清單")
def test_real_scene_is_consistent():
    load = lambda n: json.loads((REAL / n).read_text(encoding="utf-8"))  # noqa: E731
    assets = load("assets_manifest.json") if (REAL / "assets_manifest.json").exists() else None
    s = build_schedule(load("timeline.json"), load("voice_manifest.json"), assets, load_settings(),
                       voice_dir="out/act33side_st01")
    assert len(s["lines"]) == 158 and len(s["audio"]["voice"]) == 143
    ts = [e["t"] for e in s["events"]]
    assert ts == sorted(ts)
    shown = {x["line_id"]: x for k in ("dialogs", "subtitles", "stickers") for x in s["layers"][k]}
    for l in s["lines"]:
        box = shown[l["line_id"]]
        assert box["t0"] == l["t"]                              # 字與聲音同時開始
        assert box["t1"] >= l["t_voice_end"] - 1e-6             # 字至少留到這句說完
    for a, b in zip(s["lines"], s["lines"][1:]):
        assert b["t"] >= a["t_end"] - 1e-6                      # 語音不重疊
    assert not [w for w in s["warnings"] if "語音清單" in w]
