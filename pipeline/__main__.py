"""CLI 入口：python -m pipeline <子命令>"""
from __future__ import annotations

import argparse
import sys

from . import casting, gamedata, parse
from .common.paths import OUT_DIR, ROOT
from .common.settings import load_settings
from .render import cli as render_cli


def _scenes(args) -> list[gamedata.Scene]:
    if args.scene:
        return [gamedata.find_scene(args.scene)]
    return gamedata.list_scenes(args.act)


def cmd_fetch_gamedata(args) -> int:
    r = gamedata.fetch_gamedata(args.act, force=args.force)
    print(f"{r['act']}：{r['scenes']} 場；新下載 {r['downloaded']} 個檔，沿用快取 {r['cached']} 個"
          f" → {gamedata.STORY_DIR.parent.relative_to(ROOT)}")
    return 0


def cmd_parse(args) -> int:
    total = {"lines": 0, "dialogue": 0, "narration": 0, "subtitle": 0, "planning_count": 0}
    scenes = _scenes(args)
    for scene in scenes:
        tl = parse.parse_scene(scene)
        path = parse.write_timeline(tl)
        st = tl["stats"]
        for k in total:
            total[k] += st[k]
        unknown = sorted({e["cmd"] for e in tl["events"] if "raw" in e})
        print(f"{scene.scene_id:<22} {scene.story_code:<8} {scene.avg_tag}  事件 {st['events']:>4}  "
              f"句 {st['lines']:>3}（對白 {st['dialogue']} 旁白 {st['narration']} 字幕 {st['subtitle']}）"
              f"  規劃口徑 {st['planning_count']:>3}  → {path.relative_to(ROOT)}"
              + (f"  未知指令：{', '.join(unknown)}" if unknown else ""))
    if len(scenes) > 1:
        print(f"合計 {len(scenes)} 場：句 {total['lines']}（對白 {total['dialogue']} 旁白 {total['narration']} "
              f"字幕 {total['subtitle']}）；規劃口徑 {total['planning_count']}")
    return 0


def cmd_speakers(args) -> int:
    timelines = [parse.parse_scene(s) for s in _scenes(args)]
    rows = casting.collect_speakers(timelines)
    path = casting.write_speakers_csv(rows, OUT_DIR / (args.scene or args.act) / "speakers.csv")
    named = [r for r in rows if not r["speaker"].startswith("（")]
    print(f"{len(named)} 個有名字的說話者（另有旁白／字幕列）→ {path.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    default_act = load_settings()["parse"]["default_act"]
    p = argparse.ArgumentParser(prog="python -m pipeline", description="明日方舟劇情配音管線")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch-gamedata", help="下載 excel 表與指定活動的全部劇情腳本（有快取就跳過）")
    f.add_argument("--act", default=default_act)
    f.add_argument("--force", action="store_true", help="忽略快取重新下載")
    f.set_defaults(func=cmd_fetch_gamedata)

    for name, func, helptext in (
        ("parse", cmd_parse, "腳本 → out/<scene>/timeline.json"),
        ("speakers", cmd_speakers, "說話者統計 → out/<scene 或 act>/speakers.csv"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--scene", help="單一場景，如 act33side_st01；省略則處理整個活動")
        s.add_argument("--act", default=default_act)
        s.set_defaults(func=func)

    r = sub.add_parser("render", help="timeline＋語音清單＋素材清單 → out/<scene>/<scene>.mp4 與 _nobgm.mp4")
    r.add_argument("--scene", required=True)
    r.add_argument("--voice-manifest", help="語音清單的路徑；省略則用 out/<scene>/voice_manifest.json")
    r.add_argument("--tag", default="", help="這次輸出的標記：工作檔與影片改放 out/<scene>/render-<tag>/（佔位清單會自動標 placeholder）")
    r.add_argument("--intro-card", action="store_true", help="片頭加「本片語音為 AI 生成」字卡")
    r.add_argument("--no-bgm", action="store_true", help="只出沒有背景音樂的版本（預設兩個版本都出）")
    r.add_argument("--schedule-only", action="store_true", help="只算時間表")
    r.add_argument("--audio-only", action="store_true", help="只做時間表與音軌，不畫畫面")
    r.add_argument("--workers", type=int, default=1, help="同時開幾個瀏覽器分段畫")
    r.add_argument("--keep-frames", action="store_true", help="把每一幀另存成圖檔（除錯用）")
    r.add_argument("--force", action="store_true", help="直接覆蓋同名的舊影片（預設先把舊的改名留著）")
    r.set_defaults(func=render_cli.cmd_render)

    rp = sub.add_parser("render-placeholder", help="語音清單還沒出來時：生一份佔位清單到 out/<scene>/placeholder/")
    rp.add_argument("--scene", required=True)
    rp.add_argument("--silent", action="store_true", help="不用 say，全部用靜音佔位")
    rp.set_defaults(func=render_cli.cmd_render_placeholder)

    rv = sub.add_parser("render-preview", help="開本機預覽頁（拖曳條＋播放），看時間表畫出來的樣子")
    rv.add_argument("--scene", required=True)
    rv.add_argument("--tag", default="")
    rv.set_defaults(func=render_cli.cmd_render_preview)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as e:
        print(f"錯誤：{e.args[0] if e.args else e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
