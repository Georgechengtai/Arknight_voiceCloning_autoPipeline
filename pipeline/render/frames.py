"""(5b) 逐幀截圖：Playwright 開渲染器頁面，對每一幀呼叫 seek 後截圖，直接餵給 ffmpeg 編碼。"""
from __future__ import annotations

import functools
import http.server
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ..common.paths import ROOT

PAGE = "pipeline/render/web/index.html"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@contextmanager
def serve(root: Path = ROOT):
    """把倉庫根目錄開成本機網站（只聽 127.0.0.1），回傳網址前綴。"""
    handler = functools.partial(_Quiet, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def preview_url(base: str, schedule_rel: str, audio_rel: str | None = None) -> str:
    """給人看的預覽頁網址（有拖曳條與播放鍵）。路徑都相對於倉庫根目錄。"""
    return f"{base}/{PAGE}?preview=1&schedule=/{schedule_rel}" + (f"&audio=/{audio_rel}" if audio_rel else "")


@contextmanager
def open_renderer(schedule: dict):
    """開好頁面、把時間表交給渲染器並等素材載完。yield (page, 沒載到的素材清單)。"""
    from playwright.sync_api import sync_playwright

    with serve() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": schedule["width"], "height": schedule["height"]},
                                device_scale_factor=1)
        page.goto(f"{base}/{PAGE}")
        page.evaluate("s => renderer.load(s, '/')", schedule)
        try:
            yield page, page.evaluate("renderer.missing")
        finally:
            browser.close()


def encode_frames(schedule: dict, out_path: Path, encode: dict, *,
                  start: int = 0, end: int | None = None, keep_frames: Path | None = None,
                  progress=None) -> dict:
    """畫第 start 到 end−1 幀，編成無聲的 H.264 影片。回傳統計。"""
    fps = schedule["fps"]
    end = schedule["frames"] if end is None else min(end, schedule["frames"])
    fmt = encode.get("frame_format", "png")
    shot = {"type": "png"} if fmt == "png" else {"type": "jpeg", "quality": 95}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if keep_frames:
        keep_frames.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps),
         "-c:v", "png" if fmt == "png" else "mjpeg", "-i", "-",
         "-c:v", "libx264", "-preset", str(encode["preset"]), "-crf", str(encode["crf"]),
         "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(out_path)],
        stdin=subprocess.PIPE)
    t_begin = time.time()
    drawn = 0
    with open_renderer(schedule) as (page, missing):
        buf = None
        for n in range(start, end):
            changed = page.evaluate("t => renderer.seek(t)", n * 1000.0 / fps)
            if changed or buf is None:
                buf = page.screenshot(**shot)
                drawn += 1
            ff.stdin.write(buf)
            if keep_frames:
                (keep_frames / f"{n:06d}.{fmt}").write_bytes(buf)
            if progress and (n - start) % 300 == 0:
                progress(n - start, end - start, time.time() - t_begin)
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg 編碼畫面失敗")
    return {"frames": end - start, "drawn": drawn, "seconds": round(time.time() - t_begin, 1), "missing": missing}


def _encode_part(job: tuple) -> dict:
    schedule, out_path, encode, start, end = job
    return encode_frames(schedule, Path(out_path), encode, start=start, end=end)


def encode_parallel(schedule: dict, out_path: Path, encode: dict, workers: int) -> dict:
    """把全片切成 workers 段同時畫（seek 是確定性的，各段互不相干），最後無損接起來。"""
    import multiprocessing as mp

    total = schedule["frames"]
    fps = schedule["fps"]
    step = -(-total // workers)
    step += (-step) % fps     # 每段整數秒，接縫落在關鍵幀
    parts = [(s, min(s + step, total)) for s in range(0, total, step)]
    tmp = out_path.parent / (out_path.stem + "_parts")
    tmp.mkdir(parents=True, exist_ok=True)
    jobs = [(schedule, str(tmp / f"{k:02d}.mp4"), encode, s, e) for k, (s, e) in enumerate(parts)]
    t_begin = time.time()
    with mp.get_context("spawn").Pool(len(jobs)) as pool:
        stats = pool.map(_encode_part, jobs)
    (tmp / "list.txt").write_text("".join(f"file '{Path(j[1]).name}'\n" for j in jobs), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-c", "copy", "-movflags", "+faststart", str(out_path)], check=True)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return {"frames": total, "drawn": sum(s["drawn"] for s in stats), "seconds": round(time.time() - t_begin, 1),
            "missing": stats[0]["missing"], "workers": len(jobs)}
