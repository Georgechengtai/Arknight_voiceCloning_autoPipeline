"""`python -m pipeline render` 與 `render-placeholder` 的實作。"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from ..common.paths import OUT_DIR, ROOT
from ..common.settings import load_settings
from . import audio, frames, placeholder
from .schedule import build_schedule


def _rel(p: Path) -> str:
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def _load(path: Path, what: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"找不到{what}：{_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_render_placeholder(args) -> int:
    scene_dir = OUT_DIR / args.scene
    lines = _load(scene_dir / "lines.json", "逐句清單（先跑 python tools/scene_lines.py）")
    out_dir = scene_dir / "placeholder"
    m = placeholder.build_placeholder(lines, args.scene, out_dir, use_say=not args.silent)
    voiced = [l for l in m["lines"] if l["path"]]
    print(f"{args.scene}：佔位語音清單 {len(m['lines'])} 行（有聲 {len(voiced)} 行，共 {sum(l['dur'] for l in voiced):.0f} 秒）"
          f" → {_rel(out_dir / 'voice_manifest.json')}")
    return 0


def cmd_render(args) -> int:
    settings = load_settings()
    cfg = settings["render"]
    scene_dir = OUT_DIR / args.scene
    timeline = _load(scene_dir / "timeline.json", "時間軸（先跑 python -m pipeline parse）")
    voice_path = Path(args.voice_manifest) if args.voice_manifest else scene_dir / "voice_manifest.json"
    if not voice_path.is_absolute():
        voice_path = ROOT / voice_path
    voice = _load(voice_path, "語音清單（還沒有的話先跑 python -m pipeline render-placeholder，再用 --voice-manifest 指過去）")
    assets_path = scene_dir / "assets_manifest.json"
    assets = json.loads(assets_path.read_text(encoding="utf-8")) if assets_path.exists() else None
    if assets is None:
        print("沒有素材清單，背景與立繪全部以色塊佔位、音樂音效靜音")

    tag = args.tag or ("placeholder" if voice.get("placeholder") else "")
    work = scene_dir / (f"render-{tag}" if tag else "render")
    final_dir = work if tag else scene_dir
    work.mkdir(parents=True, exist_ok=True)

    schedule = build_schedule(timeline, voice, assets, settings, voice_dir=_rel(voice_path.parent),
                              intro_card=args.intro_card)
    schedule_path = work / "schedule.json"
    schedule_path.write_text(json.dumps(schedule, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    m, s = divmod(schedule["duration"], 60)
    print(f"時間表：{len(schedule['events'])} 個事件、{len(schedule['lines'])} 行文字，全長 {int(m)} 分 {s:.0f} 秒"
          f"（{schedule['frames']} 幀）→ {_rel(schedule_path)}")
    for w in schedule["warnings"]:
        print(f"  注意：{w}")
    if args.schedule_only:
        return 0

    acfg = cfg["audio"]
    sr = acfg["sample_rate"]
    v = audio.render_voice(schedule, ROOT, work / "voice.wav", sr)
    b = audio.render_bgm(schedule, ROOT, work / "bgm.wav", sr, acfg["bgm_gain_db"], acfg.get("duck"))
    f = audio.render_sfx(schedule, ROOT, work / "sfx.wav", sr, acfg["sfx_gain_db"])
    print(f"音軌：語音 {v['placed']} 句、音樂 {b['segments']} 段、音效 {f['sounds']} 個 → {_rel(work)}/voice.wav、bgm.wav、sfx.wav")
    for name, lst in (("語音", v["missing"]), ("音樂", b["skipped"]), ("音效", f["skipped"])):
        if lst:
            print(f"  注意：缺{name}檔，已靜音：{', '.join(map(str, lst))}")
    audio.mix_final(work / "voice.wav", work / "sfx.wav", work / "bgm.wav", work / "mix.wav", sr)
    audio.mix_final(work / "voice.wav", work / "sfx.wav", None, work / "mix_nobgm.wav", sr)
    spans = [[x["t"], x["t"] + x["dur"]] for x in schedule["audio"]["voice"]]
    lv, lb, ls = (audio.loudness(work / n, spans) for n in ("voice.wav", "bgm.wav", "sfx.wav"))
    if lv is not None and lb is not None:
        report = {"voice_lufs": lv, "bgm_lufs_under_speech": lb, "sfx_lufs_under_speech": ls,
                  "bgm_below_voice_db": round(lv - lb, 1), "ducked_spans": b["ducked_spans"]}
        (work / "loudness.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"響度（只量有人說話的時候）：語音 {lv} LUFS、音樂 {lb} LUFS（比語音低 {lv - lb:.1f} dB）、音效 {ls} LUFS")
    if args.audio_only:
        print(f"只做音軌：{_rel(work)}/mix.wav、mix_nobgm.wav")
        return 0

    encode = dict(cfg["encode"])
    video = work / "video.mp4"
    t0 = time.time()

    def progress(done: int, total: int, elapsed: float) -> None:
        if done:
            print(f"  畫面 {done}/{total} 幀，已用 {elapsed:.0f} 秒，約剩 {elapsed / done * (total - done):.0f} 秒", flush=True)

    if args.workers > 1:
        st = frames.encode_parallel(schedule, video, encode, args.workers)
    else:
        st = frames.encode_frames(schedule, video, encode, progress=progress,
                                  keep_frames=(work / "frames") if args.keep_frames else None)
    print(f"畫面：{st['frames']} 幀（其中 {st['drawn']} 幀有變化、實際截圖），用時 {time.time() - t0:.0f} 秒")
    if st["missing"]:
        print(f"  注意：{len(st['missing'])} 個圖檔載入失敗，以佔位顯示：{', '.join(st['missing'][:5])}")

    name = args.scene
    outputs = [(work / "mix.wav", final_dir / f"{name}.mp4"), (work / "mix_nobgm.wav", final_dir / f"{name}_nobgm.mp4")]
    if args.no_bgm:
        outputs = outputs[1:]
    for mix, out in outputs:
        if out.exists() and not args.force:
            keep = out.with_name(f"{out.stem}.{time.strftime('%Y%m%d-%H%M%S', time.localtime(out.stat().st_mtime))}{out.suffix}")
            shutil.move(out, keep)      # 不覆蓋舊成品：先改名留著
            print(f"  舊的 {out.name} 已改名為 {keep.name}")
        audio.mux(video, mix, out, encode["audio_bitrate"])
        print(f"完成 → {_rel(out)}")
    return 0


def cmd_render_preview(args) -> int:
    scene_dir = OUT_DIR / args.scene
    work = scene_dir / (f"render-{args.tag}" if args.tag else "render")
    if not (work / "schedule.json").exists():
        raise FileNotFoundError(f"找不到 {_rel(work / 'schedule.json')}，請先跑 python -m pipeline render --scene {args.scene} --audio-only")
    mix = work / "mix.wav"
    with frames.serve() as base:
        print("用瀏覽器打開（Ctrl-C 結束）：")
        print(frames.preview_url(base, _rel(work / "schedule.json"), _rel(mix) if mix.exists() else None))
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
