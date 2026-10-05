"""音軌：用 ffmpeg 生幾個測試音，檢查語音、音樂、音效各自落在時間表指定的位置。"""
import shutil
import subprocess
import wave
from array import array

import pytest

from pipeline.render import audio

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="沒有 ffmpeg")
SR = 8000


def tone(path, seconds, freq=440):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate={SR}",
                    "-t", str(seconds), "-ac", "1", str(path)], check=True)
    return path.name


def level(path, t0, t1):
    """[t0, t1) 秒內的平均絕對振幅（取第一個聲道）。"""
    with wave.open(str(path), "rb") as w:
        ch, sr = w.getnchannels(), w.getframerate()
        w.setpos(int(t0 * sr))
        data = array("h", w.readframes(int((t1 - t0) * sr)))[::ch]
    return sum(abs(x) for x in data) / max(1, len(data))


def seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def schedule(tmp_path, **audio_tracks):
    return {"duration": 6.0, "audio": {"voice": [], "music": [], "sounds": [], **audio_tracks}}


def test_voice_lands_on_schedule(tmp_path):
    name = tone(tmp_path / "v.wav", 0.5)
    s = schedule(tmp_path, voice=[{"line_id": "a", "t": 1.0, "dur": 0.5, "path": name},
                                  {"line_id": "b", "t": 3.0, "dur": 0.5, "path": "missing.wav"}])
    r = audio.render_voice(s, tmp_path, tmp_path / "voice.wav", SR)
    assert r == {"placed": 1, "missing": ["missing.wav"]}
    out = tmp_path / "voice.wav"
    assert seconds(out) == pytest.approx(6.0, abs=0.001)
    assert level(out, 0, 0.99) == 0 and level(out, 1.6, 6) == 0 and level(out, 1.05, 1.45) > 1000


def test_bgm_intro_then_loop_with_fade(tmp_path):
    intro, loop = tone(tmp_path / "i.wav", 1.0, 300), tone(tmp_path / "l.wav", 0.5, 600)
    s = schedule(tmp_path, music=[{"t0": 0.5, "t1": 5.0, "fade_out": 1.0, "volume": 0.5, "intro": "i", "loop": "l",
                                   "intro_path": intro, "loop_path": loop},
                                  {"t0": 5.5, "t1": None, "fade_out": 0, "volume": 1, "intro": None, "loop": "none",
                                   "intro_path": None, "loop_path": None}])
    r = audio.render_bgm(s, tmp_path, tmp_path / "bgm.wav", SR)
    assert r == {"segments": 1, "skipped": ["none"], "ducked_spans": 0}
    out = tmp_path / "bgm.wav"
    assert seconds(out) == pytest.approx(6.0, abs=0.01)
    assert level(out, 0, 0.45) < 5 and level(out, 5.1, 6) < 5
    mid = level(out, 2.5, 3.5)          # 循環段已經重複了好幾輪，還在響
    assert mid > 500 and level(out, 4.7, 4.95) < mid * 0.4      # 結尾淡出


def test_sfx_one_shot_and_loop_envelope(tmp_path):
    hit, wind = tone(tmp_path / "hit.wav", 0.3, 800), tone(tmp_path / "wind.wav", 0.5, 200)
    s = schedule(tmp_path, sounds=[
        {"key": "wind", "path": wind, "t0": 0.0, "t1": 4.0, "loop": True, "channel": "bgs", "src_dur": 0.5,
         "vol": [[0, 0], [0, 0], [1, 0.6], [3, 0.6], [4, 0]]},
        {"key": "hit", "path": hit, "t0": 5.0, "t1": 5.3, "loop": False, "channel": None, "src_dur": 0.3, "vol": [[5.0, 1.0]]},
        {"key": "gone", "path": None, "t0": 2.0, "t1": None, "loop": False, "channel": None, "src_dur": None, "vol": [[2.0, 1.0]]}])
    r = audio.render_sfx(s, tmp_path, tmp_path / "sfx.wav", SR)
    assert r == {"sounds": 2, "skipped": ["gone"]}
    out = tmp_path / "sfx.wav"
    full = level(out, 1.5, 2.5)
    assert level(out, 0, 0.1) < full * 0.2 and full > 300       # 從 0 漸強
    assert level(out, 4.1, 4.9) < 5                             # 停掉後是靜的
    assert level(out, 5.02, 5.28) > 1000 and level(out, 5.4, 6) < 5


def test_final_mix_has_voice_and_optional_bgm(tmp_path):
    for n, f in (("voice", 440), ("sfx", 880), ("bgm", 220)):
        tone(tmp_path / f"{n}.wav", 1.0, f)
    audio.mix_final(tmp_path / "voice.wav", tmp_path / "sfx.wav", tmp_path / "bgm.wav", tmp_path / "mix.wav", SR)
    audio.mix_final(tmp_path / "voice.wav", tmp_path / "sfx.wav", None, tmp_path / "nobgm.wav", SR)
    assert level(tmp_path / "mix.wav", 0.1, 0.9) > level(tmp_path / "nobgm.wav", 0.1, 0.9) > 0


def test_speech_spans_bridge_short_gaps():
    s = {"audio": {"voice": [{"t": 1.0, "dur": 1.0}, {"t": 2.5, "dur": 1.0}, {"t": 6.0, "dur": 0.5}]}}
    assert audio.speech_spans(s, 1.0) == [[1.0, 3.5], [6.0, 6.5]]
    assert audio.speech_spans(s, 0.2) == [[1.0, 2.0], [2.5, 3.5], [6.0, 6.5]]


def test_bgm_gain_and_ducking_under_speech(tmp_path):
    loop = tone(tmp_path / "l.wav", 0.5, 600)
    s = schedule(tmp_path, voice=[{"line_id": "a", "t": 2.0, "dur": 1.5, "path": "x"}],
                 music=[{"t0": 0, "t1": 6.0, "fade_out": 0, "volume": 1, "intro": None, "loop": "l",
                         "intro_path": None, "loop_path": loop}])
    audio.render_bgm(s, tmp_path, tmp_path / "raw.wav", SR)
    duck = {"duck_db": 6, "attack_s": 0.25, "release_s": 0.5, "bridge_s": 1.0}
    r = audio.render_bgm(s, tmp_path, tmp_path / "bgm.wav", SR, gain_db=-12, duck=duck)
    assert r["ducked_spans"] == 1
    raw, away, under = level(tmp_path / "raw.wav", 0.2, 1.2), level(tmp_path / "bgm.wav", 0.2, 1.2), level(tmp_path / "bgm.wav", 2.2, 3.3)
    assert away / raw == pytest.approx(10 ** (-12 / 20), rel=0.05)      # 沒人說話：只有固定的 −12 dB
    assert under / away == pytest.approx(10 ** (-6 / 20), rel=0.05)     # 說話時再退 6 dB
    assert level(tmp_path / "bgm.wav", 4.5, 5.8) == pytest.approx(away, rel=0.05)   # 說完後回來
