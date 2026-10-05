"""把一場已完成的配音整理成逐句音檔與語音清單（docs/01-architecture.md「追加 2026-10-05」的契約）。
只整理、不重新合成：ElevenLabs 的段落照語音辨識的逐字時間切成逐句，幹員台詞本來就是逐句。

輸入（out/<scene>/，不入庫）：lines.json、director_el.json＋el/<block>.mp3、director_idx.json＋idx/<line_id>.wav
輸出（只新增）：voice/<line_id>.wav、voice_manifest.json、voice_work/（中間檔與檢查結果）

步驟（每步都可重跑）：
  python3 tools/voice_manifest.py prep  <scene>   # 各段照 scene_assemble 的做法去頭尾、統一音量；備好要傳上叢集的 16 kHz 檔與 job.json
  bash tools/voice_cluster.sh <scene> blocks      # 傳上叢集、跑 cluster/voice_align.py、取回 voice_work/align.json（需 CUHK VPN）
  python3 tools/voice_manifest.py build <scene>   # 找切點、切句、寫 voice/ 與 voice_manifest.json，並備好逐句回聽用的 job
  bash tools/voice_cluster.sh <scene> lines       # 逐句檔再回聽一次，取回 voice_work/align_lines.json（驗證切點用，可略）
  python3 tools/voice_manifest.py check <scene>   # 驗收：重新接軌比總長與各段起點、句尾音量、回聽比對，寫 voice_work/check.json

只更新一部分（來源音檔換了幾段時）：prep 與 build 後面加上要更新的段名與幹員句號，用逗號隔開，例如
  python3 tools/voice_manifest.py prep  <scene> b01,b03
  python3 tools/voice_manifest.py build <scene> b01,b03,0142
其餘的逐句檔與清單裡其餘的行原樣保留（build 會覆寫列出的那些檔，請先自行備份 voice/）。

切法：
- 每段先做與 tools/scene_assemble.py 完全相同的處理（去頭尾、整段一個增益），所以逐句檔接回去與認可過的 scene.mp3 是同一批聲音；
  音量是「整段一起調」而不是逐句各調，段內輕重對比保持原樣。
- 兩句之間的切點：在前一句最後一個字與後一句第一個字之間，取最長那段安靜的正中間；找不到安靜處就取最安靜的 20 毫秒並標記。
  沒被辨識出字的句子（咳嗽、喘息這類非語言聲音）靠前後句推：它前面的切點取「緊鄰它之前」的安靜處，後面同理。
- 每句切下後去掉頭尾的靜音，句尾留 0.08 秒並淡出 0.06 秒；被去掉的靜音長度記成下一句的 gap_before，
  所以段內的節奏與原本合成出來的一樣。
- 段內的無聲行（「……」）在送合成時是一個停頓標記：清單裡它照樣一筆（path 為 null），
  停留時間記在 hold（不超過 1 秒），停頓剩下的部分記在下一句的 gap_before。
"""
import array
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene_assemble import GAP, GAP_SILENT, GAP_TURN, PEAK, SR, TARGET, measure  # noqa: E402

HOP = SR // 100                     # 量音量用的 10 毫秒格
HEAD_DB, TAIL_DB = -50.0, -60.0     # 與 scene_assemble 的去頭、去尾門檻相同
TAIL_KEEP, TAIL_FADE, HEAD_FADE = 0.08, 0.06, 0.005
QUIET_DB = -45.0                    # 找切點時「安靜」的門檻（相對該段峰值）
MIN_QUIET = 0.06                    # 至少這麼長才算一段安靜
TAG = re.compile(r"\[[^\]]*\]")
TRIM = ("silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.08,afade=t=in:d=0.06,areverse")


def sid(line_id):
    return line_id.rsplit("_", 1)[1]


def load(scene):
    d = ROOT / "out" / scene
    lines = json.loads((d / "lines.json").read_text(encoding="utf-8"))
    blocks = json.loads((d / "director_el.json").read_text(encoding="utf-8"))
    idx = json.loads((d / "director_idx.json").read_text(encoding="utf-8"))["lines"]
    order = [sid(r["line_id"]) for r in lines]
    by = {sid(r["line_id"]): r for r in lines}
    for b in blocks:
        span = order[order.index(b["first"]):order.index(b["last"]) + 1]
        b["span"] = span
        b["voiced"] = [s for s in span if by[s]["tts"]]
        texts = [TAG.sub("", p).strip() for p in b["prompt"].split("\n")]
        if len(texts) != len(b["voiced"]):
            sys.exit(f"{b['block']}: 送出的文字有 {len(texts)} 行，段內要配音的是 {len(b['voiced'])} 句，對不上")
        b["texts"] = texts
    if any(l.get("block_last") for l in idx):
        sys.exit("director_idx.json 有幾句共用一個音檔（block_last）的項目，這支工具還沒處理")
    return d, lines, blocks, {l["line_id"]: l for l in idx}


def normalize(src, dst, rate=SR):
    """與 scene_assemble 相同的處理：去頭尾、句尾留 0.08 秒並淡出、整個檔一個增益（平均 -20 dB、峰值不過 -1.5 dB）。"""
    mean, peak = measure(src)
    gain = min(TARGET - mean, PEAK - peak)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"{TRIM},volume={gain:.2f}dB",
                    "-ar", str(rate), "-ac", "1", "-c:a", "pcm_s16le", str(dst)], check=True)


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR, path
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    return a


def write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(samples.tobytes())


def db(x):
    return 20 * math.log10(max(x, 1e-9))


def levels(a):
    """每 10 毫秒一格的音量（dB，滿刻度為 0）。"""
    return [db(math.sqrt(sum(x * x for x in a[i:i + HOP]) / HOP) / 32768) for i in range(0, max(len(a) - HOP + 1, 1), HOP)]


# ---------- prep ----------

def prep(scene, only=None):
    d, lines, blocks, _ = load(scene)
    blocks = [b for b in blocks if only is None or b["block"] in only]
    work = d / "voice_work"
    (work / "el").mkdir(parents=True, exist_ok=True)
    (work / "upload_blocks" / "wav").mkdir(parents=True, exist_ok=True)
    items = []
    for b in blocks:
        full = work / "el" / f"{b['block']}.wav"
        normalize(d / "el" / f"{b['block']}.mp3", full)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(full), "-ar", "16000", str(work / "upload_blocks" / "wav" / full.name)], check=True)
        items.append(dict(key=b["block"], wav=f"wav/{full.name}",
                          lines=[dict(line_id=s, text=t) for s, t in zip(b["voiced"], b["texts"])]))
    (work / "upload_blocks" / "job.json").write_text(json.dumps(dict(scene=f"{scene}_voice_blocks", items=items), ensure_ascii=False), encoding="utf-8")
    print(f"{scene}: {len(items)} 段已備好 -> {(work / 'upload_blocks').relative_to(ROOT)}")


# ---------- build ----------

def quiet_runs(lv, lo, hi, thr):
    """[lo, hi) 格之間低於門檻的連續區段 [(起, 訖)]。"""
    runs, start = [], None
    for i in range(lo, hi):
        if lv[i] < thr:
            start = i if start is None else start
        elif start is not None:
            runs.append((start, i)); start = None
    if start is not None:
        runs.append((start, hi))
    return [r for r in runs if (r[1] - r[0]) * HOP / SR >= MIN_QUIET]


def spans(res):
    """每句被辨識到的起訖毫秒（含多念出來、落在這句裡的字）；整句沒被認出來的是 None。"""
    out = []
    for n, l in enumerate(res["lines"]):
        hit = [q for q in l["hyp"] if q >= 0] + [x["i"] for x in res["ins"] if x["line"] == n and any(q >= 0 for q in l["hyp"])]
        out.append((res["ts"][min(hit)][0], res["ts"][max(hit)][1]) if hit else None)
    return out


def pick_engine(item):
    """逐字時間取字錯率最低的那套辨識（同分時優先 paraformer：它的逐字時間較準）。"""
    cands = [item[k] for k in ("para", "para_vad", "whisper") if k in item and item[k].get("ts")]
    if not cands:
        sys.exit(f"{item['key']}: 沒有可用的逐字時間")
    return min(cands, key=lambda r: r["cer"])


def find_cuts(lv, sp, peak_db):
    """回傳每個句間切點（格）與說明。sp＝每句的 (起, 訖) 毫秒或 None。"""
    n_frames, thr = len(lv), peak_db + QUIET_DB
    f = lambda ms: min(max(int(ms / 10), 0), n_frames)
    cuts = []
    for n in range(len(sp) - 1):
        prev = next((sp[k] for k in range(n, -1, -1) if sp[k]), None)
        nxt = next((sp[k] for k in range(n + 1, len(sp)) if sp[k]), None)
        lo, hi = f(prev[1]) if prev else 0, f(nxt[0]) if nxt else n_frames
        # 辨識給的字邊界不準（常把字尾算短、把字頭算晚），兩邊各放寬 0.15 秒再找
        lo, hi = max(lo - 15, f(prev[0]) + 1 if prev else 0), min(hi + 15, f(nxt[1]) - 1 if nxt else n_frames)
        if hi <= lo:
            lo, hi = max(min(lo, hi) - 25, 0), min(max(lo, hi) + 25, n_frames)
        runs = quiet_runs(lv, lo, hi, thr)
        wide = False
        if not runs and sp[n] and sp[n + 1]:
            # 逐字時間偏了（whisper 的時間較粗）：放寬到前後兩句各自的中點，取離原本位置最近的安靜處
            mid, lo2, hi2 = (lo + hi) // 2, f(sum(sp[n]) / 2), f(sum(sp[n + 1]) / 2)
            near = sorted(quiet_runs(lv, lo2, hi2, thr), key=lambda r: abs((r[0] + r[1]) // 2 - mid))
            if near:
                runs, wide, lo, hi = near[:1], True, lo2, hi2
        if sp[n] is None and sp[n + 1] is None:
            how, run = "兩句都沒被認出來", None
        elif runs and sp[n] is None:
            how, run = "前一句沒被認出來，取後一句開口前的安靜處", runs[-1]
        elif runs and sp[n + 1] is None:
            how, run = "後一句沒被認出來，取前一句收尾後的安靜處", runs[0]
        elif runs:
            how, run = "ok（放寬範圍後找到）" if wide else "ok", max(runs, key=lambda r: r[1] - r[0])
        else:
            how, run = "兩句之間沒有安靜處", None
        if run:
            cut = (run[0] + run[1]) // 2
        else:                           # 退而求其次：最安靜的 20 毫秒
            cut = min(range(lo, max(hi - 1, lo + 1)), key=lambda i: lv[i] + lv[min(i + 1, n_frames - 1)]) + 1
        cuts.append(dict(frame=cut, how=how, quiet=round((run[1] - run[0]) * HOP / SR, 2) if run else 0.0,
                         window=[round(lo * HOP / SR, 2), round(hi * HOP / SR, 2)]))
    return cuts


def fade(a, n, out):
    n = min(n, len(a))
    for i in range(n):
        k = len(a) - 1 - i if out else i
        a[k] = int(a[k] * i / n)


def cut_block(a, lv, cuts):
    """照切點切成逐句：回傳 [(samples, 開口前被去掉的靜音秒數)]。第一句的頭、最後一句的尾已由 normalize 處理過。"""
    n_frames = len(lv)
    edges = [0] + [c["frame"] for c in cuts] + [n_frames]
    out, prev_end = [], 0
    for n, (lo, hi) in enumerate(zip(edges, edges[1:])):
        first, last = n == 0, n == len(edges) - 2
        on = lo if first else next((i for i in range(lo, hi) if lv[i] >= HEAD_DB), lo)
        if last:
            end = len(a)
        else:
            off = next((i for i in range(hi - 1, on - 1, -1) if lv[i] >= TAIL_DB), on) + 1
            end = min(off * HOP + int(TAIL_KEEP * SR), hi * HOP)
        seg = a[on * HOP:end]
        if not first:
            fade(seg, int(HEAD_FADE * SR), out=False)
        if not last:
            fade(seg, int(TAIL_FADE * SR), out=True)
        out.append((seg, (on * HOP - prev_end) / SR))
        prev_end = end
    return out


def build(scene, only=None):
    d, lines, blocks, idx = load(scene)
    work = d / "voice_work"
    align = {it["key"]: it for it in json.loads((work / "align.json").read_text(encoding="utf-8"))["items"]}
    old = {}                            # 只更新一部分時，其餘的行沿用現有清單
    if only is not None:
        old = {sid(l["line_id"]): {k: v for k, v in l.items() if k not in ("line_id", "speaker")}
               for l in json.loads((d / "voice_manifest.json").read_text(encoding="utf-8"))["lines"]}
        blocks = [b for b in blocks if b["block"] in only]
        idx = {k: v for k, v in idx.items() if sid(k) in only}
        unknown = only - {b["block"] for b in blocks} - {sid(k) for k in idx}
        if unknown:
            sys.exit(f"找不到這些段或句：{sorted(unknown)}")
    voice = d / "voice"
    voice.mkdir(exist_ok=True)
    row = {}                            # sid -> 清單的一筆（不含 line_id、speaker）
    diag, job = [], []
    for b in blocks:
        a = read_wav(work / "el" / f"{b['block']}.wav")
        lv = levels(a)
        res = pick_engine(align[b["block"]])
        sp = spans(res)
        cuts = find_cuts(lv, sp, max(lv))
        parts = cut_block(a, lv, cuts)
        for n, (s, (seg, lead)) in enumerate(zip(b["voiced"], parts)):
            path = voice / f"{scene}_{s}.wav"
            write_wav(path, seg)
            gap = b.get("gap_before") if n == 0 else round(lead, 3)
            row[s] = dict(engine="elevenlabs", path=f"voice/{path.name}", dur=round(len(seg) / SR, 3), gap_before=gap)
            job.append(dict(key=s, wav=f"wav/{path.name}", lines=[dict(line_id=s, text=b["texts"][n])]))
            if n:
                diag.append(dict(block=b["block"], before=s, **cuts[n - 1], pause=round(lead, 3)))
        # 段內的無聲行：它前後兩句之間的停頓，一部分當它的停留時間，其餘留給下一句
        for k, s in enumerate(b["span"]):
            if s in b["voiced"]:
                continue
            nxt = next(x for x in b["span"][k + 1:] if x in b["voiced"])
            pause = row[nxt]["gap_before"]
            hold = round(min(GAP_SILENT, pause), 3)
            row[s] = dict(engine=None, path=None, dur=0, gap_before=None)
            if hold < GAP_SILENT:       # 停頓不到 1 秒才需要另外寫；等於預設值就不寫
                row[s]["hold"] = hold
            row[nxt]["gap_before"] = round(pause - hold, 3)
    for line_id, l in idx.items():
        path = voice / f"{line_id}.wav"
        normalize(d / "idx" / f"{line_id}.wav", path)
        with wave.open(str(path), "rb") as w:
            dur = w.getnframes() / SR
        row[sid(line_id)] = dict(engine="indextts2", path=f"voice/{path.name}", dur=round(dur, 3), gap_before=l.get("gap_before"))
    out = []
    for r in lines:
        s = sid(r["line_id"])
        if s not in row and s in old:
            row[s] = old[s]
        if r["tts"] and s not in row:
            sys.exit(f"{r['line_id']}: 要配音但找不到音檔來源")
        out.append(dict(line_id=r["line_id"], speaker=r["identity"],
                        **row.get(s, dict(engine=None, path=None, dur=0, gap_before=None))))
    manifest = dict(scene=scene, sample_rate=SR, gap_rules=dict(same_speaker=GAP, turn=GAP_TURN, silent_line=GAP_SILENT), lines=out)
    (d / "voice_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    if only is not None and (work / "cuts.json").exists():
        diag = [c for c in json.loads((work / "cuts.json").read_text(encoding="utf-8")) if c["block"] not in only] + diag
    (work / "cuts.json").write_text(json.dumps(diag, ensure_ascii=False, indent=1), encoding="utf-8")
    up = work / "upload_lines"
    (up / "wav").mkdir(parents=True, exist_ok=True)
    for j in job:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(d / "voice" / Path(j["wav"]).name), "-ar", "16000", str(up / j["wav"])], check=True)
    (up / "job.json").write_text(json.dumps(dict(scene=f"{scene}_voice_lines", items=job), ensure_ascii=False), encoding="utf-8")
    bad = [c for c in diag if not c["how"].startswith("ok")]
    print(f"{scene}: {len(out)} 行，逐句檔 {sum(1 for r in out if r['path'])} 個 -> {voice.relative_to(ROOT)}/ 與 voice_manifest.json")
    print(f"段內切點 {len(diag)} 個，其中要留意 {len(bad)} 個：")
    for c in bad:
        print(f"  {c['block']} {c['before']} 之前：{c['how']}（搜尋範圍 {c['window']} 秒）")


def merge(scene, what):
    """把剛從叢集取回的辨識結果（*.fetched）依 key 併進 align.json／align_lines.json。"""
    work = ROOT / "out" / scene / "voice_work"
    name = {"blocks": "align.json", "lines": "align_lines.json"}[what]
    new = json.loads((work / f"{name}.fetched").read_text(encoding="utf-8"))
    cur = json.loads((work / name).read_text(encoding="utf-8")) if (work / name).exists() else dict(scene=new["scene"], items=[])
    got = {it["key"]: it for it in new["items"]}
    items = [got.pop(it["key"], it) for it in cur["items"]] + list(got.values())
    (work / name).write_text(json.dumps(dict(scene=cur["scene"], items=items), ensure_ascii=False), encoding="utf-8")
    (work / f"{name}.fetched").unlink()
    print(f"{name}：更新 {len(new['items'])} 筆，共 {len(items)} 筆")


# ---------- check ----------

def timeline(manifest):
    """照節奏規則排出每行的開始時間：回傳 [(line, start)] 與總長。"""
    t, prev, out = 0.0, None, []
    for l in manifest["lines"]:
        if not l["path"]:
            hold = l.get("hold")
            out.append((l, t))
            t += GAP_SILENT if hold is None else hold
            continue
        gap = l["gap_before"] if l["gap_before"] is not None else (0.0 if prev is None else GAP if prev == l["speaker"] else GAP_TURN)
        out.append((l, t + gap))
        t += gap + l["dur"]
        prev = l["speaker"]
    return out, t


def diff_report(res, texts=None):
    """把一份辨識比對結果整理成「哪句、原文哪個字、聽成什麼」。"""
    probs = []
    for n, l in enumerate(res["lines"]):
        miss = [(i, t) for i, (t, q) in enumerate(zip(l["ref"], l["hyp"])) if q < 0]
        wrong = [(t, res["toks"][q]) for t, q, ok in zip(l["ref"], l["hyp"], l["ok"]) if q >= 0 and not ok]
        extra = [x["tok"] for x in res["ins"] if x["line"] == n]
        if miss or wrong or extra:
            probs.append(dict(line=l["line_id"], n_ref=len(l["ref"]), missing="".join(t for _, t in miss),
                              wrong=[f"{a}→{b}" for a, b in wrong], extra="".join(extra)))
    return probs


def check(scene):
    d, lines, blocks, idx = load(scene)
    work = d / "voice_work"
    manifest = json.loads((d / "voice_manifest.json").read_text(encoding="utf-8"))
    report = {}

    # 1. 重新接軌：總長、各段起點
    tl, total = timeline(manifest)
    buf = array.array("h")
    for l, start in tl:
        if l["path"]:
            buf.extend(array.array("h", bytes(2 * max(int(round(start * SR)) - len(buf), 0))))
            buf.extend(read_wav(d / l["path"]))
    buf.extend(array.array("h", bytes(2 * SR)))        # scene.mp3 結尾墊了 1 秒
    re_path = work / "reassembled.wav"
    write_wav(re_path, buf)
    probe = lambda p: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                           capture_output=True, text=True).stdout)
    scene_dur = probe(d / "scene.mp3")
    cues = {c["key"]: c for c in json.loads((d / "cues.json").read_text(encoding="utf-8"))}
    first_of = {b["voiced"][0]: b["block"] for b in blocks}
    drift = []
    for l, start in tl:
        s = sid(l["line_id"])
        key = first_of.get(s) or (s if l["line_id"] in idx else None)
        if key:
            drift.append((round(start - cues[key]["start"], 3), key))
    block_end = []
    by_sid = {sid(l["line_id"]): (l, st) for l, st in tl}
    for b in blocks:
        l, st = by_sid[b["voiced"][-1]]
        block_end.append((round(st + l["dur"] - cues[b["block"]]["end"], 3), b["block"]))
    report["reassemble"] = dict(total=round(len(buf) / SR, 3), scene_mp3=round(scene_dur, 3), diff=round(len(buf) / SR - scene_dur, 3),
                                max_start_drift=max(drift, key=lambda x: abs(x[0])), max_block_end_drift=max(block_end, key=lambda x: abs(x[0])))

    # 1a. 每段切出來的各句（含段內停頓）加起來要等於整段的長度
    span = []
    for b in blocks:
        (l0, s0), (l1, s1) = by_sid[b["voiced"][0]], by_sid[b["voiced"][-1]]
        with wave.open(str(work / "el" / f"{b['block']}.wav"), "rb") as w:
            span.append((round(s1 + l1["dur"] - s0 - w.getnframes() / SR, 3), b["block"]))
    report["reassemble"]["max_block_span_diff"] = max(span, key=lambda x: abs(x[0]))

    # 1b. 與 scene.mp3 比每 0.1 秒的音量曲線（確認接回去的是同一批聲音）
    ref_raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(d / "scene.mp3"), "-ar", str(SR), "-ac", "1", "-f", "s16le", "-"],
                             capture_output=True).stdout
    ref = array.array("h"); ref.frombytes(ref_raw[:len(ref_raw) // 2 * 2])
    env = lambda a: [math.sqrt(sum(x * x for x in a[i:i + 4410:10]) / 441) for i in range(0, len(a) - 4410, 4410)]
    e1, e2 = env(buf), env(ref)
    m = min(len(e1), len(e2))
    e1, e2 = e1[:m], e2[:m]
    m1, m2 = sum(e1) / m, sum(e2) / m
    corr = sum((x - m1) * (y - m2) for x, y in zip(e1, e2)) / math.sqrt(sum((x - m1) ** 2 for x in e1) * sum((y - m2) ** 2 for y in e2))
    report["reassemble"]["envelope_corr"] = round(corr, 4)

    # 2. 句尾音量：最後 40 毫秒相對該檔峰值
    tails = []
    for l in manifest["lines"]:
        if not l["path"]:
            continue
        a = read_wav(d / l["path"])
        peak = max(max(a), -min(a), 1)
        n = int(0.04 * SR)
        tail = db(math.sqrt(sum(x * x for x in a[-n:]) / n) / peak)
        tails.append((round(tail, 1), sid(l["line_id"])))
    report["tail"] = dict(worst=max(tails), over=[t for t in tails if t[0] > -45.0], n=len(tails))

    # 3. 段落回聽比對（兩套辨識都標的才算可信）
    align = json.loads((work / "align.json").read_text(encoding="utf-8"))["items"]
    blocks_rep = []
    for it in align:
        engines = {k: it[k] for k in ("para", "para_vad", "whisper") if k in it and "lines" in it[k]}
        blocks_rep.append(dict(block=it["key"], cer={k: v["cer"] for k, v in engines.items()},
                               heard={k: "".join(v["toks"]) for k, v in engines.items()},
                               problems={k: diff_report(v) for k, v in engines.items()}))
    report["blocks"] = blocks_rep

    # 4. 逐句檔回聽（有跑才有）
    p = work / "align_lines.json"
    if p.exists():
        rep = []
        for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
            engines = {k: it[k] for k in ("para", "para_vad", "whisper") if k in it and "lines" in it[k]}
            rep.append(dict(line=it["key"], dur=it["dur"], cer={k: v["cer"] for k, v in engines.items()},
                            heard={k: "".join(v["toks"]) for k, v in engines.items()}))
        report["lines"] = rep
    (work / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    r = report["reassemble"]
    print(f"重新接軌 {r['total']} 秒，scene.mp3 {r['scene_mp3']} 秒，差 {r['diff']} 秒；段起點最大偏移 {r['max_start_drift']}；"
          f"段終點最大偏移 {r['max_block_end_drift']}；音量曲線相關 {r['envelope_corr']}")
    print(f"各段逐句加總與整段長度的最大差距 {r['max_block_span_diff']}")
    print(f"句尾音量：{report['tail']['n']} 個檔，最差 {report['tail']['worst']}，高於 -45 dB 的 {report['tail']['over']}")
    print(f"細節 -> {(work / 'check.json').relative_to(ROOT)}")


if __name__ == "__main__":
    cmd, scene, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if cmd == "merge":
        merge(scene, rest[0])
    elif cmd == "check":
        check(scene)
    else:
        {"prep": prep, "build": build}[cmd](scene, set(rest[0].split(",")) if rest else None)
