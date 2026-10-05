"""素材鍵解析的單測：全部用小型假索引，不碰網路。鍵的各種形式見 docs/02-data-sources.md §3、§3b。"""
import pytest

from pipeline import assets
from pipeline.assets import Candidate, Indexes, Item, Requirements

SUMMARY = {
    "avg_003_kalts_1": {"size": {"x": 890.0, "y": 890.0}, "pos": {"x": 0.0, "y": 180.0},
                        "items": {"avg_003_kalts_1": "", "avg_003_kalts_1#1$1": "", "avg_003_kalts_1#4$1": ""}},
    "avg_npc_053": {"size": {"x": 1024.0, "y": 1024.0}, "pos": {"x": 0.0, "y": 180.0},
                    "items": {"avg_npc_053#053": ""}},
    "npc_10002": {"size": {"x": 1100.0, "y": 1100.0}, "pos": {"x": 0.0, "y": 400.0}, "items": {"npc_10002#1": ""}},
    "avg_npc_069": {"size": {"x": 1.0, "y": 1.0}, "pos": {"x": 0.0, "y": 0.0},
                    "items": {"avg_npc_069#1": "", "avg_npc_069#2": ""}},
}
LINK = {
    "avg_003_kalts_1": {"pos": {"x": 0.0, "y": 180.0}, "size": {"x": 890.0, "y": 890.0},
                        "array": [{"alias": "", "name": "avg_003_kalts_1-1$1"},
                                  {"alias": "", "name": "avg_003_kalts_1-4$1"}]},
    "npc_10002": {"pos": {"x": 0.0, "y": 400.0}, "size": {"x": 1100.0, "y": 1100.0},
                  "array": [{"alias": "", "name": "npc_10002_1"}]},
    "avg_npc_053": {"pos": {"x": 0.0, "y": 180.0}, "size": {"x": 1024.0, "y": 1024.0},
                    "array": [{"alias": "", "name": "avg_npc_053"}]},
    "avg_npc_1306_1": {"pos": {"x": 0.0, "y": 0.0}, "size": {"x": 1.0, "y": 1.0},
                       "array": [{"alias": "", "name": "avg_npc_1306_1$1"}]},
}
CHAR = {k: f"https://media.prts.wiki/x/xx/Avg_{k}.png" for k in
        ("avg_003_kalts_1-1$1", "avg_003_kalts_1-4$1", "npc_10002_1", "avg_npc_053", "avg_npc_1306_1$1")}
AUDIO = {"drift_intro": "Sound_Beta_2/Music/act9d0d0/m_avg_drift_intro",
         "Mon3tr_n": "Sound_Beta_2/Player/p_atk/p_atk_Mon3tr_n"}
IMAGE = {"bg_bg_laccolith": "https://media.prts.wiki/b/b9/Avg_bg_bg_laccolith.png",
         "avg_5_7_shining": "https://media.prts.wiki/f/f1/Avg_avg_5_7_shining.png"}
IDX = Indexes(SUMMARY, IMAGE, CHAR, LINK, AUDIO)


@pytest.mark.parametrize("name, expected", [
    ("avg_npc_1305_1#8$1", ("avg_npc_1305_1", "8", "1")),
    ("avg_npc_069#2", ("avg_npc_069", "2", None)),
    ("avg_npc_1306_1$1", ("avg_npc_1306_1", None, "1")),
    ("npc_10002", ("npc_10002", None, None)),
])
def test_split_sprite_name(name, expected):
    assert assets.split_sprite_name(name) == expected


@pytest.mark.parametrize("name, item, filename", [
    ("avg_003_kalts_1#4$1", "avg_003_kalts_1#4$1", "avg_003_kalts_1_4_1"),
    ("avg_003_kalts_1", "avg_003_kalts_1", "avg_003_kalts_1"),         # 本體
    ("avg_npc_053", "avg_npc_053#053", "avg_npc_053_053"),             # 舊式 NPC 經 summary 命中
    ("npc_10002", "npc_10002#1", "npc_10002_1"),
    ("avg_npc_069#2", "avg_npc_069#2", "avg_npc_069_2"),               # 只有 face
])
def test_fexli_sprite_item(name, item, filename):
    got, warning = assets.fexli_sprite_item(name, SUMMARY)
    assert (got, warning) == (item, None)
    assert assets.fexli_file_key(got) == filename


def test_fexli_sprite_missing_variant_falls_back_with_warning():
    got, warning = assets.fexli_sprite_item("avg_003_kalts_1#99$1", SUMMARY)
    assert got == "avg_003_kalts_1" and "avg_003_kalts_1#99$1" in warning


def test_fexli_sprite_unknown_group():
    assert assets.fexli_sprite_item("avg_npc_9999_1#1$1", SUMMARY) == (None, None)


@pytest.mark.parametrize("name, key", [
    ("avg_003_kalts_1#4$1", "avg_003_kalts_1-4$1"),
    ("avg_003_kalts_1", "avg_003_kalts_1-1$1"),       # face、body 缺省取 1
    ("avg_npc_1306_1", "avg_npc_1306_1$1"),           # 只有 body 的鍵
    ("avg_npc_053", "avg_npc_053"),
    ("npc_10002", "npc_10002_1"),                     # 舊式 _1
])
def test_prts_sprite_key(name, key):
    assert assets.prts_sprite_key(name, LINK, CHAR) == (key, None)


def test_prts_sprite_missing_variant_falls_back_with_warning():
    key, warning = assets.prts_sprite_key("avg_003_kalts_1#9$1", LINK, CHAR)
    assert key == "avg_003_kalts_1-1$1" and warning


def test_audio_urls_are_lowercased():
    path = assets.audio_index_path("$Mon3tr_n", AUDIO)
    assert path == "Sound_Beta_2/Player/p_atk/p_atk_Mon3tr_n"
    assert assets.torappu_audio_url(path) == "https://torappu.prts.wiki/assets/audio/player/p_atk/p_atk_mon3tr_n.mp3"
    assert assets.aceship_audio_url(path).endswith("/main/player/p_atk/p_atk_mon3tr_n.wav")


def test_audio_key_case_insensitive_and_missing():
    assert assets.audio_index_path("mon3tr_N", AUDIO) == AUDIO["Mon3tr_n"]
    assert assets.audio_index_path("no_such_key", AUDIO) is None


def test_parse_kv_index_skips_junk():
    text = "a,https://x/a.png\n<noinclude>\nb$1,https://x/b$1.png\n"
    assert assets.parse_kv_index(text) == {"a": "https://x/a.png", "b$1": "https://x/b$1.png"}


TIMELINE = {"events": [
    {"i": 0, "cmd": "background", "args": {"image": "bg_laccolith"}},
    {"i": 1, "cmd": "image", "args": {"image": "avg_5_7_shining"}},
    {"i": 2, "cmd": "image", "args": {}},
    {"i": 3, "cmd": "charslot", "args": {"slot": "m", "name": "avg_003_kalts_1#4$1"}},
    {"i": 4, "cmd": "charslot", "args": {}},
    {"i": 5, "cmd": "charactercutin", "args": {"name": "char_empty"}},
    {"i": 6, "cmd": "playmusic", "args": {"intro": "drift_intro", "key": "drift_loop"}},
    {"i": 7, "cmd": "playsound", "args": {"key": "Mon3tr_n"}},
    {"i": 8, "cmd": "interlude", "args": {"name": "bg_black"}},
    {"i": 9, "cmd": "gridbg", "args": {"imagegroup": "sky_L1/sky_r1"}},
    {"i": 10, "cmd": "bgeffect", "args": {"name": "$eb_snow"}},
    {"i": 11, "cmd": "line", "kind": "narration", "text": "……"},
]}


def test_collect_requirements():
    req = assets.collect_requirements(TIMELINE)
    assert req.backgrounds == {"bg_laccolith", "bg_black", "sky_L1", "sky_r1"}
    assert req.images == {"avg_5_7_shining"}
    assert req.sprites == {"avg_003_kalts_1#4$1"}
    assert req.music == {"drift_intro", "drift_loop"}
    assert req.sounds == {"Mon3tr_n"}
    assert req.effects == {"bgeffect:$eb_snow"}


def test_resolve_orders_sources_and_flags_unknown_audio():
    items = {(i.kind, i.key): i for i in assets.resolve(assets.collect_requirements(TIMELINE), IDX)}
    bg = items["backgrounds", "bg_laccolith"]
    assert [c.source for c in bg.candidates] == ["fexli", "prts"]
    assert bg.candidates[0].url.endswith("/avgs/bg/bg_laccolith.png")
    assert items["images", "avg_5_7_shining"].candidates[0].url.endswith("/avgs/avg_5_7_shining.png")
    sp = items["sprites", "avg_003_kalts_1#4$1"]
    assert sp.path == "assets/char/avg_003_kalts_1_4_1.png"
    assert sp.candidates[0].url.endswith("/avgs/npcs/avg_003_kalts_1_4_1.png")
    assert sp.candidates[1].url.endswith("Avg_avg_003_kalts_1-4%241.png")       # $ 要跳脫
    assert sp.extra == {"group": "avg_003_kalts_1", "pos": {"x": 0.0, "y": 180.0}, "size": {"x": 890.0, "y": 890.0}}
    assert [c.source for c in items["music", "drift_intro"].candidates] == ["prts", "aceship"]
    assert items["music", "drift_loop"].candidates == []                         # 假索引裡沒有


def test_sniff():
    assert assets.sniff(b"\x89PNG\r\n\x1a\n....") == "png"
    assert assets.sniff(b"ID3\x04....") == "mp3"
    assert assets.sniff(b"\xff\xfb\x90\x00") == "mp3"
    assert assets.sniff(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "wav"
    assert assets.sniff(b"<!DOCTYPE html>") is None


class FakeFetcher:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url):
        self.asked.append(url)
        return self.pages.get(url)


PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x04\x00\x00\x00\x02\x40rest"


def test_fetch_item_falls_back_skips_existing_and_records_source(tmp_path):
    item = Item("backgrounds", "bg_x", "assets/bg/bg_x.png",
                [Candidate("fexli", "https://f/bg_x.png"), Candidate("prts", "https://p/bg_x.png")])
    # 第一個來源 404、第二個回傳 HTML 以外的真 PNG
    f = FakeFetcher({"https://p/bg_x.png": PNG})
    sources = {}
    entry = assets.fetch_item(item, f, tmp_path, sources)
    assert entry == {"source": "prts", "url": "https://p/bg_x.png", "path": "assets/bg/bg_x.png",
                     "bytes": len(PNG), "w": 1024, "h": 576}
    assert (tmp_path / "assets/bg/bg_x.png").read_bytes() == PNG
    # 再跑一次：檔案已在，不發任何請求，來源照舊
    f2 = FakeFetcher({})
    assert assets.fetch_item(item, f2, tmp_path, sources) == entry
    assert f2.asked == []


def test_fetch_item_rejects_html_and_reports_missing(tmp_path):
    item = Item("sounds", "k", "assets/audio/sound/k.mp3", [Candidate("prts", "https://p/k.mp3")])
    assert assets.fetch_item(item, FakeFetcher({"https://p/k.mp3": b"<html>blocked</html>"}), tmp_path, {}) is None
    assert not (tmp_path / "assets/audio/sound/k.mp3").exists()


def test_build_manifest_groups_sprites_and_lists_missing():
    req = Requirements(sprites={"avg_003_kalts_1#4$1"}, sounds={"nope"}, effects={"bgeffect:$eb_snow"})
    items = assets.resolve(req, IDX)
    entry = {"source": "fexli", "url": "u", "path": "assets/char/avg_003_kalts_1_4_1.png", "bytes": 1}
    man = assets.build_manifest("s", items, {("sprites", "avg_003_kalts_1#4$1"): entry, ("sounds", "nope"): None}, req)
    assert man["sprites"] == {"avg_003_kalts_1": {"pos": {"x": 0.0, "y": 180.0}, "size": {"x": 890.0, "y": 890.0},
                                                  "variants": {"avg_003_kalts_1#4$1": entry}}}
    assert man["missing"] == [{"kind": "sounds", "key": "nope", "reason": "索引裡沒有這個鍵"}]
    assert man["effects"] == ["bgeffect:$eb_snow"]
