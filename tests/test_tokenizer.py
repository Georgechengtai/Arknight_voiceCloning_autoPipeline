from pipeline.tokenizer import tokenize_line


def test_command_with_args_and_type_conversion():
    t = tokenize_line('[Blocker(a=0.6, r=0, g=0, b=0, fadetime=2, block=true)]')
    assert t.kind == "command" and t.cmd == "blocker"
    assert t.args == {"a": 0.6, "r": 0, "g": 0, "b": 0, "fadetime": 2, "block": True}
    assert isinstance(t.args["r"], int) and isinstance(t.args["a"], float)


def test_command_without_args_and_case_folding():
    assert tokenize_line("[Dialog]").cmd == "dialog"
    assert tokenize_line("[dialog]").args == {}
    assert tokenize_line("[HEADER(key=\"title_test\", is_skippable=true)]").cmd == "header"


def test_dialogue_line():
    t = tokenize_line('[name="凯尔希"]欢迎回来，Dr.{@nickname}。')
    assert t.cmd == "name" and t.args == {"name": "凯尔希"}
    assert t.text == "欢迎回来，Dr.{@nickname}。"


def test_dialogue_text_may_contain_brackets():
    t = tokenize_line('[name="博士"]影像编号[0018]（admin）……')
    assert t.args == {"name": "博士"} and t.text == "影像编号[0018]（admin）……"


def test_narration_blank_comment():
    assert tokenize_line("巨人轻轻讲述一部遥远的史诗……\n").kind == "text"
    assert tokenize_line("   \n").kind == "blank"
    assert tokenize_line("// 註解").kind == "comment"


def test_quoted_value_with_commas_parens_and_spaces():
    t = tokenize_line('[Sticker(id="st1", text="可惜，可叹, (烈怒) 火光]汹涌", size="1280, 100", x=300,y=370)]')
    assert t.args == {"id": "st1", "text": "可惜，可叹, (烈怒) 火光]汹涌", "size": "1280, 100", "x": 300, "y": 370}


def test_irregular_spacing_around_equals_and_commas():
    t = tokenize_line('[charslot(slot = "m", name = "avg_npc_1296_1#1$1",duration = 1.5 , isblock=true)]')
    assert t.args == {"slot": "m", "name": "avg_npc_1296_1#1$1", "duration": 1.5, "isblock": True}
    t = tokenize_line('[CharacterCutin(widgetID="1", fadestyle= "horiz_expand_center", offsetx=-300)]')
    assert t.cmd == "charactercutin"
    assert t.args == {"widgetid": "1", "fadestyle": "horiz_expand_center", "offsetx": -300}


def test_quoted_numbers_stay_strings():
    t = tokenize_line('[Decision(options="走;留", values="1;2")]')
    assert t.args == {"options": "走;留", "values": "1;2"}


def test_unescaped_quote_inside_value():
    t = tokenize_line('[Subtitle(text="他说"好"，然后离开", x=300)]')
    assert t.args == {"text": '他说"好"，然后离开', "x": 300}


def test_rich_text_tags_survive_tokenizing():
    t = tokenize_line('[Sticker(id="st1", text="<color=#000000>一条自毁之路。</color>", block = true)]')
    assert t.args["text"] == "<color=#000000>一条自毁之路。</color>" and t.args["block"] is True


def test_multiline_command_with_trailing_text():
    t = tokenize_line('[multiline(name="巴别塔成员", end=true)]咳。')
    assert t.cmd == "multiline" and t.args == {"name": "巴别塔成员", "end": True} and t.text == "咳。"


def test_malformed_lines_do_not_raise():
    for bad in ('[Delay(time=1', '[name="X', "[", "[Delay(time)]", "[=x]"):
        t = tokenize_line(bad)
        assert t.cmd == "_unparsed" and t.error and t.raw == bad
