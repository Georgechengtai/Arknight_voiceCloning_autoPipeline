"""渲染器頁面：同一時刻畫兩次要逐像素相同；三個時刻與基準圖比對（容忍 1% 的像素不同）。

測試用的時間表不含任何遊戲素材（背景、立繪都是缺素材時的色塊佔位），所以基準圖可以入庫。
重新產生基準圖：UPDATE_BASELINE=1 python -m pytest tests/test_render_web.py
"""
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from pipeline.render import frames  # noqa: E402
from tests.test_schedule import Script  # noqa: E402

BASELINE = Path(__file__).parent / "baseline"
MOMENTS = {"intro": 1.0, "dialog": 7.2, "sticker": 12.5}

# 在頁面裡把目前畫面與基準圖逐像素比較，回傳不同的比例（任一色版差超過 24 才算不同）
DIFF_JS = """async (url) => {
  const img = new Image(); img.src = url; await img.decode();
  const c = document.getElementById('stage');
  if (img.naturalWidth !== c.width || img.naturalHeight !== c.height) return 1;
  const o = new OffscreenCanvas(c.width, c.height).getContext('2d');
  o.drawImage(img, 0, 0);
  const a = o.getImageData(0, 0, c.width, c.height).data;
  const b = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let bad = 0;
  for (let i = 0; i < a.length; i += 4)
    if (Math.abs(a[i] - b[i]) > 24 || Math.abs(a[i+1] - b[i+1]) > 24 || Math.abs(a[i+2] - b[i+2]) > 24) bad++;
  return bad / (a.length / 4);
}"""


def demo_schedule():
    return (Script()
            .cmd("background", image="bg_demo")
            .cmd("charslot", slot="l", name="npc_a#1$1", group="npc_a", face=1, body=1, duration=1)
            .cmd("charslot", slot="r", name="npc_b#1$1", group="npc_b", face=1, body=1, focus="r")
            .cmd("delay", time=1.5)
            .say("甲", 3.0, text="这是一句用来测试对话框排版的台词，长度要超过一行，才看得出换行的位置对不对。")
            .cmd("camerashake", duration=0.5, xstrength=30, ystrength=30, vibrato=30, fadeout=True)
            .cmd("dialog").cmd("charslot")
            .cmd("blocker", a=0.6, fadetime=1, block=True)
            .card("st1", "第一张字卡，", 2.0, x=300, y=370, width=700, alignment="center", size=24, delay=0.04)
            .card("st2", "第二张字卡。", 2.0, x=300, y=410, width=700, alignment="center", size=24, delay=0.04)
            .cmd("sticker", id="st1", duration=1).cmd("sticker", id="st2", duration=1).cmd("delay", time=1.5)
            .build(intro_card=True))


@pytest.fixture(scope="module")
def page():
    try:
        with frames.open_renderer(demo_schedule()) as (pg, missing):
            assert missing == []
            yield pg
    except Exception as e:      # 沒裝瀏覽器等環境問題：跳過而不是失敗
        if "Executable doesn't exist" in str(e):
            pytest.skip("Playwright 的 Chromium 沒有安裝")
        raise


def shot(page, t):
    page.evaluate("t => renderer.seek(t)", t * 1000)
    return page.screenshot(type="png")


def test_seek_is_deterministic(page):
    for t in (0.2, 6.03, 9.31, 11.9):       # 淡入中、打字中、震動中、字卡中
        first = shot(page, t)
        shot(page, 14.0)                    # 中間跳到別處再跳回來
        assert shot(page, t) == first


def test_unchanged_state_is_not_redrawn(page):
    page.evaluate("renderer.seek(8500)")
    assert page.evaluate("renderer.seek(8500)") is False        # 同一刻
    assert page.evaluate("renderer.seek(8533.3)") is False      # 字打完後的靜止畫面
    assert page.evaluate("renderer.seek(5800)") is True


def test_typewriter_and_layers(page):
    st = page.evaluate("renderer.stateAt(5500 + 100)")          # 對白開始後 0.1 秒：每字 0.03 秒
    assert st["dialog"]["name"] == "甲" and st["dialog"]["n"] == 4
    assert [s["dim"] for s in st["sprites"]] == [0.6, 1] and st["bg"]["src"] is None
    assert page.evaluate("renderer.stateAt(1000).intro") == 1


@pytest.mark.parametrize("name", MOMENTS)
def test_matches_baseline(page, name):
    png = shot(page, MOMENTS[name])
    path = BASELINE / f"render_{name}.png"
    if os.environ.get("UPDATE_BASELINE"):
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(png)
    if not path.exists():
        pytest.skip(f"沒有基準圖 {path.name}")
    base = page.url.split("/pipeline/")[0]
    ratio = page.evaluate(DIFF_JS, f"{base}/tests/baseline/{path.name}")
    assert ratio <= 0.01, f"與基準圖有 {ratio:.2%} 的像素不同"
