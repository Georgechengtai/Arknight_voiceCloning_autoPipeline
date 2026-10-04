"""第二輪劇情台詞合成：參考音改由音頻量測挑選，短句另試放慢語速。

依序執行（由 round2.sh 呼叫；需先跑過 ref_catalog.py 與 gsv_finetune.sh）：
    python round2.py segments   # aktts 環境：長句切片、短句拼接、逐段量測、挑參考音，寫 plan.json
    python round2.py gsv        # aktts-gsv 環境、GPT-SoVITS 倉庫目錄：微調後模型合成
    python round2.py idx        # aktts 環境、index-tts 倉庫目錄：IndexTTS-2 合成
    python round2.py report     # aktts 環境：語速、聲紋相似度與試聽頁

挑參考音的規則（全部依量測，不看台詞文字）：
  急促 A/B：短於 3 秒的原聲裡音高中位數最高的幾句，接成 3–10 秒（GPT-SoVITS 不收短於 3 秒的參考音）。
  感傷 1/2：長句切出的 3.5–9.5 秒片段中，情緒模型「难过」分數最高、且來自不同原句的兩段。
  切片的文字對齊用語音辨識回檢，字錯率超過 0.15 的片段不拿來當參考音。
"""
import json
import os
import re
import sys
import time
from types import SimpleNamespace

import numpy as np
import soundfile as sf

ROOT = os.environ["AKTTS_ROOT"]
sys.path.insert(0, ROOT)
KEY = "kalts"
REF = f"{ROOT}/work/refs/{KEY}"
R2 = f"{ROOT}/work/round2_{KEY}"
SEED = 1234
SR, HOP, FRAME = 16000, 256, 1024
STORY = [("story1", "Monster，切开门！", "urgent"), ("story2", "阿米娅！博士！", "urgent"),
         ("story3", "特蕾西娅……", "sad"), ("story4", "我明知道这样的可能性始终存在……为什么……", "sad"),
         ("story5", "我应该留下，是我……", "sad")]
CALM = "CN_011"
SPOKEN = lambda t: t.replace("Mon3tr", "Monster")   # 參考音文字照她實際念法寫


def units(text):
    return len(re.findall(r"[一-鿿]", text)) + 2 * len(re.findall(r"[A-Za-z0-9]+", text))


def features(path, text):
    import librosa
    y, _ = librosa.load(path, sr=SR, mono=True)
    iv = librosa.effects.split(y, top_db=35, frame_length=FRAME, hop_length=HOP)
    speech = float(sum(e - s for s, e in iv)) / SR
    f0, _, _ = librosa.pyin(y, fmin=70, fmax=500, sr=SR, frame_length=FRAME, hop_length=HOP)
    f0v = f0[~np.isnan(f0)]
    st = 12 * np.log2(f0v / np.median(f0v)) if len(f0v) > 5 else np.zeros(1)
    cen = librosa.feature.spectral_centroid(y=y, sr=SR, n_fft=FRAME, hop_length=HOP)[0]
    return dict(dur=round(len(y) / SR, 2), rate=round(units(text) / max(speech, 1e-6), 2),
                f0_median=round(float(np.median(f0v)), 1) if len(f0v) > 5 else None,
                f0_std_st=round(float(np.std(st)), 2), centroid=round(float(np.mean(cen)), 0))


# ------------------------------------------------------------- segments ------
def segments():
    import librosa
    import real_ab as R
    from funasr import AutoModel
    cat = json.load(open(f"{REF}/catalog.json", encoding="utf-8"))
    clips = {c["id"]: c for c in cat["clips"]}
    os.makedirs(f"{REF}/segments", exist_ok=True)
    refs = []

    for vid, c in clips.items():                      # 1) 3–10 秒的原句直接可用
        if 3.0 <= c["dur"] <= 10.0:
            p = f"{REF}/segments/{vid}.wav"
            data, sr = sf.read(f"{REF}/audio/{vid}.mp3")
            sf.write(p, data, sr)
            refs.append(dict(id=vid, kind="原句", src=[vid], text=SPOKEN(c["text"]), path=p))

    for vid, c in clips.items():                      # 2) 長句按停頓切片
        if c["dur"] <= 10.0:
            continue
        data, sr = sf.read(f"{REF}/audio/{vid}.mp3")
        y = librosa.resample(data if data.ndim == 1 else data.mean(axis=1), orig_sr=sr, target_sr=SR)
        iv = librosa.effects.split(y, top_db=35, frame_length=FRAME, hop_length=HOP) / SR
        speech_total = float(sum(e - s for s, e in iv))
        gaps = [((iv[i][1] + iv[i + 1][0]) / 2) for i in range(len(iv) - 1) if iv[i + 1][0] - iv[i][1] >= 0.15]

        def time_at(frac):                            # 假設發聲時間內語速均勻，由字數比例推時間
            need = frac * speech_total
            for s, e in iv:
                if need <= e - s:
                    return s + need
                need -= e - s
            return iv[-1][1]

        clauses = re.findall(r"[^，。？！…、]+[，。？！…、]*", c["text"])
        total_u = sum(units(x) for x in clauses) or 1
        bounds, acc = [], 0
        for cl in clauses[:-1]:                       # 每個子句結束的時間：推估後吸附到最近的停頓
            acc += units(cl)
            est = time_at(acc / total_u)
            near = min(gaps, key=lambda g: abs(g - est)) if gaps else est
            bounds.append(near if abs(near - est) <= 0.6 else est)
        bounds.append(float(iv[-1][1]) + 0.05)
        start, buf, n = max(float(iv[0][0]) - 0.05, 0.0), [], 0
        for k, cl in enumerate(clauses):
            buf.append(cl)
            d = bounds[k] - start
            nxt = bounds[k + 1] - start if k + 1 < len(clauses) else None
            strong = bool(re.search(r"[。？！…]$", cl))
            if (d >= 3.5 and (strong or d >= 6.0)) or (nxt is not None and nxt > 9.5 and d >= 3.0) or nxt is None:
                n += 1
                p = f"{REF}/segments/{vid}_s{n}.wav"
                sf.write(p, data[int(start * sr):int(bounds[k] * sr)], sr)
                refs.append(dict(id=f"{vid}_s{n}", kind="切片", src=[vid], text="".join(buf), path=p))
                start, buf = bounds[k], []

    def composite(cid, vids):                         # 3) 短句拼接（中間留 0.25 秒）
        parts, sr = [], None
        for v in vids:
            d, sr = sf.read(f"{REF}/audio/{v}.mp3")
            parts += [d if d.ndim == 1 else d.mean(axis=1), np.zeros(int(0.25 * sr))]
        p = f"{REF}/segments/{cid}.wav"
        sf.write(p, np.concatenate(parts[:-1]), sr)
        refs.append(dict(id=cid, kind="拼接", src=vids, text=SPOKEN("".join(clips[v]["text"] for v in vids)), path=p))

    short_high = sorted([c for c in clips.values() if c["dur"] < 3.0 and c.get("f0_median") and units(c["text"]) >= 3],
                        key=lambda c: -c["f0_median"])
    a, b = [], []
    for c in short_high:                              # 依音高由高到低，A 取較長的、B 取其餘，各湊到 ≥3.2 秒
        tgt = a if (sum(clips[v]["dur"] + 0.25 for v in a) < 3.2 and c["dur"] >= 2.0) else b
        if sum(clips[v]["dur"] + 0.25 for v in tgt) < 3.2:
            tgt.append(c["id"])
    composite("urgentA", a)
    composite("urgentB", b)

    asr = AutoModel(model="paraformer-zh", disable_update=True)
    emo = AutoModel(model="iic/emotion2vec_plus_large", disable_update=True)
    for r in refs:
        r.update(features(r["path"], r["text"]))
        hyp = asr.generate(input=R.to16k(r["path"]))[0]["text"]
        r["align_cer"] = R.cer(r["text"], hyp)
        res = emo.generate(r["path"], granularity="utterance", extract_embedding=False)[0]
        r["emotion"] = {lab.split("/")[0]: round(float(s), 3) for lab, s in zip(res["labels"], res["scores"])}
        r["usable"] = bool(3.0 <= r["dur"] <= 10.0 and r["align_cer"] <= 0.15)
        print({k: r[k] for k in ("id", "kind", "dur", "rate", "f0_median", "align_cer", "usable")},
              max(r["emotion"], key=r["emotion"].get), r["text"][:24], flush=True)

    by = {r["id"]: r for r in refs}
    sad = sorted([r for r in refs if r["kind"] == "切片" and r["usable"] and 3.5 <= r["dur"] <= 9.5],
                 key=lambda r: (-r["emotion"].get("难过", 0), r["rate"]))
    sad1 = sad[0]
    sad2 = next(r for r in sad[1:] if r["src"] != sad1["src"])
    plan = dict(calm=by[CALM]["id"], urgentA="urgentA", urgentB="urgentB", sad1=sad1["id"], sad2=sad2["id"])
    json.dump(dict(refs=refs, plan=plan), open(f"{REF}/refs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_seg = sum(r["kind"] == "切片" for r in refs)
    print("SEGMENTS_DONE", json.dumps(dict(n_refs=len(refs), n_segments=n_seg, n_usable=sum(r["usable"] for r in refs),
                                           composites=dict(urgentA=a, urgentB=b), plan=plan), ensure_ascii=False), flush=True)


def load_plan():
    d = json.load(open(f"{REF}/refs.json", encoding="utf-8"))
    return {r["id"]: r for r in d["refs"]}, d["plan"]


def variants(engine):
    """每句台詞要試的做法：(做法代號, 說明, 參數)。"""
    out = []
    for line, text, kind in STORY:
        if engine == "gsv":
            pri, alt = ("urgentA", "urgentB") if kind == "urgent" else ("sad1", "sad2")
            slow = 0.8 if kind == "urgent" else 0.85
            out += [(line, text, f"{pri}_x1", dict(ref=pri, speed=1.0)), (line, text, f"{pri}_slow", dict(ref=pri, speed=slow)),
                    (line, text, f"{alt}_slow", dict(ref=alt, speed=slow))]
        else:
            e = "urgentA" if kind == "urgent" else "sad1"
            out += [(line, text, f"emo_{e}", dict(spk="calm", emo=e)), (line, text, f"spk_{e}", dict(spk=e, emo=None))]
    return out


# ------------------------------------------------------------------ gsv ------
def gsv():
    import torch
    import gsv_pipeline as G
    os.environ.update(version=G.VERSION, gpt_path=G.S1, sovits_path=G.S2G, is_half="True")
    from tools.i18n.i18n import I18nAuto
    from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
    i18n = I18nAuto(language=os.environ.get("language", "Auto"))
    refs, plan = load_plan()
    lang = lambda t: i18n("中英混合") if re.search(r"[A-Za-z]", t) else i18n("中文")
    change_gpt_weights(gpt_path=G.latest(f"GPT_weights_{G.VERSION}/{G.EXP}-e*.ckpt", r"-e(\d+)\.ckpt"))
    for _ in change_sovits_weights(sovits_path=G.latest(f"SoVITS_weights_{G.VERSION}/{G.EXP}_e*_s*.pth", r"_e(\d+)_s"),
                                   prompt_language=i18n("中文"), text_language=i18n("中文")):
        pass
    aux = [SimpleNamespace(name=f"{REF}/audio/{v}.mp3") for v in G.AUX_REFS]
    os.makedirs(f"{R2}/gsv", exist_ok=True)
    rows = []
    for line, text, tag, p in variants("gsv"):
        r = refs[plan[p["ref"]]]
        path = f"{R2}/gsv/{line}_{tag}.wav"
        torch.manual_seed(SEED)
        try:
            out = list(get_tts_wav(ref_wav_path=r["path"], prompt_text=r["text"], prompt_language=lang(r["text"]),
                                   text=text, text_language=lang(text), how_to_cut=i18n("不切"),
                                   top_k=15, top_p=1, temperature=1, speed=p["speed"], inp_refs=aux))
            sr, audio = out[-1]
            sf.write(path, audio, sr)
            rows.append(dict(engine="GPT-SoVITS", line=line, text=text, tag=tag, ok=True, path=path,
                             cond=f"參考音 {p['ref']}（{r['id']}），語速 ×{p['speed']}"))
        except Exception as e:
            rows.append(dict(engine="GPT-SoVITS", line=line, text=text, tag=tag, ok=False, error=repr(e)[:300]))
        print(rows[-1], flush=True)
    json.dump(rows, open(f"{R2}/gsv/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"GSV_DONE ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


# ------------------------------------------------------------------ idx ------
def idx():
    import torch
    from indextts.infer_v2 import IndexTTS2
    md = f"{ROOT}/models/IndexTTS-2"
    tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
    refs, plan = load_plan()
    os.makedirs(f"{R2}/idx", exist_ok=True)
    rows = []
    for line, text, tag, p in variants("idx"):
        spk = refs[plan[p["spk"]]]
        path = f"{R2}/idx/{line}_{tag}.wav"
        kw = dict(emo_audio_prompt=refs[plan[p["emo"]]]["path"], emo_alpha=0.8) if p["emo"] else {}
        torch.manual_seed(SEED)
        try:
            tts.infer(spk_audio_prompt=spk["path"], text=text, output_path=path, verbose=False, **kw)
            cond = (f"音色 {spk['id']}＋情緒參考音 {p['emo']}（{refs[plan[p['emo']]]['id']}，強度 0.8）" if p["emo"]
                    else f"音色與語氣都用 {p['spk']}（{spk['id']}）")
            rows.append(dict(engine="IndexTTS-2", line=line, text=text, tag=tag, ok=True, path=path, cond=cond))
        except Exception as e:
            rows.append(dict(engine="IndexTTS-2", line=line, text=text, tag=tag, ok=False, error=repr(e)[:300]))
        print(rows[-1], flush=True)
    json.dump(rows, open(f"{R2}/idx/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"IDX_DONE ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


# --------------------------------------------------------------- report ------
def report():
    import html
    import real_ab as R
    from funasr import AutoModel
    refs, plan = load_plan()
    cat = json.load(open(f"{REF}/catalog.json", encoding="utf-8"))
    rows = json.load(open(f"{R2}/gsv/rows.json", encoding="utf-8")) + json.load(open(f"{R2}/idx/rows.json", encoding="utf-8"))
    for i, (line, text, _) in enumerate(STORY, 1):    # 上一輪的做法當對照
        rows.append(dict(engine="IndexTTS-2", line=line, text=text, tag="prev", ok=True,
                         path=f"{R.WORK}/gen/v2/{KEY}_story{i}_none.wav", cond="上一輪：參考音 CN_011，不控情緒"))
        rows.append(dict(engine="GPT-SoVITS", line=line, text=text, tag="prev", ok=True,
                         path=f"{ROOT}/work/gsv_{KEY}/gen/ft/story{i}_calm.wav", cond="上一輪：參考音 CN_011，語速 ×1.0"))
    sv = AutoModel(model="cam++", disable_update=True)
    asr = AutoModel(model="paraformer-zh", disable_update=True)

    def emb(p):
        e = sv.generate(input=R.to16k(p))[0]["spk_embedding"]
        e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
        return e / (np.linalg.norm(e) + 1e-9)

    cen = np.mean([emb(R.orig(KEY, v)) for v in R.CHARS[KEY]["pool"]], axis=0)
    cen /= np.linalg.norm(cen)
    for r in rows:
        if r["ok"] and os.path.exists(r["path"]):
            r.update(features(r["path"], r["text"]))
            r["sim"] = round(float(emb(r["path"]) @ cen), 3)
            r["asr"] = asr.generate(input=R.to16k(r["path"]))[0]["text"].replace(" ", "")
    short = sorted(c["rate"] for c in cat["clips"] if c["dur"] < 1.2)
    json.dump(dict(plan=plan, rows=[{k: v for k, v in r.items() if k != "path"} for r in rows]),
              open(f"{R2}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    esc = html.escape
    ref_rows = "".join(
        f"<tr><td>{k}</td><td>{refs[v]['id']}<br><small>{refs[v]['kind']}：{'＋'.join(refs[v]['src'])}</small></td>"
        f"<td>{esc(refs[v]['text'])}</td><td>{R.audio_tag(refs[v]['path'])}</td><td>{refs[v]['dur']}</td><td>{refs[v]['rate']}</td>"
        f"<td>{refs[v]['f0_median']}</td><td><small>{esc(json.dumps(dict(sorted(refs[v]['emotion'].items(), key=lambda x: -x[1])[:3]), ensure_ascii=False))}</small></td></tr>"
        for k, v in plan.items())
    body = ""
    for line, text, _ in STORY:
        body += f"<h3>{esc(text)}</h3><table><tr><th>引擎</th><th>做法</th><th>播放</th><th>長度</th><th>語速</th><th>相似度</th><th>辨識</th></tr>"
        for r in sorted([x for x in rows if x["line"] == line], key=lambda x: (x["engine"], x["tag"] != "prev", x["tag"])):
            if r["ok"]:
                body += (f"<tr><td>{r['engine']}</td><td>{esc(r['cond'])}</td><td>{R.audio_tag(r['path'])}</td><td>{r['dur']}</td>"
                         f"<td><b>{r['rate']}</b></td><td>{r['sim']}</td><td><small>{esc(r['asr'])}</small></td></tr>")
            else:
                body += f"<tr><td>{r['engine']}</td><td>{r['tag']}</td><td colspan=5><i>失敗：{esc(r['error'][:120])}</i></td></tr>"
        body += "</table>"
    all_refs = "".join(
        f"<tr><td>{r['id']}<br><small>{r['kind']}</small></td><td>{esc(r['text'])}</td><td>{R.audio_tag(r['path'])}</td><td>{r['dur']}</td>"
        f"<td>{r['rate']}</td><td>{r['f0_median']}</td><td>{r['f0_std_st']}</td>"
        f"<td><small>{esc(json.dumps(dict(sorted(r['emotion'].items(), key=lambda x: -x[1])[:2]), ensure_ascii=False))}</small></td>"
        f"<td>{r['align_cer']}</td><td>{'✓' if r['usable'] else '✗'}</td></tr>" for r in refs.values())
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希 第二輪：量測選參考音</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:210px;min-width:190px}}small{{color:#555}}</style></head><body>
<h1>凯尔希 第二輪：參考音由量測挑選</h1>
<p>語速單位是字/秒（扣掉停頓）。她的原聲：全部 38 句中位數 {cat['median']['rate']}；短於 1.2 秒的短句是 {short[0]}–{short[-1]}。
每個條件只合成一次，固定隨機種子 {SEED}。相似度是聲紋相似度（上限 0.894）。</p>
<h2>一、這輪用到的參考音</h2>
<table><tr><th>用途</th><th>來源</th><th>文字</th><th>播放</th><th>長度</th><th>語速</th><th>音高 Hz</th><th>情緒模型前三</th></tr>{ref_rows}</table>
<h2>二、劇情台詞</h2>{body}
<h2>三、全部可選的參考音（原句、切片、拼接）</h2>
<p>「對齊」欄是切片文字與語音辨識結果的字錯率，超過 0.15 的不拿來用。</p>
<table><tr><th>編號</th><th>文字</th><th>播放</th><th>長度</th><th>語速</th><th>音高</th><th>起伏</th><th>情緒模型</th><th>對齊</th><th>可用</th></tr>{all_refs}</table>
</body></html>"""
    open(f"{R2}/report.html", "w", encoding="utf-8").write(page)
    print("ROUND2_REPORT_DONE", flush=True)


if __name__ == "__main__":
    {"segments": segments, "gsv": gsv, "idx": idx, "report": report}[sys.argv[1]]()
