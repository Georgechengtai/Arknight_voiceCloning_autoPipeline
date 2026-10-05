"""(2) 素材解析與下載：timeline.json → assets/ ＋ out/<scene>/assets_manifest.json。

來源優先序（docs/02-data-sources.md §3–3c）：
- 背景、插圖、立繪：fexli/ArknightsResource → PRTS 索引（Data_Image / Data_Link / Data_Char）
- BGM、音效：PRTS Data_Audio → torappu.prts.wiki → Aceship/Arknight-voices（WAV）

上半部是純函式（鍵解析，可單測），下半部才碰網路與檔案。
"""
from __future__ import annotations

import json
import re
import ssl
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import certifi

from .common.paths import CACHE_DIR, OUT_DIR, ROOT
from .common.settings import load_settings

_SSL = ssl.create_default_context(cafile=certifi.where())

FEXLI_RAW = "https://raw.githubusercontent.com/fexli/ArknightsResource/main"
ACESHIP_RAW = "https://raw.githubusercontent.com/Aceship/Arknight-voices/main"
PRTS_RAW = "https://prts.wiki/index.php?title={title}&action=raw"
TORAPPU = "https://torappu.prts.wiki/assets"

# 不是圖檔的立繪名：遊戲用它清空插入框
EMPTY_SPRITES = {"char_empty"}


# ---------------------------------------------------------------- 需求收集（純函式）

@dataclass
class Requirements:
    backgrounds: set[str] = field(default_factory=set)
    images: set[str] = field(default_factory=set)
    sprites: set[str] = field(default_factory=set)      # 腳本裡的完整名字，如 avg_003_kalts_1#4$1
    music: set[str] = field(default_factory=set)
    sounds: set[str] = field(default_factory=set)
    effects: set[str] = field(default_factory=set)      # 粒子／畫面特效：沒有可下載的檔，由渲染器自行實作

    def update(self, other: "Requirements") -> None:
        for name in self.__dataclass_fields__:
            getattr(self, name).update(getattr(other, name))


def collect_requirements(timeline: dict) -> Requirements:
    """掃過 timeline 的事件，列出這一場需要的每個素材鍵。"""
    req = Requirements()
    for e in timeline["events"]:
        cmd, a = e["cmd"], e.get("args") or {}
        if cmd == "background" and a.get("image"):
            req.backgrounds.add(a["image"])
        elif cmd == "interlude" and a.get("name"):       # 過場遮罩裡露出的也是背景圖
            req.backgrounds.add(a["name"])
        elif cmd == "gridbg" and a.get("imagegroup"):    # 多張背景拼成的長卷，以 / 分隔
            req.backgrounds.update(p for p in a["imagegroup"].split("/") if p)
        elif cmd in ("image", "imagetween", "imgeffect") and a.get("image"):
            req.images.add(a["image"])
        elif cmd in ("charslot", "charactercutin") and a.get("name"):
            if a["name"] not in EMPTY_SPRITES:
                req.sprites.add(a["name"])
        elif cmd == "character":                          # 舊語法：name、name2、name3
            req.sprites.update(v for k, v in a.items()
                               if re.fullmatch(r"name\d?", k) and v and v not in EMPTY_SPRITES)
        elif cmd == "playmusic":
            req.music.update(v for v in (a.get("intro"), a.get("key")) if v)
        elif cmd == "playsound" and a.get("key"):
            req.sounds.add(a["key"])
        if cmd in ("effect", "bgeffect", "imgeffect", "cameraeffect", "warp"):
            name = a.get("name") or a.get("effect")
            if name:
                req.effects.add(f"{cmd}:{name}")
    return req


# ---------------------------------------------------------------- 鍵解析（純函式）

def split_sprite_name(name: str) -> tuple[str, str | None, str | None]:
    """'avg_npc_1305_1#8$1' → ('avg_npc_1305_1', '8', '1')；face、body 可省略。"""
    m = re.fullmatch(r"([^#$]+)(?:#([^$]+))?(?:\$(.+))?", name)
    if not m:
        raise ValueError(f"看不懂的立繪名：{name}")
    return m.group(1), m.group(2), m.group(3)


def fexli_sprite_item(name: str, summary: dict) -> tuple[str | None, str | None]:
    """腳本立繪名 → (fexli summary.json 裡的變體鍵, 警告)。組不存在回傳 (None, None)。

    變體鍵的樣子：'avg_003_kalts_1#4$1'、舊式 NPC 'avg_npc_053#053'、'npc_10002#1'、
    以及不帶後綴的本體 'avg_003_kalts_1'。
    """
    group, face, body = split_sprite_name(name)
    entry = summary.get(group)
    if not entry or not entry.get("items"):
        return None, None
    items = list(entry["items"])
    if face is None and body is None:
        # 本體：有同名項就用它，否則取該組第一個變體（舊式 NPC 只有一個）
        return (group if group in items else items[0]), None
    exact = f"{group}#{face or 1}${body or 1}"
    for cand in (name, exact, f"{group}#{face}" if face else None):
        if cand and cand in items:
            return cand, None
    return items[0], f"立繪 {name} 沒有對應變體，改用 {items[0]}"


def fexli_sprite_url(item: str) -> str:
    return f"{FEXLI_RAW}/avgs/npcs/{fexli_file_key(item)}.png"


def fexli_file_key(item: str) -> str:
    """變體鍵 → 檔名（# 與 $ 都換成 _）。"""
    return item.replace("#", "_").replace("$", "_")


def prts_sprite_key(name: str, link: dict, char: dict) -> tuple[str | None, str | None]:
    """腳本立繪名 → (PRTS Data_Char 的鍵, 警告)。找不到回傳 (None, None)。"""
    group, face, body = split_sprite_name(name)
    entry = link.get(group) or link.get(group + "_1")
    if not entry:
        return None, None
    names = [x["name"] for x in entry.get("array", [])]
    want = f"{group}-{face or 1}${body or 1}"
    for cand in (want, f"{group}${body or 1}", group, group + "_1"):
        if cand in names and cand in char:
            return cand, None
    for cand in names:
        if cand in char:
            return cand, f"立繪 {name} 在 PRTS 沒有對應變體，改用 {cand}"
    return None, None


def audio_index_path(key: str, audio_index: dict) -> str | None:
    """音訊鍵 → Data_Audio 的相對路徑。鍵的大小寫以索引為準，對不上時不分大小寫再找一次。"""
    key = key.lstrip("$")
    if key in audio_index:
        return audio_index[key]
    low = key.lower()
    for k, v in audio_index.items():
        if k.lower() == low:
            return v
    return None


def torappu_audio_url(index_path: str, ext: str = "mp3") -> str:
    """2026-10-05 實測：路徑必須整條小寫，Sound_Beta_2 換成 audio；保留大小寫會 404。"""
    return f"{TORAPPU}/{index_path.lower().replace('sound_beta_2', 'audio')}.{ext}"


def aceship_audio_url(index_path: str) -> str:
    rel = index_path.lower().removeprefix("sound_beta_2/")
    return f"{ACESHIP_RAW}/{rel}.wav"


def parse_kv_index(text: str) -> dict[str, str]:
    """Data_Image / Data_Char：每行 'key,url'。"""
    out = {}
    for line in text.splitlines():
        key, sep, url = line.partition(",")
        if sep and url.startswith("http"):
            out[key.strip()] = url.strip()
    return out


@dataclass
class Indexes:
    fexli_summary: dict
    prts_image: dict
    prts_char: dict
    prts_link: dict
    prts_audio: dict


@dataclass
class Candidate:
    source: str          # fexli | prts | aceship
    url: str


@dataclass
class Item:
    kind: str            # backgrounds | images | sprites | music | sounds
    key: str             # 腳本裡的名字
    path: str            # 相對於倉庫根目錄；副檔名在下載後依實際來源確定
    candidates: list[Candidate]
    extra: dict = field(default_factory=dict)
    warning: str | None = None


def _quote(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?=&%")


def resolve(req: Requirements, idx: Indexes) -> list[Item]:
    """每個需要的素材 → 依優先序排好的候選網址。沒有任何候選的項目 candidates 為空。"""
    items: list[Item] = []
    for name in sorted(req.backgrounds):
        cands = [Candidate("fexli", f"{FEXLI_RAW}/avgs/bg/{name}.png")]
        if url := idx.prts_image.get("bg_" + name):
            cands.append(Candidate("prts", _quote(url)))
        items.append(Item("backgrounds", name, f"assets/bg/{name}.png", cands))
    for name in sorted(req.images):
        cands = [Candidate("fexli", f"{FEXLI_RAW}/avgs/{name}.png")]
        if url := idx.prts_image.get(name):
            cands.append(Candidate("prts", _quote(url)))
        items.append(Item("images", name, f"assets/image/{name}.png", cands))
    for name in sorted(req.sprites):
        group = split_sprite_name(name)[0]
        cands, warnings = [], []
        item, w1 = fexli_sprite_item(name, idx.fexli_summary)
        if item:
            cands.append(Candidate("fexli", fexli_sprite_url(item)))
            warnings.append(w1)
        pkey, w2 = prts_sprite_key(name, idx.prts_link, idx.prts_char)
        if pkey:
            cands.append(Candidate("prts", _quote(idx.prts_char[pkey])))
            if not item:
                warnings.append(w2)
        geo = idx.fexli_summary.get(group) or idx.prts_link.get(group) or idx.prts_link.get(group + "_1") or {}
        file_key = fexli_file_key(item) if item else fexli_file_key(name)
        items.append(Item("sprites", name, f"assets/char/{file_key}.png", cands,
                          extra={"group": group, "pos": geo.get("pos"), "size": geo.get("size")},
                          warning=next((w for w in warnings if w), None)))
    for kind, sub, keys in (("music", "music", req.music), ("sounds", "sound", req.sounds)):
        for key in sorted(keys):
            ipath = audio_index_path(key, idx.prts_audio)
            cands = []
            if ipath:
                cands = [Candidate("prts", torappu_audio_url(ipath)), Candidate("aceship", aceship_audio_url(ipath))]
            items.append(Item(kind, key, f"assets/audio/{sub}/{key.lstrip('$')}.mp3", cands,
                              extra={"index_path": ipath}))
    return items


# ---------------------------------------------------------------- 網路與檔案

class Fetcher:
    """限速＋重試的下載器。同一個主機兩次請求至少間隔 min_interval 秒。"""

    def __init__(self, cfg: dict):
        self.ua = cfg["user_agent"]
        self.retries = cfg["retries"]
        self.intervals = cfg["min_interval_s"]
        self._last: dict[str, float] = {}

    def _wait(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).hostname or ""
        gap = next((v for k, v in self.intervals.items() if host.endswith(k)), self.intervals["default"])
        wait = self._last.get(host, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _open(self, url: str, method: str = "GET"):
        self._wait(url)
        r = urllib.request.Request(url, method=method, headers={"User-Agent": self.ua})
        return urllib.request.urlopen(r, timeout=180, context=_SSL)

    def get(self, url: str) -> bytes | None:
        """回傳內容；404 回傳 None；其他錯誤退避重試後丟 RuntimeError。"""
        for attempt in range(1, self.retries + 1):
            try:
                with self._open(url) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                err = e
            if attempt == self.retries:
                raise RuntimeError(f"下載失敗 {url}: {err}")
            time.sleep(2 ** attempt)

    def exists(self, url: str) -> bool:
        for attempt in range(1, self.retries + 1):
            try:
                with self._open(url, "HEAD"):
                    return True
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False
                err = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                err = e
            if attempt == self.retries:
                raise RuntimeError(f"檢查失敗 {url}: {err}")
            time.sleep(2 ** attempt)


def load_indexes(fetcher: Fetcher, max_age_h: float = 24, cache_dir: Path = CACHE_DIR) -> Indexes:
    """讀索引；快取在 cache/，超過 max_age_h 小時才重抓。"""
    def cached(rel: str, url: str) -> str:
        path = cache_dir / rel
        if not path.exists() or time.time() - path.stat().st_mtime > max_age_h * 3600:
            print(f"  抓索引 {rel}", file=sys.stderr)
            data = fetcher.get(url)
            if data is None:
                raise RuntimeError(f"索引不存在：{url}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return path.read_text(encoding="utf-8")

    def prts(title):
        return cached(f"prts/{title}.txt", PRTS_RAW.format(title=f"Widget:{title}"))

    return Indexes(
        fexli_summary=json.loads(cached("fexli/summary.json", f"{FEXLI_RAW}/avgs/npcs/summary.json")),
        prts_image=parse_kv_index(prts("Data_Image")),
        prts_char=parse_kv_index(prts("Data_Char")),
        prts_link=json.loads(prts("Data_Link")),
        prts_audio=json.loads(prts("Data_Audio")),
    )


def sniff(data: bytes) -> str | None:
    """依檔頭判斷格式；不是預期的圖檔或音檔回傳 None（例如被擋時拿到的 HTML）。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if data[:4] == b"OggS":
        return "ogg"
    return None


def png_size(path: Path) -> tuple[int, int] | None:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def audio_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30)
        return round(float(out.stdout.strip()), 3)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


_EXTS = {"backgrounds": ("png", "jpg"), "images": ("png", "jpg"), "sprites": ("png",),
         "music": ("mp3", "wav", "ogg"), "sounds": ("mp3", "wav", "ogg")}


def _existing(item: Item, root: Path) -> Path | None:
    base = root / item.path
    for ext in _EXTS[item.kind]:
        p = base.with_suffix("." + ext)
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def fetch_item(item: Item, fetcher: Fetcher, root: Path = ROOT, sources: dict | None = None) -> dict | None:
    """下載一個素材（已存在就跳過），回傳 manifest 的一筆；全部來源都失敗回傳 None。

    sources：assets/sources.json 的內容（路徑 → 來源與網址），讓沿用舊檔時也能記下來源。
    """
    sources = sources if sources is not None else {}
    path = _existing(item, root)
    if path is None:
        for cand in item.candidates:
            data = fetcher.get(cand.url)
            fmt = sniff(data) if data else None
            if fmt not in _EXTS[item.kind]:
                continue
            path = (root / item.path).with_suffix("." + fmt)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            sources[str(path.relative_to(root))] = {"source": cand.source, "url": cand.url}
            print(f"  下載 {path.relative_to(root)}  ← {cand.source}", file=sys.stderr)
            break
        else:
            return None
    rel = str(path.relative_to(root))
    entry = {**sources.get(rel, {"source": None, "url": None}), "path": rel, "bytes": path.stat().st_size}
    if item.kind in ("music", "sounds"):
        entry["dur"] = audio_duration(path)
        entry["index_path"] = item.extra.get("index_path")
    elif size := png_size(path):
        entry["w"], entry["h"] = size
    return entry


def _load_timeline(scene_id: str) -> dict:
    path = OUT_DIR / scene_id / "timeline.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}，請先執行 python -m pipeline parse --scene {scene_id}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_manifest(scene_id: str, items: list[Item], entries: dict[tuple[str, str], dict | None],
                   req: Requirements) -> dict:
    man = {"scene_id": scene_id, "backgrounds": {}, "images": {}, "sprites": {}, "music": {}, "sounds": {},
           "effects": sorted(req.effects), "warnings": [], "missing": []}
    for it in items:
        entry = entries.get((it.kind, it.key))
        if it.warning:
            man["warnings"].append(it.warning)
        if entry is None:
            man["missing"].append({"kind": it.kind, "key": it.key,
                                   "reason": "所有來源都抓不到" if it.candidates else "索引裡沒有這個鍵"})
            continue
        if it.kind == "sprites":
            g = man["sprites"].setdefault(it.extra["group"], {"pos": it.extra["pos"], "size": it.extra["size"],
                                                               "variants": {}})
            g["variants"][it.key] = entry
        else:
            man[it.kind][it.key] = entry
    return man


def run_scene(scene_id: str, fetcher: Fetcher, idx: Indexes, root: Path = ROOT) -> dict:
    """下載一場的全部素材並寫 out/<scene>/assets_manifest.json。"""
    req = collect_requirements(_load_timeline(scene_id))
    items = resolve(req, idx)
    src_path = root / "assets" / "sources.json"
    sources = json.loads(src_path.read_text(encoding="utf-8")) if src_path.exists() else {}
    entries = {}
    try:
        for it in items:
            entries[(it.kind, it.key)] = fetch_item(it, fetcher, root, sources)
    finally:
        src_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.write_text(json.dumps(sources, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    man = build_manifest(scene_id, items, entries, req)
    out = OUT_DIR / scene_id / "assets_manifest.json"
    out.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return man


def dry_run(scene_ids: list[str], idx: Indexes, fetcher: Fetcher | None = None) -> dict:
    """只解析不下載。fetcher 有給時，另外對每個素材的首選網址發 HEAD 確認真的存在（已下載的不查）。"""
    total = Requirements()
    per_scene = {}
    for sid in scene_ids:
        req = collect_requirements(_load_timeline(sid))
        per_scene[sid] = {k: len(getattr(req, k)) for k in req.__dataclass_fields__}
        total.update(req)
    items = resolve(total, idx)
    report = {"scenes": per_scene, "counts": {}, "unresolved": [], "fallback": [], "warnings": [],
              "effects": sorted(total.effects), "verified": fetcher is not None}
    for it in items:
        c = report["counts"].setdefault(it.kind, {"total": 0, "resolved": 0})
        c["total"] += 1
        if it.warning:
            report["warnings"].append(it.warning)
        ok_source = None
        if fetcher is None or _existing(it, ROOT):
            ok_source = it.candidates[0].source if it.candidates else None
        else:
            for cand in it.candidates:
                if fetcher.exists(cand.url):
                    ok_source = cand.source
                    break
        if ok_source is None:
            report["unresolved"].append({"kind": it.kind, "key": it.key,
                                         "tried": [c.url for c in it.candidates]})
            continue
        c["resolved"] += 1
        if it.candidates and ok_source != it.candidates[0].source:
            report["fallback"].append({"kind": it.kind, "key": it.key, "source": ok_source})
    return report


def make_fetcher() -> Fetcher:
    return Fetcher(load_settings()["assets"])
