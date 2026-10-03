"""用幹員原聲當參考音，對比 IndexTTS-2 與 IndexTTS-2.5（設計決定 D3 的版本取捨用）。

用法（在 index-tts 倉庫目錄下、已 source env.sh）：
    python real_ab.py gen v2      # 用 IndexTTS-2 合成全部條目
    python real_ab.py gen v25     # 用 IndexTTS-2.5 合成全部條目
    python real_ab.py report      # 算聲紋相似度與字錯率，產生單檔試聽頁 report.html

原聲 MP3 由 real_ab.sh 預先下載到 $AKTTS_ROOT/work/real_ab/orig/<角色>/<語音編號>.mp3。
台詞取自 BB-ST-1「未完成的告别」與幹員語音表；「Mon3tr」在合成文字裡寫成「Monster」以便發音。
"""
import base64
import html
import io
import json
import os
import re
import sys
import time

import numpy as np
import soundfile as sf

ROOT = os.environ["AKTTS_ROOT"]
WORK = f"{ROOT}/work/real_ab"
SEED = 1234

# 情緒向量順序（IndexTTS-2）：[高興, 憤怒, 悲傷, 害怕, 厭惡, 低落, 驚訝, 平靜]
CHARS = {
    "kalts": {
        "name": "凯尔希", "char_id": "char_003_kalts",
        "ref": "CN_011", "ref_b": "CN_038", "emo_ref": "CN_032",
        "pool": ["CN_003", "CN_005", "CN_006", "CN_007", "CN_008", "CN_009"],
        "holdout": [
            ("CN_036", "你似乎更加适应自己的工作和职责了，更像一个领导者了。"),
            ("CN_002", "我会定期为你进行理学检查，记录你的生命征象与意识状态，其他人没有这个权限。"
                       "任何人想对你进行进一步的检查，你都有权拒绝，明白吗？"),
        ],
        "story": [
            ("Monster，切开门！", [0, 0.6, 0, 0.2, 0, 0, 0, 0], "憤怒 0.6＋害怕 0.2", True),
            ("阿米娅！博士！", [0, 0, 0, 0.6, 0, 0, 0.3, 0], "害怕 0.6＋驚訝 0.3", True),
            ("特蕾西娅……", [0, 0, 0.7, 0, 0, 0.2, 0, 0], "悲傷 0.7＋低落 0.2", False),
            ("我明知道这样的可能性始终存在……为什么……", [0, 0, 0.7, 0, 0, 0.3, 0, 0], "悲傷 0.7＋低落 0.3", False),
            ("我应该留下，是我……", [0, 0, 0.6, 0, 0, 0.4, 0, 0], "悲傷 0.6＋低落 0.4", False),
        ],
    },
    "ascln": {
        "name": "阿斯卡纶", "char_id": "char_4132_ascln",
        "ref": "CN_010", "ref_b": None, "emo_ref": None,
        "pool": ["CN_002", "CN_003", "CN_004", "CN_005", "CN_006", "CN_007"],
        "holdout": [
            ("CN_001", "不用看了，是我。情况有变，我替换了你之前的助理排班表。别紧张，你会习惯的。"),
            ("CN_011", "阿斯卡纶，有且只有这个称呼。名字也好，代号也罢，你随意填写就行。"
                       "但想更新我的档案，请先联系凯尔希医生。"),
        ],
        "story": [
            ("我不关心。", None, None, False),
            ("你会死，所以我给你最后的尊重。", None, None, False),
            ("死前少废话。", None, None, False),
            ("那你有看到过自己的结局吗？", None, None, False),
        ],
    },
}


def orig(char, vid):
    return f"{WORK}/orig/{char}/{vid}.mp3"


def ref_wav(char, vid):
    """IndexTTS 讀參考音用的 WAV（由 MP3 轉出，避免依賴 ffmpeg）。"""
    p = f"{WORK}/orig/{char}/{vid}.wav"
    if not os.path.exists(p):
        data, sr = sf.read(orig(char, vid))
        sf.write(p, data, sr)
    return p


def build_items():
    items = []
    for ck, c in CHARS.items():
        for vid, text in c["holdout"]:
            for tag, ref in (("refA", c["ref"]), ("refB", c["ref_b"])):
                if ref:
                    items.append(dict(id=f"{ck}_same_{vid}_{tag}", char=ck, section="same", text=text,
                                      ref=ref, mode=f"參考音 {ref}", orig=vid))
        for i, (text, vec, vec_label, use_emo_ref) in enumerate(c["story"], 1):
            base = dict(char=ck, section="story", text=text, ref=c["ref"], line=i)
            items.append(dict(base, id=f"{ck}_story{i}_none", mode="不控情緒"))
            if vec:
                items.append(dict(base, id=f"{ck}_story{i}_vec", mode=f"情緒向量：{vec_label}", emo_vector=vec))
            if use_emo_ref and c["emo_ref"]:
                items.append(dict(base, id=f"{ck}_story{i}_emoref", mode=f"情緒參考音 {c['emo_ref']}（強度 0.8）",
                                  emo_audio=c["emo_ref"]))
    return items


def gen(ver):
    import torch
    out_dir = f"{WORK}/gen/{ver}"
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    if ver == "v2":
        from indextts.infer_v2 import IndexTTS2
        md = f"{ROOT}/models/IndexTTS-2"
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md,
                        use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
        extra = {}
    elif ver == "v25":
        from indextts.infer_v2_5 import IndexTTS2
        md = f"{ROOT}/models/IndexTTS-2.5"
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_bf16=True)
        extra = {"lang": "ZH"}
    else:
        sys.exit("版本參數必須是 v2 或 v25")
    load_s = time.time() - t0
    rows = []
    for it in build_items():
        path = f"{out_dir}/{it['id']}.wav"
        kw = dict(extra)
        if it.get("emo_vector"):
            kw["emo_vector"] = it["emo_vector"]
        if it.get("emo_audio"):
            kw["emo_audio_prompt"] = ref_wav(it["char"], it["emo_audio"])
            kw["emo_alpha"] = 0.8
        torch.manual_seed(SEED)
        t1 = time.time()
        try:
            tts.infer(spk_audio_prompt=ref_wav(it["char"], it["ref"]), text=it["text"],
                      output_path=path, verbose=False, **kw)
            dur = sf.info(path).duration
            rows.append(dict(id=it["id"], ok=True, gen_s=round(time.time() - t1, 2), audio_s=round(dur, 2)))
        except Exception as e:  # 單句失敗不要拖垮整批
            rows.append(dict(id=it["id"], ok=False, error=repr(e)[:300]))
        print(f"[{ver}] {rows[-1]}", flush=True)
    ok = [r for r in rows if r["ok"]]
    summary = dict(version=ver, model_load_s=round(load_s, 1), gpu=torch.cuda.get_device_name(0),
                   peak_gpu_mem_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2),
                   mean_rtf=round(sum(r["gen_s"] for r in ok) / max(sum(r["audio_s"] for r in ok), 1e-6), 3),
                   n_ok=len(ok), n_fail=len(rows) - len(ok), rows=rows)
    json.dump(summary, open(f"{out_dir}/summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"GEN_DONE {ver} ok={len(ok)} fail={len(rows) - len(ok)} rtf={summary['mean_rtf']}", flush=True)


# ---------------------------------------------------------------- report ------
def to16k(path):
    import librosa
    tmp = f"{WORK}/tmp16k/{abs(hash(path))}.wav"
    if not os.path.exists(tmp):
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        y, _ = librosa.load(path, sr=16000, mono=True)
        sf.write(tmp, y, 16000)
    return tmp


def norm_text(s):
    return re.sub(r"[^0-9a-z一-鿿]", "", s.lower())


def cer(ref, hyp):
    r, h = norm_text(ref), norm_text(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return round(d[len(h)] / max(len(r), 1), 3)


def audio_tag(path):
    if not path or not os.path.exists(path):
        return "<i>（無）</i>"
    if path.endswith(".mp3"):
        mime, raw = "audio/mpeg", open(path, "rb").read()
    else:  # 生成的 WAV 轉成 FLAC 內嵌，體積減半、無損
        data, sr = sf.read(path)
        buf = io.BytesIO()
        sf.write(buf, data, sr, format="FLAC")
        mime, raw = "audio/flac", buf.getvalue()
    return f'<audio controls preload="metadata" src="data:{mime};base64,{base64.b64encode(raw).decode()}"></audio>'


def report():
    items = build_items()
    summ = {v: json.load(open(f"{WORK}/gen/{v}/summary.json", encoding="utf-8")) for v in ("v2", "v25")}
    gpath = lambda v, i: f"{WORK}/gen/{v}/{i}.wav"
    metrics, notes = {}, []

    # --- 聲紋相似度：每個角色用「沒當參考音的原聲」求平均聲紋當基準 ---
    try:
        from funasr import AutoModel
        sv = AutoModel(model="cam++", disable_update=True)

        def emb(p):
            e = sv.generate(input=to16k(p))[0]["spk_embedding"]
            e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
            return e / (np.linalg.norm(e) + 1e-9)

        pool = {ck: [emb(orig(ck, v)) for v in c["pool"]] for ck, c in CHARS.items()}
        cen = {ck: np.mean(p, axis=0) for ck, p in pool.items()}
        cen = {ck: v / np.linalg.norm(v) for ck, v in cen.items()}
        other = {"kalts": "ascln", "ascln": "kalts"}
        base = {}
        for ck, c in CHARS.items():
            hold = [float(emb(orig(ck, vid)) @ cen[ck]) for vid, _ in c["holdout"]]
            cross = [float(e @ cen[other[ck]]) for e in pool[ck]]
            base[ck] = dict(ceiling=round(float(np.mean(hold)), 3), floor=round(float(np.mean(cross)), 3))
        metrics["baseline"] = base
        for v in ("v2", "v25"):
            for it in items:
                if os.path.exists(gpath(v, it["id"])):
                    metrics.setdefault(v, {}).setdefault(it["id"], {})["sim"] = round(
                        float(emb(gpath(v, it["id"])) @ cen[it["char"]]), 3)
    except Exception as e:
        notes.append(f"聲紋相似度計算失敗：{e!r}")

    # --- 字錯率：語音辨識回轉文字後與原文比 ---
    try:
        from funasr import AutoModel
        asr = AutoModel(model="paraformer-zh", disable_update=True)
        for v in ("v2", "v25"):
            for it in items:
                if os.path.exists(gpath(v, it["id"])):
                    hyp = asr.generate(input=to16k(gpath(v, it["id"])))[0]["text"]
                    m = metrics.setdefault(v, {}).setdefault(it["id"], {})
                    m["asr"], m["cer"] = hyp, cer(it["text"], hyp)
    except Exception as e:
        notes.append(f"字錯率計算失敗：{e!r}")

    def mean(v, key, pred):
        xs = [metrics.get(v, {}).get(it["id"], {}).get(key) for it in items if pred(it)]
        xs = [x for x in xs if x is not None]
        return round(float(np.mean(xs)), 3) if xs else None

    agg = {v: {ck: dict(sim_same=mean(v, "sim", lambda it: it["char"] == ck and it["section"] == "same"),
                        sim_story=mean(v, "sim", lambda it: it["char"] == ck and it["section"] == "story"),
                        cer=mean(v, "cer", lambda it: it["char"] == ck)) for ck in CHARS} for v in ("v2", "v25")}
    json.dump(dict(summary={v: {k: s[k] for k in s if k != "rows"} for v, s in summ.items()},
                   metrics=metrics, aggregate=agg, notes=notes),
              open(f"{WORK}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # --- 試聽頁 ---
    def cell(v, it):
        m = metrics.get(v, {}).get(it["id"], {})
        info = []
        if "sim" in m:
            info.append(f"相似度 {m['sim']}")
        if "cer" in m:
            info.append(f"字錯率 {m['cer']}")
        asr_line = f"<br><small>辨識：{html.escape(m['asr'])}</small>" if m.get("asr") else ""
        return f"{audio_tag(gpath(v, it['id']))}<br><small>{'　'.join(info)}</small>{asr_line}"

    parts = []
    for ck, c in CHARS.items():
        b = metrics.get("baseline", {}).get(ck, {})
        parts.append(f"<h2>{c['name']}</h2><p>主參考音 {c['ref']}：{audio_tag(orig(ck, c['ref']))}"
                     + (f"　副參考音 {c['ref_b']}：{audio_tag(orig(ck, c['ref_b']))}" if c["ref_b"] else "")
                     + (f"　情緒參考音 {c['emo_ref']}：{audio_tag(orig(ck, c['emo_ref']))}" if c["emo_ref"] else "")
                     + f"</p><p><small>聲紋相似度刻度：原聲對原聲 {b.get('ceiling')}（上限），"
                       f"換成另一個角色 {b.get('floor')}（下限）。</small></p>")
        parts.append("<h3>一、同一句話：原聲 對 克隆</h3><table><tr><th>台詞</th><th>做法</th><th>原聲</th>"
                     "<th>IndexTTS-2</th><th>IndexTTS-2.5</th></tr>")
        for it in [x for x in items if x["char"] == ck and x["section"] == "same"]:
            parts.append(f"<tr><td>{html.escape(it['text'])}</td><td>{it['mode']}</td>"
                         f"<td>{audio_tag(orig(ck, it['orig']))}</td><td>{cell('v2', it)}</td><td>{cell('v25', it)}</td></tr>")
        parts.append("</table><h3>二、BB-ST-1 劇情台詞（沒有原聲可比）</h3><table><tr><th>台詞</th><th>做法</th>"
                     "<th>IndexTTS-2</th><th>IndexTTS-2.5</th></tr>")
        for it in [x for x in items if x["char"] == ck and x["section"] == "story"]:
            parts.append(f"<tr><td>{html.escape(it['text'])}</td><td>{it['mode']}</td>"
                         f"<td>{cell('v2', it)}</td><td>{cell('v25', it)}</td></tr>")
        parts.append("</table>")
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>幹員原聲克隆試聽</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px}}td,th{{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}}
audio{{width:230px;min-width:210px;vertical-align:middle}}small{{color:#555}}</style></head><body>
<h1>幹員原聲克隆試聽：IndexTTS-2 對 IndexTTS-2.5</h1>
<p>參考音是遊戲內幹員中文原聲；每個條件只合成一次（固定隨機種子 {SEED}），預設參數、未調校。
合成速度（每秒音訊耗時）：IndexTTS-2 {summ['v2']['mean_rtf']} 秒，IndexTTS-2.5 {summ['v25']['mean_rtf']} 秒。</p>
<p><small>平均值 {html.escape(json.dumps(agg, ensure_ascii=False))}</small></p>
{''.join(f'<p style="color:#b00">{html.escape(n)}</p>' for n in notes)}
{''.join(parts)}</body></html>"""
    open(f"{WORK}/report.html", "w", encoding="utf-8").write(page)
    print("REPORT_DONE", json.dumps(dict(baseline=metrics.get("baseline"), aggregate=agg, notes=notes),
                                    ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "gen":
        gen(sys.argv[2])
    else:
        report()
