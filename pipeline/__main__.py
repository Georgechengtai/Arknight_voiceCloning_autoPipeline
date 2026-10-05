"""CLI 入口：python -m pipeline <子命令>"""
from __future__ import annotations

import argparse
import sys

from . import casting, gamedata, parse
from .common.paths import OUT_DIR, ROOT
from .common.settings import load_settings


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

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as e:
        print(f"錯誤：{e.args[0] if e.args else e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
