import array
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import voice_manifest as vm  # noqa: E402

SR = vm.SR


def tone(sec, amp=8000):
    return array.array("h", (int(amp * math.sin(2 * math.pi * 220 * i / SR)) for i in range(int(sec * SR))))


def silence(sec):
    return array.array("h", bytes(2 * int(sec * SR)))


def test_cut_between_two_lines_keeps_the_pause_as_gap():
    a = tone(1.0) + silence(0.5) + tone(1.0)
    lv = vm.levels(a)
    cuts = vm.find_cuts(lv, [(0, 950), (1550, 2500)], max(lv))
    assert cuts[0]["how"] == "ok" and 100 < cuts[0]["frame"] < 150
    (s1, lead1), (s2, lead2) = vm.cut_block(a, lv, cuts)
    assert lead1 == 0
    assert abs(len(s1) / SR - (1.0 + vm.TAIL_KEEP)) < 0.03          # 句尾留 0.08 秒
    assert abs(len(s2) / SR - 1.0) < 0.03
    assert abs(len(s1) / SR + lead2 + len(s2) / SR - 2.5) < 0.001   # 接回去與原本一樣長
    assert s1[-1] == 0                                              # 淡出到零


def test_unrecognised_line_is_cut_at_the_silence_next_to_its_neighbour():
    # 咳嗽（沒被認出字）＋短停頓＋咳嗽＋長停頓＋下一句
    a = tone(0.3) + silence(0.2) + tone(0.3) + silence(0.6) + tone(1.0)
    lv = vm.levels(a)
    cuts = vm.find_cuts(lv, [None, (1450, 2400)], max(lv))
    assert "前一句沒被認出來" in cuts[0]["how"]
    assert 80 < cuts[0]["frame"] < 140                              # 切在下一句開口前那段安靜，不是兩聲咳嗽之間


def test_no_silence_between_lines_is_flagged():
    a = tone(2.0)
    lv = vm.levels(a)
    cuts = vm.find_cuts(lv, [(0, 1000), (1000, 2000)], max(lv))
    assert cuts[0]["how"] == "兩句之間沒有安靜處"


def test_timeline_follows_gap_rules():
    m = {"lines": [
        {"line_id": "x_0001", "speaker": "甲", "path": "a", "dur": 2.0, "gap_before": None},
        {"line_id": "x_0002", "speaker": "甲", "path": "b", "dur": 1.0, "gap_before": None},
        {"line_id": "x_0003", "speaker": "乙", "path": None, "dur": 0, "gap_before": None},
        {"line_id": "x_0004", "speaker": "乙", "path": "c", "dur": 1.0, "gap_before": None},
        {"line_id": "x_0005", "speaker": "乙", "path": None, "dur": 0, "gap_before": None, "hold": 0.4},
        {"line_id": "x_0006", "speaker": "乙", "path": "d", "dur": 1.0, "gap_before": 0.25},
    ]}
    tl, total = vm.timeline(m)
    starts = [round(s, 2) for _, s in tl]
    # 第一句 0；同一人 0.8；無聲行 1.0 之後換人 0.6（看的是上一個有聲音的說話者）；hold 與 gap_before 照給的值
    assert starts == [0.0, 2.8, 3.8, 5.4, 6.4, 7.05]
    assert round(total, 2) == 8.05
