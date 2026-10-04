"""參考音目錄：把一位幹員的全部中文原聲逐句做聲學分析，產生可查的目錄與試聽頁。

在 aktts 環境下執行： python ref_catalog.py <短名> <charId> <顯示名>
    例： python ref_catalog.py kalts char_003_kalts 凯尔希

量的是音頻本身，不看台詞文字猜語氣：
  語速（字/秒，扣掉停頓）、停頓次數與比例、音高中位數與起伏（半音）、音量動態範圍、
  頻譜質心（越高聽感越亮、越用力），以及語音情緒辨識模型 emotion2vec 的分數。
「慢/中/快」之類的標籤是相對於該角色自己 38 句的三等分，不是絕對標準。
另外把先前幾輪合成結果的語速也量出來，與原聲對照。
"""
import base64
import html
import json
import os
import re
import sys
import urllib.request

import librosa
import numpy as np

ROOT = os.environ["AKTTS_ROOT"]
KEY, CHAR_ID, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
OUT = f"{ROOT}/work/refs/{KEY}"
VOICE_SRC = "https://raw.githubusercontent.com/PseudoMon/arknights-audio/master/voice_cn"
TABLE_SRC = ("https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/"
             "zh_CN/gamedata/excel/charword_table.json")
SR, HOP, FRAME = 16000, 256, 1024


def fetch(url, path):
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(url, path)


def units(text):
    """可發音單位數：一個漢字算 1，一個英數詞算 2。"""
    return len(re.findall(r"[一-鿿]", text)) + 2 * len(re.findall(r"[A-Za-z0-9]+", text))


def acoustic(path, text):
    y, _ = librosa.load(path, sr=SR, mono=True)
    iv = librosa.effects.split(y, top_db=35, frame_length=FRAME, hop_length=HOP)
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
    lo, hi = np.percentile(vals, [33.3, 66.7])
    for r in rows:
        v = r.get(key)
        r[key + "_tag"] = None if v is None else labels[0] if v <= lo else labels[2] if v > hi else labels[1]


def audio_tag(path):
    mime = "audio/mpeg" if path.endswith(".mp3") else "audio/wav"
    return f'<audio controls preload="none" src="data:{mime};base64,{base64.b64encode(open(path, "rb").read()).decode()}"></audio>'


# ------------------------------------------------------------ 原聲目錄 ------
fetch(TABLE_SRC, f"{ROOT}/work/refs/charword_table.json")
table = {}
for v in json.load(open(f"{ROOT}/work/refs/charword_table.json", encoding="utf-8"))["charWords"].values():
    if v.get("charId") == CHAR_ID and v["voiceId"].startswith("CN_") and v["voiceId"] not in table:
        text = v["voiceText"].replace("Dr.{@nickname}", "博士").replace("{@nickname}", "博士")
        table[v["voiceId"]] = dict(id=v["voiceId"], title=v.get("voiceTitle", ""), text=re.sub(r"\s+", "", text))
rows = []
for vid in sorted(table):
    p = f"{OUT}/audio/{vid}.mp3"
    try:
        fetch(f"{VOICE_SRC}/{CHAR_ID}/{vid}.mp3", p)
        a = acoustic(p, table[vid]["text"])
    except Exception as e:
        print("skip", vid, repr(e), flush=True)
        continue
    if a:
        rows.append(dict(table[vid], **a))

notes = []
try:  # 語音情緒辨識（只當參考，動畫式演出的準確度有限）
    from funasr import AutoModel
    emo = AutoModel(model="iic/emotion2vec_plus_large", disable_update=True)
    for r in rows:
        res = emo.generate(f"{OUT}/audio/{r['id']}.mp3", granularity="utterance", extract_embedding=False)[0]
        pairs = sorted(zip(res["labels"], res["scores"]), key=lambda x: -x[1])[:3]
        r["emotion"] = [[lab.split("/")[0], round(float(s), 2)] for lab, s in pairs]
except Exception as e:
    notes.append(f"情緒辨識失敗：{e!r}")

tercile_tags(rows, "rate", ["慢", "中", "快"])
tercile_tags(rows, "f0_median", ["低", "中", "高"])
tercile_tags(rows, "f0_std_st", ["平", "中", "起伏大"])
tercile_tags(rows, "centroid", ["柔", "中", "亮"])
for r in rows:
    r["ok_gptsovits"] = 3.0 <= r["dur"] <= 10.0        # GPT-SoVITS 硬性要求 3–10 秒
    r["ok_indextts"] = r["dur"] >= 3.0                  # IndexTTS 超過 15 秒會截斷
med = {k: round(float(np.median([r[k] for r in rows if r.get(k) is not None])), 2)
       for k in ("rate", "rate_span", "f0_median", "f0_std_st", "dyn_db", "centroid", "dur")}

# ------------------------------------------------- 合成結果的語速對照 ------
gen = []


def add_gen(engine, cond, line, text, path):
    if os.path.exists(path):
        a = acoustic(path, text)
        if a:
            gen.append(dict(engine=engine, cond=cond, line=line, text=text, path=path, **a))


try:
    sys.path.insert(0, ROOT)
    import real_ab as R
    for it in R.build_items():
        if it["char"] == KEY:
            line = f"same_{it['orig']}" if it["section"] == "same" else f"story{it['line']}"
            add_gen("IndexTTS-2", it["mode"], line, it["text"], f"{R.WORK}/gen/v2/{it['id']}.wav")
    g = json.load(open(f"{ROOT}/work/gsv_{KEY}/gen/results.json", encoding="utf-8"))
    for r in g["rows"]:
        if r["ok"]:
            cond = "未微調" if r["tag"] == "base" else f"微調後，參考音 {r['ref']}"
            add_gen("GPT-SoVITS", cond, r["line"], r["text"], f"{ROOT}/work/gsv_{KEY}/gen/{r['tag']}/{r['id']}.wav")
except Exception as e:
    notes.append(f"合成結果語速對照未完成：{e!r}")
by_id = {r["id"]: r for r in rows}
for x in gen:
    o = by_id.get(x["line"].replace("same_", "")) if x["line"].startswith("same_") else None
    x["orig_rate"] = o["rate"] if o else None

os.makedirs(OUT, exist_ok=True)
json.dump(dict(char=dict(key=KEY, id=CHAR_ID, name=NAME), median=med, notes=notes, clips=rows,
               generated=[{k: v for k, v in x.items() if k != "path"} for x in gen]),
          open(f"{OUT}/catalog.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ----------------------------------------------------------------- 頁面 ------
esc = html.escape
gen_rows = "".join(
    f"<tr><td>{esc(x['text'][:26])}{'…' if len(x['text']) > 26 else ''}</td><td>{x['engine']}</td><td>{esc(x['cond'])}</td>"
    f"<td>{audio_tag(x['path'])}</td><td>{x['dur']}</td><td><b>{x['rate']}</b></td>"
    f"<td>{x['orig_rate'] if x['orig_rate'] else '—'}</td><td>{round(x['rate'] / med['rate'], 2)}</td></tr>"
    for x in sorted(gen, key=lambda x: (x["line"], x["engine"], x["cond"])))
clip_rows = "".join(
    f"<tr><td>{r['id']}<br><small>{esc(r['title'])}</small></td><td>{esc(r['text'])}</td>"
    f"<td>{audio_tag(OUT + '/audio/' + r['id'] + '.mp3')}</td><td>{r['dur']}</td>"
    f"<td>{r['rate']}<br><small>{r['rate_tag']}</small></td><td>{r['n_pauses']}<br><small>{round(r['pause_ratio'] * 100)}%</small></td>"
    f"<td>{r['f0_median']}<br><small>{r['f0_median_tag']}</small></td><td>{r['f0_std_st']}<br><small>{r['f0_std_st_tag']}</small></td>"
    f"<td>{r['dyn_db']}</td><td>{int(r['centroid'])}<br><small>{r['centroid_tag']}</small></td>"
    f"<td><small>{'<br>'.join(f'{e} {s}' for e, s in r.get('emotion', [])) or '—'}</small></td>"
    f"<td><small>{'GPT-SoVITS ✓' if r['ok_gptsovits'] else 'GPT-SoVITS ✗'}<br>{'IndexTTS ✓' if r['ok_indextts'] else 'IndexTTS ✗'}</small></td></tr>"
    for r in rows)
page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(NAME)} 參考音目錄</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:22px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:200px;min-width:180px}}small{{color:#555}}</style></head><body>
<h1>{esc(NAME)}：參考音目錄與語速對照</h1>
{''.join(f'<p style="color:#b00">{esc(n)}</p>' for n in notes)}
<h2>一、語速：原聲 對 合成</h2>
<p>語速＝字數 ÷ 實際發聲時間（停頓不算），單位字/秒。{esc(NAME)} {len(rows)} 句原聲的中位數是 <b>{med['rate']}</b> 字/秒。
最右欄是該段合成相對這個中位數的倍數，大於 1 表示比她平常快。</p>
<table><tr><th>台詞</th><th>引擎</th><th>做法</th><th>播放</th><th>長度(秒)</th><th>語速</th><th>同句原聲語速</th><th>相對她的中位數</th></tr>{gen_rows}</table>
<h2>二、{len(rows)} 句原聲逐句分析</h2>
<p>標籤（慢/中/快、低/中/高、平/起伏大、柔/亮）是相對她自己這 {len(rows)} 句的三等分。情緒欄是 emotion2vec 模型的前三名與分數，僅供參考。
中位數：語速 {med['rate']} 字/秒、音高 {med['f0_median']} Hz、音高起伏 {med['f0_std_st']} 半音、動態範圍 {med['dyn_db']} dB、頻譜質心 {int(med['centroid'])} Hz。</p>
<table><tr><th>編號/場合</th><th>台詞</th><th>播放</th><th>長度</th><th>語速</th><th>停頓 次/佔比</th><th>音高 Hz</th><th>起伏 半音</th>
<th>動態 dB</th><th>質心 Hz</th><th>情緒模型</th><th>可當參考音</th></tr>{clip_rows}</table></body></html>"""
open(f"{OUT}/catalog.html", "w", encoding="utf-8").write(page)
print("CATALOG_DONE", json.dumps(dict(n=len(rows), median=med, notes=notes, n_generated=len(gen)), ensure_ascii=False), flush=True)
