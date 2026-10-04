import pytest

from pipeline import casting, gamedata
from pipeline.gamedata import Scene
from pipeline.parse import parse_scene, parse_script, split_sprite_name, validate_timeline

SCENE = Scene("test_st01", "test", "T-1", "測試", "幕间", "activities/test/level_test_st01")


def parse(text: str) -> dict:
    tl = parse_script(text, SCENE, nickname="博士")
    validate_timeline(tl)
    return tl


def lines(tl: dict) -> list[dict]:
    return [e for e in tl["events"] if e["cmd"] == "line"]


@pytest.mark.parametrize("name,expected", [
    ("avg_npc_1305_1#8$1", ("avg_npc_1305_1", 8, 1)),
    ("avg_npc_069#2", ("avg_npc_069", 2, None)),
    ("avg_npc_1306_1$1", ("avg_npc_1306_1", None, 1)),
    ("npc_10002", ("npc_10002", None, None)),
    ("avg_npc_053#053", ("avg_npc_053", 53, None)),
    ("char_002_amiya_1#a", ("char_002_amiya_1", "a", None)),
])
def test_split_sprite_name(name, expected):
    r = split_sprite_name(name)
    assert (r["group"], r["face"], r["body"]) == expected


def test_line_kinds_ids_and_header():
    tl = parse(
        '[HEADER(key="title_test", is_skippable=true)]\n'
        "旁白一句。\n"
        '[name="凯尔希"]欢迎回来，Dr.{@nickname}。\n'
        '[Subtitle(text="<color=#000000>字幕。</color>", x=300, y=350)]\n'
        "[subtitle]\n"
        '[Sticker(id="st1", text="六十四年前", x=300)]\n'
    )
    assert tl["header"] == {"key": "title_test", "is_skippable": True}
    ls = lines(tl)
    assert [l["kind"] for l in ls] == ["narration", "dialogue", "subtitle"]
    assert [l["line_id"] for l in ls] == ["test_st01_0001", "test_st01_0002", "test_st01_0003"]
    assert ls[1]["speaker"] == "凯尔希" and ls[1]["text"] == "欢迎回来，Dr.博士。"
    assert ls[1]["rich_text"] == "欢迎回来，Dr.{@nickname}。"
    assert ls[2]["text"] == "字幕。" and ls[2]["args"] == {"x": 300, "y": 350}
    assert "rich_text" not in ls[0]
    # 清除用的 [subtitle] 與 Sticker 都不是 line
    assert [e["cmd"] for e in tl["events"]] == ["line", "line", "line", "subtitle", "sticker"]
    assert [e["i"] for e in tl["events"]] == list(range(5))


def test_audio_keys_lose_dollar_prefix():
    tl = parse(
        '[playMusic(intro="$drift_intro",key="$drift_loop", volume=0.6)]\n'
        '[playsound(key="$d_avg_snowstormlp", loop=true, channel="bgs",volume=0)]\n'
        '[PlaySound(key="@Sound_Beta_2/x")]\n'
    )
    e = tl["events"]
    assert e[0] == {"i": 0, "cmd": "playmusic", "args": {"intro": "drift_intro", "key": "drift_loop", "volume": 0.6}}
    assert e[1]["args"]["key"] == "d_avg_snowstormlp" and e[1]["args"]["loop"] is True
    assert e[2]["args"]["key"] == "@Sound_Beta_2/x"


def test_charslot_stage_tracking():
    tl = parse(
        '[charslot(slot="l", name="avg_003_kalts_1#1$1")]\n'
        '[charslot(slot="r", name="avg_4132_ascln_1#4$1", focus="r")]\n'
        '[name="阿斯卡纶"]一。\n'
        '[charslot(slot="l", focus="l")]\n'
        '[name="凯尔希"]二。\n'
        '[charslot(slot="l", focus="n")]\n'
        '[name="远处的声音"]三。\n'
        '[charslot(slot="r", posfrom="0,0", posto="50,0", afrom=1, ato=0, duration=1)]\n'
        '[name="凯尔希"]四。\n'
        "[charslot(duration=1)]\n"
        '[name="凯尔希"]五。\n'
    )
    assert tl["events"][0]["args"] == {
        "slot": "l", "name": "avg_003_kalts_1#1$1", "group": "avg_003_kalts_1", "face": 1, "body": 1}
    ls = lines(tl)
    both = ["avg_003_kalts_1", "avg_4132_ascln_1"]
    assert [(l["sprites_on_stage"], l["focus_group"]) for l in ls] == [
        (both, "avg_4132_ascln_1"),
        (both, "avg_003_kalts_1"),
        (both, None),
        (["avg_003_kalts_1"], None),   # focus="n" 仍然有效
        ([], None),
    ]


def test_sole_sprite_is_focus_and_char_empty_clears_slot():
    tl = parse(
        '[charslot(slot="m", name="avg_npc_053")]\n'
        '[name="负伤的雇佣兵"]一。\n'
        '[charslot(slot="m", name="char_empty")]\n'
        '[name="负伤的雇佣兵"]二。\n'
    )
    ls = lines(tl)
    assert (ls[0]["sprites_on_stage"], ls[0]["focus_group"]) == (["avg_npc_053"], "avg_npc_053")
    assert (ls[1]["sprites_on_stage"], ls[1]["focus_group"]) == ([], None)


def test_slot_and_focus_aliases():
    tl = parse(
        '[charslot(slot="left", name="avg_npc_1294_1#1$1", focus="l")]\n'
        '[charslot(slot="right", name="avg_npc_1306_1#1$1", focus="r")]\n'
        '[name="奴隶商人"]一。\n'
        '[charslot(slot="l", focus="left")]\n'
        '[name="“疤眼”"]二。\n'
    )
    ls = lines(tl)
    assert ls[0]["sprites_on_stage"] == ["avg_npc_1294_1", "avg_npc_1306_1"]
    assert [l["focus_group"] for l in ls] == ["avg_npc_1306_1", "avg_npc_1294_1"]


def test_legacy_character_syntax():
    tl = parse(
        '[character(name="char_002_amiya_1#3", name2="char_003_kalts_1", focus=2)]\n'
        '[name="凯尔希"]一。\n'
        '[character(name="char_002_amiya_1")]\n'
        '[name="阿米娅"]二。\n'
        "[character]\n"
        '[name="阿米娅"]三。\n'
    )
    assert tl["events"][0]["args"]["chars"] == [
        {"name": "char_002_amiya_1#3", "group": "char_002_amiya_1", "face": 3, "body": None},
        {"name": "char_003_kalts_1", "group": "char_003_kalts_1", "face": None, "body": None},
    ]
    ls = lines(tl)
    assert (ls[0]["sprites_on_stage"], ls[0]["focus_group"]) == (
        ["char_002_amiya_1", "char_003_kalts_1"], "char_003_kalts_1")
    assert (ls[1]["sprites_on_stage"], ls[1]["focus_group"]) == (["char_002_amiya_1"], "char_002_amiya_1")
    assert ls[2]["sprites_on_stage"] == []


def test_cutin_counts_as_on_stage():
    tl = parse(
        '[CharacterCutin(widgetID="1", name="avg_4131_odda_1#5$2", style="cutin")]\n'
        '[name="奥达"]一。\n'
        '[CharacterCutin(widgetID="1", name="char_empty")]\n'
        '[name="奥达"]二。\n'
    )
    ls = lines(tl)
    assert ls[0]["sprites_on_stage"] == ["avg_4131_odda_1"] and ls[1]["sprites_on_stage"] == []


def test_multiline_stays_separate_lines_in_order():
    tl = parse(
        '[multiline(name="巴别塔成员")]我们必须立刻——\n'
        "[CameraShake(duration=0.5)]\n"
        '[multiline(name="巴别塔成员", end=true)]咳咳——\n'
        '[multiline(name="曼弗雷德")]你等——\n'
        '[multiline(name="曼弗雷德")]啊！\n'
        "[dialog]\n"
        '[multiline(name="阿米娅",end=true)]开了！\n'
    )
    assert [e["cmd"] for e in tl["events"]] == ["line", "camerashake", "line", "line", "line", "dialog", "line"]
    assert [l["multiline"] for l in lines(tl)] == [
        {"block": 1, "end": False}, {"block": 1, "end": True},
        {"block": 2, "end": False}, {"block": 2, "end": False},   # 沒寫 end，靠 [dialog] 收尾
        {"block": 3, "end": True},
    ]
    assert tl["stats"]["multiline"] == 5 and tl["stats"]["planning_count"] == 0


def test_unknown_and_malformed_commands_are_kept_verbatim():
    tl = parse('[FutureCmd(foo="bar", n=2)]\n[Delay(time=1\n[Delay(time=1)]\n')
    e = tl["events"]
    assert e[0] == {"i": 0, "cmd": "futurecmd", "args": {"foo": "bar", "n": 2}, "raw": '[FutureCmd(foo="bar", n=2)]'}
    assert e[1]["cmd"] == "_unparsed" and e[1]["raw"] == "[Delay(time=1" and e[1]["src_line"] == 2
    assert "raw" not in e[2]


def test_decision_options_split():
    tl = parse('[Decision(options="走;留", values="1;2")]\n[Predicate(references="1")]\n')
    assert tl["events"][0]["args"] == {"options": ["走", "留"], "values": ["1", "2"]}


def test_schema_rejects_broken_timeline():
    tl = parse('[name="凯尔希"]一。\n')
    tl["events"][0]["speaker"] = None
    with pytest.raises(ValueError):
        validate_timeline(tl)


# ---- 以下需要 data/gamedata（python -m pipeline fetch-gamedata） ----

def _babel() -> list[Scene]:
    try:
        scenes = gamedata.list_scenes("act33side")
    except FileNotFoundError:
        pytest.skip("尚未下載 gamedata")
    if not all(s.path.exists() for s in scenes):
        pytest.skip("尚未下載 gamedata")
    return scenes


def test_bb_st_1_has_127_lines():
    _babel()
    tl = parse_scene(gamedata.find_scene("act33side_st01"))
    assert (tl["story_code"], tl["story_name"], tl["avg_tag"]) == ("BB-ST-1", "未完成的告别", "幕间")
    st = tl["stats"]
    # 規劃口徑：[name=...] 行 + 非 [ 開頭的非空行
    assert st["planning_count"] == 127
    assert (st["dialogue"], st["narration"]) == (89, 38)
    assert not [e for e in tl["events"] if "raw" in e]


def test_all_23_babel_scenes_parse_and_match_planning_numbers():
    scenes = _babel()
    assert len(scenes) == 23
    timelines = [parse_scene(s) for s in scenes]   # parse_scene 內含 schema 驗證
    assert not [e for tl in timelines for e in tl["events"] if "raw" in e]
    total = lambda k: sum(tl["stats"][k] for tl in timelines)
    assert total("planning_count") == pytest.approx(4400, rel=0.02)
    assert total("narration") == pytest.approx(761, rel=0.02)
    rows = casting.collect_speakers(timelines)
    named = [r for r in rows if not r["speaker"].startswith("（")]
    assert abs(len(named) - 104) <= 3
    doctor = next(r for r in rows if r["speaker"] == "博士")
    assert doctor["line_count"] == pytest.approx(467, rel=0.02)
