import json
import pytest
from pipeline.tts_text import normalize_nickname, spoken_text
from tools import scene_lines

@pytest.mark.parametrize('text', ['{@nickname}', 'Dr.{@nickname}', 'Dr. 博士', 'nickname', 'Dr. nickname', '{@nickname}博士'])
def test_nickname(text):
    assert normalize_nickname(text, 'nickname') == '博士'

def test_unrelated_text_preserved():
    assert spoken_text('Dr. Smith，博士研究生，Mon3tr。') == 'Dr. Smith，博士研究生，Monster。'

@pytest.mark.parametrize('scene', ['act33side_04_end','act33side_05_beg','act33side_07_beg','act33side_10_beg','act33side_st02','act33side_st03'])
def test_previously_failing_scenes(scene):
    assert scene_lines.build(scene)

def test_full_dialogue_mismatch_rejected(monkeypatch):
    original = scene_lines.json.loads
    def corrupt(text):
        obj = original(text)
        for event in obj.get('events', []):
            if event.get('cmd') == 'line':
                event['text'] += '错字'
                break
        return obj
    monkeypatch.setattr(scene_lines.json, 'loads', corrupt)
    with pytest.raises(SystemExit, match='文字對不上'):
        scene_lines.build('act33side_02_beg')
