"""參考音目錄：替一位幹員備好「可選的參考音清單」。

在 aktts 環境下執行： python ref_catalog.py <短名> <charId> <顯示名>
    例： python ref_catalog.py kalts char_003_kalts 凯尔希

一次完成：
  1. 下載該幹員全部中文語音（PseudoMon/arknights-audio 的 MP3；沒有就改抓 PRTS 的 WAV）。
  2. 逐句量測：語速（字/秒，扣掉停頓）、停頓、音高中位數與起伏、動態範圍、頻譜質心、emotion2vec 情緒分數。
  3. 3–10 秒的原句直接可用；長於 10 秒的按子句切成 3–10 秒片段。
     子句的結束時間有兩種推法：語音辨識的逐字時間戳、字數比例；都吸附到最近的停頓，
     再各自回檢，取切出來平均字錯率較低的那一種。
  4. 短於 3 秒的句子依音高排序，相鄰的接成 3–10 秒的拼接片段。
  5. 每段參考音再量一次，並用語音辨識回檢文字（同音字不算錯）。長度不在 3–10 秒的標為不可用；
     切片另外要求字錯率 ≤ 0.15（超過代表切到相鄰子句）。原句與拼接的字錯率只記錄，不淘汰。

輸出到 $AKTTS_ROOT/work/refs/<短名>/：
  audio/        下載的原聲
  segments/     全部參考音（WAV）
  catalog.json  逐句量測（含台詞原文）
  refs.json     全部參考音的量測（含文字與檔案路徑；合成時讀這份）
  summary.json  同 refs.json 但不含台詞原文與路徑（入庫到 config/refs/<短名>.json 的就是這份）
  catalog.html  試聽頁（音檔用相對路徑，需與 audio/、segments/ 放在一起）

量的是音頻本身，不看台詞文字猜語氣。「慢/中/快」之類的標籤是相對於該角色自己的三等分，不是絕對標準。
emotion2vec 的標籤只能當分群線索，不是情緒真值（冷峻的語氣常被標成「生气」）。
"""
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.request

import librosa
import numpy as np
import soundfile as sf

ROOT = os.environ["AKTTS_ROOT"]
KEY, CHAR_ID, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
OUT = f"{ROOT}/work/refs/{KEY}"
TABLE_SRC = ("https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/"
             "zh_CN/gamedata/excel/charword_table.json")
SOURCES = [  # (來源名, 網址樣板, 副檔名, 每次請求後等待秒數)
    ("PseudoMon/arknights-audio", "https://raw.githubusercontent.com/PseudoMon/arknights-audio/master/voice_cn/{cid}/{vid}.mp3", "mp3", 0.0),
    ("torappu.prts.wiki", "https://torappu.prts.wiki/assets/audio/voice_cn/{cid}/{vid_lower}.wav", "wav", 1.2),
]
SR, HOP, FRAME = 16000, 256, 1024
MIN_S, MAX_S = 3.0, 10.0          # 參考音可用的長度範圍
CER_MAX = 0.15                    # 文字回檢的字錯率上限
GAP_S = 0.25                      # 拼接時句子之間的靜音
SPOKEN = {"Mon3tr": "Monster"}    # 參考音文字照實際念法寫


def units_list(text):
    """可發音單位：一個漢字一個，一個英數詞一個（小寫）。"""
    return re.findall(r"[一-鿿]|[a-z0-9]+", text.lower())


def units(text):
    """可發音單位數：一個漢字算 1，一個英數詞算 2。"""
    return len(re.findall(r"[一-鿿]", text)) + 2 * len(re.findall(r"[A-Za-z0-9]+", text))


def spoken(text):
    for a, b in SPOKEN.items():
        text = text.replace(a, b)
    return text


try:
    from pypinyin import lazy_pinyin

    def sound_key(tok):  # 同音字歸一：語音辨識常把專有名詞寫成同音字
        return lazy_pinyin(tok)[0] if re.match(r"[一-鿿]", tok) else tok
    HOMOPHONE = True
except ImportError:
    def sound_key(tok):
        return tok
    HOMOPHONE = False


def edit_align(ref, hyp):
    """編輯距離與對應：回傳 (距離, ref 每個單位對到的 hyp 位置或 None)。"""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0], d[0, :] = np.arange(n + 1), np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    match, i, j = [None] * n, n, m
    while i > 0 and j > 0:
        if d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            match[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif d[i, j] == d[i - 1, j] + 1:
            i -= 1
        else:
            j -= 1
    return int(d[n, m]), match


def cer(ref_text, hyp_text, by_sound=True):
    r, h = units_list(ref_text), units_list(hyp_text)
    if by_sound:
        r, h = [sound_key(x) for x in r], [sound_key(x) for x in h]
    return round(edit_align(r, h)[0] / max(len(r), 1), 3)


def fetch(url, path, wait=0.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (aktts ref_catalog)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    time.sleep(wait)
    if len(data) < 1000:
        raise IOError(f"too small: {len(data)} bytes")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)


def download(vid):
    """回傳 (本機路徑, 來源名)；已下載過就直接用。"""
    for name, _, ext, _ in SOURCES:
        p = f"{OUT}/audio/{vid}.{ext}"
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p, name
    err = None
    for name, tpl, ext, wait in SOURCES:
        p = f"{OUT}/audio/{vid}.{ext}"
        for attempt in range(3):
            try:
                fetch(tpl.format(cid=CHAR_ID, vid=vid, vid_lower=vid.lower()), p, wait)
                return p, name
            except Exception as e:
                err = e
                if "404" in repr(e):
                    break
                time.sleep(5 * (attempt + 1))
    raise IOError(f"{vid}: 所有來源都失敗（{err!r}）")


def load_mono(path):
    data, sr = sf.read(path)
    return (data if data.ndim == 1 else data.mean(axis=1)), sr


def intervals(y):
    return librosa.effects.split(y, top_db=35, frame_length=FRAME, hop_length=HOP)


def acoustic(path, text):
    y, _ = librosa.load(path, sr=SR, mono=True)
    iv = intervals(y)
    if len(iv) == 0:
        return None
    speech = float(sum(e - s for s, e in iv)) / SR
    span = float(iv[-1][1] - iv[0][0]) / SR
    gaps = [(iv[i + 1][0] - iv[i][1]) / SR for i in range(len(iv) - 1)]
    pauses = [g for g in gaps if g >= 0.25]
    f0, _, _ = librosa.pyin(y, fmin=70, fmax=500, sr=SR, frame_length=FRAME, hop_length=HOP)
    f0v = f0[~np.isnan(f0)]
    mask = np.zeros(1 + len(y) // HOP, dtype=bool)
    for s, e in iv:
        mask[s // HOP:e // HOP + 1] = True
    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    cen = librosa.feature.spectral_centroid(y=y, sr=SR, n_fft=FRAME, hop_length=HOP)[0]
    n = min(len(rms), len(mask), len(cen))
    db = 20 * np.log10(rms[:n][mask[:n]] + 1e-9)
    st = 12 * np.log2(f0v / np.median(f0v)) if len(f0v) > 5 else np.zeros(1)
    u = units(text)
    return dict(
        dur=round(len(y) / SR, 2), speech_s=round(speech, 2), units=u,
        rate=round(u / max(speech, 1e-6), 2),               # 字/秒，不含停頓
        rate_span=round(u / max(span, 1e-6), 2),            # 字/秒，含句中停頓
        n_pauses=len(pauses), pause_ratio=round(sum(pauses) / max(span, 1e-6), 3),
        f0_median=round(float(np.median(f0v)), 1) if len(f0v) > 5 else None,
        f0_std_st=round(float(np.std(st)), 2), f0_range_st=round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2),
        dyn_db=round(float(np.percentile(db, 95) - np.percentile(db, 5)), 1),
        centroid=round(float(np.mean(cen[:n][mask[:n]])), 0))


def tercile_tags(rows, key, labels):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if len(vals) < 3:
        for r in rows:
            r[key + "_tag"] = None
        return
    lo, hi = np.percentile(vals, [33.3, 66.7])
    for r in rows:
        v = r.get(key)
        r[key + "_tag"] = None if v is None else labels[0] if v <= lo else labels[2] if v > hi else labels[1]


def to16k(path):
    tmp = f"{OUT}/tmp16k/{os.path.basename(path)}.wav"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    y, _ = librosa.load(path, sr=SR, mono=True)
    sf.write(tmp, y, SR)
    return tmp


# ------------------------------------------------------------ 原聲目錄 ------
shutil.rmtree(f"{OUT}/segments", ignore_errors=True)        # 參考音每次重建，避免留下舊版的檔案
os.makedirs(f"{OUT}/segments", exist_ok=True)
table_path = f"{ROOT}/work/refs/charword_table.json"
if not os.path.exists(table_path):
    fetch(TABLE_SRC, table_path)
cw = json.load(open(table_path, encoding="utf-8"))
if not any(v.get("charId") == CHAR_ID for v in cw["charWords"].values()):   # 快取的表太舊，重抓一次
    fetch(TABLE_SRC, table_path)
    cw = json.load(open(table_path, encoding="utf-8"))
wordkey = cw.get("voiceLangDict", {}).get(CHAR_ID, {}).get("dict", {}).get("CN_MANDARIN", {}).get("wordkey")
table = {}
for v in cw["charWords"].values():
    if v.get("charId") == CHAR_ID and v["voiceId"].startswith("CN_") and v["voiceId"] not in table \
            and (wordkey is None or v.get("wordKey") in (None, wordkey)):
        text = v["voiceText"].replace("Dr.{@nickname}", "博士").replace("{@nickname}", "博士")
        text = re.sub(r"（[^）]*）|\([^)]*\)", "", re.sub(r"\s+", "", text))      # 括號裡是動作描述，不是念出來的字
        table[v["voiceId"]] = dict(id=v["voiceId"], title=v.get("voiceTitle", ""), text=text)
if not table:
    sys.exit(f"charword_table 裡找不到 {CHAR_ID} 的中文語音")

notes, clips = [], []
for vid in sorted(table):
    if not units_list(table[vid]["text"]):
        notes.append(f"{vid}（{table[vid]['title']}）是沒有台詞的聲音（原文只有動作描述），不列入")
        continue
    try:
        path, source = download(vid)
        a = acoustic(path, table[vid]["text"])
    except Exception as e:
        notes.append(f"{vid} 略過：{e!r}")
        print("skip", vid, repr(e), flush=True)
        continue
    if a:
        clips.append(dict(table[vid], file=os.path.basename(path), source=source, **a))
if not clips:
    sys.exit("一句語音都沒下載到")
by_id = {c["id"]: c for c in clips}
print(f"[{KEY}] 下載並量測 {len(clips)}/{len(table)} 句", flush=True)

from funasr import AutoModel  # noqa: E402
asr = AutoModel(model="paraformer-zh", disable_update=True)
asr_long = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", disable_update=True)   # 整句長音頻：先切語音段，時間戳才準
emo = AutoModel(model="iic/emotion2vec_plus_large", disable_update=True)


def recognize(path, long=False):
    """回傳 (辨識文字, [(單位, 開始秒, 結束秒)])；模型沒給時間戳時第二項為空。"""
    res = (asr_long if long else asr).generate(input=to16k(path))[0]
    toks = res.get("text", "").split()
    ts = res.get("timestamp") or []
    if len(toks) != len(ts) and not recognize.warned:
        recognize.warned = True
        print(f"時間戳數量與單位數不符（{len(ts)} 對 {len(toks)}），該句改用字數比例", flush=True)
    timed = [(t.lower(), s / 1000, e / 1000) for t, (s, e) in zip(toks, ts)] if len(toks) == len(ts) else []
    return "".join(toks), timed


def emotion(path):
    res = emo.generate(path, granularity="utterance", extract_embedding=False)[0]
    return {lab.split("/")[0]: round(float(s), 3) for lab, s in zip(res["labels"], res["scores"])}


recognize.warned = False
for c in clips:
    c["emotion"] = emotion(f"{OUT}/audio/{c['file']}")
    c["emotion_top"] = max(c["emotion"], key=c["emotion"].get)
tercile_tags(clips, "rate", ["慢", "中", "快"])
tercile_tags(clips, "f0_median", ["低", "中", "高"])
tercile_tags(clips, "f0_std_st", ["平", "中", "起伏大"])
tercile_tags(clips, "centroid", ["柔", "中", "亮"])
med = {k: round(float(np.median([c[k] for c in clips if c.get(k) is not None])), 2)
       for k in ("rate", "rate_span", "f0_median", "f0_std_st", "dyn_db", "centroid", "dur")}

# -------------------------------------------------------------- 參考音 ------
refs = []


def add_ref(rid, kind, src, text, data, sr, span=None, align=None):
    p = f"{OUT}/segments/{rid}.wav"
    sf.write(p, data, sr)
    refs.append(dict(id=rid, kind=kind, src=src, titles=[by_id[v]["title"] for v in src], text=text, path=p,
                     span=span, align=align))


for c in clips:                                           # 1) 3–10 秒的原句直接可用
    if MIN_S <= c["dur"] <= MAX_S:
        data, sr = load_mono(f"{OUT}/audio/{c['file']}")
        add_ref(c["id"], "原句", [c["id"]], spoken(c["text"]), data, sr)

for c in clips:                                           # 2) 長句按子句切片
    if c["dur"] <= MAX_S:
        continue
    path = f"{OUT}/audio/{c['file']}"
    data, sr = load_mono(path)
    y = librosa.resample(data, orig_sr=sr, target_sr=SR)
    iv = intervals(y) / SR
    speech_total = float(sum(e - s for s, e in iv))
    gaps = [((iv[i][1] + iv[i + 1][0]) / 2) for i in range(len(iv) - 1) if iv[i + 1][0] - iv[i][1] >= 0.15]
    text = spoken(c["text"])
    clauses = re.findall(r"[^，。？！…、—；：]+[，。？！…、—；：]*", text)
    ref_u = units_list(text)
    _, timed = recognize(path, long=True)
    match = edit_align([sound_key(x) for x in ref_u], [sound_key(t) for t, _, _ in timed])[1] if timed else []
    hit = sum(m is not None and sound_key(ref_u[i]) == sound_key(timed[m][0]) for i, m in enumerate(match))

    def time_at(frac):                                    # 假設發聲時間內語速均勻，由字數比例推時間
        need = frac * speech_total
        for s, e in iv:
            if need <= e - s:
                return s + need
            need -= e - s
        return iv[-1][1]

    def clause_end(n_done, how):
        """前 n_done 個單位念完的時間。"""
        if how == "字數比例":
            return time_at(n_done / max(len(ref_u), 1))
        before = [timed[m][2] for m in match[:n_done] if m is not None]
        after = [timed[m][1] for m in match[n_done:] if m is not None]
        if before and after:
            return (before[-1] + after[0]) / 2
        return before[-1] if before else after[0]

    def cut(how):
        bounds, acc = [], 0
        for cl in clauses[:-1]:                           # 每個子句結束的時間，吸附到最近的停頓
            acc += len(units_list(cl))
            est = float(clause_end(acc, how))
            near = min(gaps, key=lambda g: abs(g - est)) if gaps else est
            b = near if abs(near - est) <= 0.6 else est
            bounds.append(max(b, bounds[-1]) if bounds else b)
        bounds.append(float(iv[-1][1]) + 0.05)
        start, buf, pieces = max(float(iv[0][0]) - 0.05, 0.0), [], []
        for k, cl in enumerate(clauses):
            buf.append(cl)
            d = bounds[k] - start
            nxt = bounds[k + 1] - start if k + 1 < len(clauses) else None
            strong = bool(re.search(r"[。？！…—]$", cl))
            if (d >= 3.5 and (strong or d >= 6.0)) or (nxt is not None and nxt > 9.5 and d >= MIN_S) or nxt is None:
                pieces.append([start, bounds[k], "".join(buf)])
                start, buf = bounds[k], []
        if len(pieces) >= 2 and pieces[-1][1] - pieces[-1][0] < MIN_S and pieces[-1][1] - pieces[-2][0] <= MAX_S:
            tail = pieces.pop()                           # 句尾零頭併回前一片
            pieces[-1] = [pieces[-1][0], tail[1], pieces[-1][2] + tail[2]]
        errs = []                                         # 逐片回檢，用來在兩種對齊法之間選
        for s, e, t in pieces:
            sf.write(f"{OUT}/tmp16k/_probe.wav", data[int(s * sr):int(e * sr)], sr)
            errs.append(cer(t, recognize(f"{OUT}/tmp16k/_probe.wav")[0]))
        return pieces, float(np.mean(errs))

    tried = {how: cut(how) for how in (["逐字時間戳"] if timed and hit / max(len(ref_u), 1) >= 0.5 else []) + ["字數比例"]}
    how = min(tried, key=lambda h: tried[h][1])           # 平均字錯率低的那種；相同時取逐字時間戳
    for n, (s, e, t) in enumerate(tried[how][0], 1):
        add_ref(f"{c['id']}_s{n}", "切片", [c["id"]], t, data[int(s * sr):int(e * sr)], sr,
                span=[round(s, 2), round(e, 2)], align=how)

short = sorted([c for c in clips if c["dur"] < MIN_S and c.get("f0_median") and units(c["text"]) >= 2],
               key=lambda c: (-c["f0_median"], c["id"]))  # 3) 短句依音高由高到低，相鄰的接成一段
groups, cur = [], []
for c in short:
    cur.append(c)
    if sum(x["speech_s"] + GAP_S for x in cur) - GAP_S >= 3.5:
        groups.append(cur)
        cur = []
if cur:
    if groups and sum(x["speech_s"] + GAP_S for x in groups[-1] + cur) <= MAX_S:
        groups[-1] += cur
    else:
        groups.append(cur)
for n, g in enumerate(groups, 1):
    parts, sr0 = [], None
    for c in g:
        data, sr = load_mono(f"{OUT}/audio/{c['file']}")
        if sr0 is None:
            sr0 = sr
        elif sr != sr0:
            data = librosa.resample(data, orig_sr=sr, target_sr=sr0)
        iv = intervals(data)                              # 去掉頭尾靜音，各留 0.05 秒
        pad = int(0.05 * sr0)
        data = data[max(iv[0][0] - pad, 0):iv[-1][1] + pad] if len(iv) else data
        parts += [data, np.zeros(int(GAP_S * sr0))]
    add_ref(f"mix_{n:02d}", "拼接", [c["id"] for c in g], spoken("".join(c["text"] for c in g)),
            np.concatenate(parts[:-1]), sr0)

for r in refs:                                            # 逐段量測與文字回檢
    r.update(acoustic(r["path"], r["text"]) or dict(dur=0.0))
    hyp, _ = recognize(r["path"])
    r["asr"] = hyp
    r["align_cer"] = cer(r["text"], hyp)
    r["align_cer_strict"] = cer(r["text"], hyp, by_sound=False)
    r["emotion"] = emotion(r["path"])
    r["emotion_top"] = max(r["emotion"], key=r["emotion"].get)
    r["f0_rel_st"] = (round(float(12 * np.log2(r["f0_median"] / med["f0_median"])), 2)
                      if r.get("f0_median") and med.get("f0_median") else None)   # 相對該角色全部語音的中位數
    why = []
    if not MIN_S <= r["dur"] <= MAX_S:
        why.append(f"長度 {r['dur']} 秒不在 {MIN_S:g}–{MAX_S:g} 秒")
    if r["kind"] == "切片" and r["align_cer"] > CER_MAX:   # 原句與拼接沒有切錯位置的問題，字錯率只記錄不淘汰
        why.append(f"文字回檢字錯率 {r['align_cer']} > {CER_MAX}")
    r["usable"], r["unusable_why"] = not why, "；".join(why) or None
    print({k: r.get(k) for k in ("id", "kind", "dur", "rate", "f0_median", "align", "align_cer", "usable")},
          r["emotion_top"], flush=True)
ok = [r for r in refs if r["usable"]]
for key, labels in (("rate", ["慢", "中", "快"]), ("f0_median", ["低", "中", "高"]),
                    ("f0_std_st", ["平", "中", "起伏大"]), ("centroid", ["柔", "中", "亮"])):
    tercile_tags(ok, key, labels)
if not HOMOPHONE:
    notes.append("環境裡沒有 pypinyin，文字回檢沒有做同音字歸一（專有名詞容易被誤判成字錯）")

emo_count = {}
for r in ok:
    emo_count[r["emotion_top"]] = emo_count.get(r["emotion_top"], 0) + 1
stats = dict(
    n_voice_lines=len(table), n_clips=len(clips),
    clips_short=sum(c["dur"] < MIN_S for c in clips), clips_mid=sum(MIN_S <= c["dur"] <= MAX_S for c in clips),
    clips_long=sum(c["dur"] > MAX_S for c in clips),
    n_refs=len(refs), n_usable=len(ok), usable_by_kind={k: sum(r["kind"] == k for r in ok) for k in ("原句", "切片", "拼接")},
    usable_by_emotion=dict(sorted(emo_count.items(), key=lambda x: -x[1])),
    usable_raised_pitch=sum((r["f0_rel_st"] or 0) >= 2.0 for r in ok),     # 音高比本人中位數高 2 個半音以上
    usable_lowered_pitch=sum((r["f0_rel_st"] or 0) <= -2.0 for r in ok),
    slices_by_align={k: sum(r["align"] == k for r in refs) for k in ("逐字時間戳", "字數比例")},
    sources=sorted({c["source"] for c in clips}))
char = dict(key=KEY, id=CHAR_ID, name=NAME)
dump = dict(ensure_ascii=False, indent=1)
json.dump(dict(char=char, median=med, notes=notes, clips=clips), open(f"{OUT}/catalog.json", "w", encoding="utf-8"), **dump)
json.dump(dict(char=char, median=med, stats=stats, notes=notes, refs=refs), open(f"{OUT}/refs.json", "w", encoding="utf-8"), **dump)
HIDE = {"text", "path", "asr"}                    # 入庫摘要：不含台詞原文、辨識文字與路徑
json.dump(dict(char=char, median=med, stats=stats, notes=notes,
               clips=[{k: v for k, v in c.items() if k not in ("text",)} for c in clips],
               refs=[{k: v for k, v in r.items() if k not in HIDE} for r in refs]),
          open(f"{OUT}/summary.json", "w", encoding="utf-8"), **dump)

# ----------------------------------------------------------------- 頁面 ------
esc = html.escape


def player(rel):
    return f'<audio controls preload="none" src="{esc(rel)}"></audio>'


def top3(e):
    return "<br>".join(f"{k} {v:.2f}" for k, v in sorted(e.items(), key=lambda x: -x[1])[:3])


ref_rows = "".join(
    f"<tr class=\"{'' if r['usable'] else 'bad'}\"><td>{r['id']}<br><small>{r['kind']}：{'＋'.join(r['src'])}<br>{esc('／'.join(r['titles']))}</small></td>"
    f"<td>{esc(r['text'])}<br><small>辨識：{esc(r['asr'])}</small></td><td>{player('segments/' + r['id'] + '.wav')}</td><td>{r['dur']}</td>"
    f"<td>{r.get('rate')}<br><small>{r.get('rate_tag') or ''}</small></td>"
    f"<td>{r.get('f0_median')}<br><small>{r.get('f0_median_tag') or ''} {r['f0_rel_st'] if r['f0_rel_st'] is not None else ''}</small></td>"
    f"<td>{r.get('f0_std_st')}<br><small>{r.get('f0_std_st_tag') or ''}</small></td><td>{r.get('centroid')}<br><small>{r.get('centroid_tag') or ''}</small></td>"
    f"<td><small>{top3(r['emotion'])}</small></td><td>{r['align_cer']}<br><small>{r['align'] or ''}</small></td>"
    f"<td>{'✓' if r['usable'] else '✗<br><small>' + esc(r['unusable_why']) + '</small>'}</td></tr>" for r in refs)
clip_rows = "".join(
    f"<tr><td>{c['id']}<br><small>{esc(c['title'])}</small></td><td>{esc(c['text'])}</td>"
    f"<td>{player('audio/' + c['file'])}</td><td>{c['dur']}</td>"
    f"<td>{c['rate']}<br><small>{c['rate_tag'] or ''}</small></td><td>{c['n_pauses']}<br><small>{round(c['pause_ratio'] * 100)}%</small></td>"
    f"<td>{c['f0_median']}<br><small>{c['f0_median_tag'] or ''}</small></td><td>{c['f0_std_st']}<br><small>{c['f0_std_st_tag'] or ''}</small></td>"
    f"<td>{c['dyn_db']}</td><td>{int(c['centroid'])}<br><small>{c['centroid_tag'] or ''}</small></td>"
    f"<td><small>{top3(c['emotion'])}</small></td></tr>" for c in clips)
page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(NAME)} 參考音目錄</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:22px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:200px;min-width:180px}}small{{color:#555}}tr.bad td{{background:#f6eded}}</style></head><body>
<h1>{esc(NAME)}（{CHAR_ID}）：參考音目錄</h1>
{''.join(f'<p style="color:#b00">{esc(n)}</p>' for n in notes)}
<p>{len(clips)} 句原聲（短於 3 秒 {stats['clips_short']}、3–10 秒 {stats['clips_mid']}、長於 10 秒 {stats['clips_long']}）→ {len(refs)} 段參考音，其中 <b>{len(ok)} 段可用</b>
（原句 {stats['usable_by_kind']['原句']}、切片 {stats['usable_by_kind']['切片']}、拼接 {stats['usable_by_kind']['拼接']}）。
本人全部語音的中位數：語速 {med['rate']} 字/秒、音高 {med['f0_median']} Hz、音高起伏 {med['f0_std_st']} 半音、頻譜質心 {int(med['centroid'])} Hz。</p>
<h2>一、參考音（原句、切片、拼接）</h2>
<p>語速單位是字/秒（扣掉停頓）。音高欄第二行是相對本人中位數的半音數。標籤是可用參考音之間的三等分。
情緒欄是 emotion2vec 模型的前三名，只能當分群線索。「回檢」是文字與語音辨識結果的字錯率（同音字不算錯），超過 {CER_MAX} 標為不可用。</p>
<table><tr><th>編號/來源</th><th>文字</th><th>播放</th><th>長度</th><th>語速</th><th>音高 Hz</th><th>起伏 半音</th><th>質心 Hz</th><th>情緒模型</th><th>回檢</th><th>可用</th></tr>{ref_rows}</table>
<h2>二、{len(clips)} 句原聲逐句量測</h2>
<table><tr><th>編號/場合</th><th>台詞</th><th>播放</th><th>長度</th><th>語速</th><th>停頓 次/佔比</th><th>音高 Hz</th><th>起伏 半音</th>
<th>動態 dB</th><th>質心 Hz</th><th>情緒模型</th></tr>{clip_rows}</table></body></html>"""
open(f"{OUT}/catalog.html", "w", encoding="utf-8").write(page)
shutil.rmtree(f"{OUT}/tmp16k", ignore_errors=True)
print("CATALOG_DONE", json.dumps(dict(char=char, stats=stats, notes=notes), ensure_ascii=False), flush=True)
