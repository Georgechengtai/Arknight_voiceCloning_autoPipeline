"""Kengxxiao/ArknightsGameData 的下載與場景索引。只取 zh_CN（D2）。"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import certifi

from .common.paths import EXCEL_DIR, STORY_DIR
from .common.settings import load_settings

# python.org 版的 macOS Python 不帶系統根憑證，改用 certifi 的
_SSL = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class Scene:
    scene_id: str        # act33side_st01
    act: str             # act33side
    story_code: str      # BB-ST-1
    story_name: str      # 未完成的告别
    avg_tag: str         # 幕间 / 行动前 / 行动后
    story_txt: str       # activities/act33side/level_act33side_st01

    @property
    def path(self) -> Path:
        return STORY_DIR / f"{self.story_txt}.txt"


def scene_id_from_story_txt(story_txt: str) -> str:
    return story_txt.rsplit("/", 1)[-1].removeprefix("level_")


def _download(url: str, dest: Path, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120, context=_SSL) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
            tmp.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries:
                raise RuntimeError(f"下載失敗 {url}: {e}") from e
            time.sleep(2 * attempt)


def _fetch(url: str, dest: Path, force: bool) -> bool:
    """回傳是否真的下載了（False = 用快取）。"""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return False
    print(f"  下載 {dest.name}", file=sys.stderr)
    _download(url, dest)
    return True


def fetch_gamedata(act: str, force: bool = False) -> dict:
    cfg = load_settings()["gamedata"]
    base = cfg["base_url"].rstrip("/")
    downloaded = cached = 0
    for table in cfg["excel_tables"]:
        got = _fetch(f"{base}/excel/{table}.json", EXCEL_DIR / f"{table}.json", force)
        downloaded += got
        cached += not got
    scenes = list_scenes(act)
    for s in scenes:
        got = _fetch(f"{base}/story/{s.story_txt}.txt", s.path, force)
        downloaded += got
        cached += not got
    return {"act": act, "scenes": len(scenes), "downloaded": downloaded, "cached": cached}


def _review_table() -> dict:
    path = EXCEL_DIR / "story_review_table.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}，請先執行 python -m pipeline fetch-gamedata")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _scene(act: str, e: dict) -> Scene:
    return Scene(
        scene_id=scene_id_from_story_txt(e["storyTxt"]),
        act=act,
        story_code=e["storyCode"],
        story_name=e["storyName"],
        avg_tag=e["avgTag"],
        story_txt=e["storyTxt"],
    )


def list_scenes(act: str) -> list[Scene]:
    table = _review_table()
    if act not in table:
        raise KeyError(f"story_review_table 中沒有活動 {act}")
    entries = sorted(table[act]["infoUnlockDatas"], key=lambda e: e["storySort"])
    return [_scene(act, e) for e in entries]


def find_scene(scene_id: str) -> Scene:
    for act, entry in _review_table().items():
        for e in entry.get("infoUnlockDatas", []):
            if scene_id_from_story_txt(e["storyTxt"]) == scene_id:
                return _scene(act, e)
    raise KeyError(f"story_review_table 中沒有場景 {scene_id}")
