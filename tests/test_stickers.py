from pipeline.stickers import clean_sticker_text, sticker_lines
from pipeline.tts_text import spoken_text


def _tl(*texts):
    events = [{"i": i, "cmd": "sticker", "args": {"id": f"st{i}", "text": t}} for i, t in enumerate(texts)]
    events.append({"i": len(events), "cmd": "sticker", "args": {"id": "st9"}})          # 無文字：清除指令
    return {"scene_id": "act33side_st01", "events": events}


def test_sticker_lines_numbering_and_silence():
    lines = sticker_lines(_tl("……", "<i>我见远方的军队袭来家园，</i>", "\\n\\n欢迎您，Dr.{@nickname}。"))
    assert [x["line_id"] for x in lines] == ["act33side_st01_s001", "act33side_st01_s002", "act33side_st01_s003"]
    assert [x["silent"] for x in lines] == [True, False, False]
    assert lines[1]["text"] == "我见远方的军队袭来家园，"
    assert lines[2]["text"] == "欢迎您，Dr.博士。"


def test_clean_joins_lines():
    assert clean_sticker_text("第一行\\n第二行", "博士") == "第一行 第二行"


def test_spoken_text_nickname():
    assert spoken_text("欢迎回来，Dr.博士。") == "欢迎回来，博士。"
    assert spoken_text("……博士。Dr.博士。") == "……博士。博士。"
    assert spoken_text("博士，你需要休息。") == "博士，你需要休息。"


def test_mon3tr_is_read_as_monster():
    from pipeline.tts_text import spoken_text
    assert spoken_text("Mon3tr，切开门！") == "Monster，切开门！"
