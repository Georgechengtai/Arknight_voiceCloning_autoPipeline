"""第三輪：凯尔希的平穩長句，IndexTTS-2 與 2.5 用完全相同的條件比較。

台詞取自巴別塔中她語氣平穩的場次（BB-1 行動後、BB-5 行動前、BB-ST-2、BB-6 行動後等），
涵蓋陳述、沉思、溫和、下令、詢問五類；每類的參考音由 refs.json 的量測與語音場合挑定。

    python round3.py idx v2|v25   # aktts 環境、index-tts 倉庫目錄
    python round3.py gsv          # aktts-gsv 環境、GPT-SoVITS 倉庫目錄（純 GPT-SoVITS 與混合方案）
    python round3.py report       # aktts 環境

每句的做法（兩個 IndexTTS 版本完全相同）：
  A 語氣對應的參考音直接當音色參考音（上一輪專案擁有者認為最好的做法）
  B 固定用 CN_011 當參考音、不控情緒（對照）
  C CN_011 ＋ 自然語言情緒描述（兩版都支援，強度 0.6）
另外：D 微調後的 GPT-SoVITS 用同一段參考音；E 把 IndexTTS-2 的 A 交給微調後的聲音模型換聲（混合方案）。
"""
import base64
import io
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
R3 = f"{ROOT}/work/round3_{KEY}"
SEED = 1234
CALM = "CN_011"
# 類別 → (參考音, 自然語言情緒描述)
CATS = {
    "陳述": ("CN_003_s1", "冷静、克制，条理清晰地分析局势"),
    "沉思": ("CN_043_s2", "低沉、缓慢，带着遥远的怀念与感伤"),
    "溫和": ("CN_038_s2", "温和而关切，放轻声音"),
    "下令": ("CN_031", "果断、简短、不容置疑地下达命令"),
    "詢問": ("CN_006_s1", "严肃而忧虑地发问"),
}
LINES = [
    ("L01", "陳述", "BB-5 行動前", "魔王在萨卡兹传统里的地位超乎想象，特蕾西娅的功绩也有目共睹。军事委员会反而不敢有过激的举动。"),
    ("L02", "陳述", "BB-5 行動前", "但维多利亚对卡兹戴尔发出的邀请并不是一个友善的信号，这意味着卡兹戴尔再次进入了泰拉诸国的视野。"),
    ("L03", "陳述", "BB-1 行動後", "但是萨尔贡和雷姆必拓的“关系人”进展都很顺利。哥伦比亚……也有一些科学家提出技术交换项目。"),
    ("L04", "陳述", "BB-7 行動前", "王庭。他们拥有执行暴力最直接的权力，孽茨雷更是被许诺了一场改变大地的战火才甘愿交出主导权。"),
    ("L05", "沉思", "BB-ST-2", "但我唯独记得，在那么远那么远的过去，有个人，将这个名字送给了我——"),
    ("L06", "沉思", "BB-6 行動後", "而与之对应的，另一个空虚而冰寒的想法，在这万年的岁月里，总是在半夜化作凉意，钻入我的脊髓。"),
    ("L07", "沉思", "BB-6 行動後", "是我决定将你唤醒，是我希望你能为这片文明……这片令我越发意外、越发惊喜，也越发无所适从的文明指明出路。"),
    ("L08", "溫和", "BB-4 行動後", "会痛，但我知道你是坚强的孩子，博士已经写信告诉我了。"),
    ("L09", "溫和", "BB-ST-2", "无论你的回答是什么，巴别塔会坚持到你归来的那天，博士。"),
    ("L10", "下令", "BB-8 行動後", "把所有情报传回给博士，行动小队加快速度，随时警惕。"),
    ("L11", "下令", "BB-4 行動後", "为了博士的安全，也为了巴别塔成员的安全，抹除他的登舰记录。"),
    ("L12", "詢問", "BB-1 行動後", "如果调和仇恨与偏见的希望反而成为新的导火索，殿下打算怎么办？"),
]


def refs():
    return {r["id"]: r for r in json.load(open(f"{REF}/refs.json", encoding="utf-8"))["refs"]}


def idx(ver):
    import torch
    md = f"{ROOT}/models/IndexTTS-2" if ver == "v2" else f"{ROOT}/models/IndexTTS-2.5"
    t0 = time.time()
    if ver == "v2":
        from indextts.infer_v2 import IndexTTS2
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
        extra = {}
    else:
        from indextts.infer_v2_5 import IndexTTS2
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_bf16=True, use_qwen_emo=True)
        extra = {"lang": "ZH"}
    rf = refs()
    name = "IndexTTS-2" if ver == "v2" else "IndexTTS-2.5"
    os.makedirs(f"{R3}/{ver}", exist_ok=True)
    rows = []
    for lid, cat, _, text in LINES:
        ref, emo_text = CATS[cat]
        for tag, spk, kw, cond in (
                ("A", ref, {}, f"A 語氣對應的參考音 {ref} 當音色參考音"),
                ("B", CALM, {}, f"B 參考音 {CALM}、不控情緒"),
                ("C", CALM, dict(use_emo_text=True, emo_text=emo_text, emo_alpha=0.6, use_random=False),
                 f"C 參考音 {CALM}＋情緒描述「{emo_text}」")):
            path = f"{R3}/{ver}/{lid}_{tag}.wav"
            torch.manual_seed(SEED)
            t1 = time.time()
            try:
                tts.infer(spk_audio_prompt=rf[spk]["path"], text=text, output_path=path, verbose=False, **extra, **kw)
                rows.append(dict(engine=name, line=lid, tag=f"{ver}_{tag}", cond=cond, ok=True, path=path,
                                 gen_s=round(time.time() - t1, 2)))
            except Exception as e:
                rows.append(dict(engine=name, line=lid, tag=f"{ver}_{tag}", cond=cond, ok=False, error=repr(e)[:300]))
            print({k: v for k, v in rows[-1].items() if k != "path"}, flush=True)
    json.dump(rows, open(f"{R3}/{ver}/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"IDX_DONE {ver} load={time.time() - t0:.0f}s ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


def gsv():
    import librosa
    import torch
    import gsv_pipeline as G
    os.environ.update(version=G.VERSION, gpt_path=G.S1, sovits_path=G.S2G, is_half="True")
    import GPT_SoVITS.inference_webui as W
    zh = W.i18n("中文")
    W.change_gpt_weights(gpt_path=G.latest(f"GPT_weights_{G.VERSION}/{G.EXP}-e*.ckpt", r"-e(\d+)\.ckpt"))
    for _ in W.change_sovits_weights(sovits_path=G.latest(f"SoVITS_weights_{G.VERSION}/{G.EXP}_e*_s*.pth", r"_e(\d+)_s"),
                                     prompt_language=zh, text_language=zh):
        pass
    rf = refs()
    aux_paths = [f"{REF}/audio/{v}.mp3" for v in G.AUX_REFS]
    aux = [SimpleNamespace(name=p) for p in aux_paths]
    os.makedirs(f"{R3}/gsv", exist_ok=True)
    rows = []
    for lid, cat, _, text in LINES:                              # D：純 GPT-SoVITS
        r = rf[CATS[cat][0]]
        path = f"{R3}/gsv/{lid}_D.wav"
        torch.manual_seed(SEED)
        try:
            out = list(W.get_tts_wav(ref_wav_path=r["path"], prompt_text=r["text"], prompt_language=zh, text=text,
                                     text_language=zh, how_to_cut=W.i18n("不切"), top_k=15, top_p=1, temperature=1, inp_refs=aux))
            sf.write(path, out[-1][1], out[-1][0])
            rows.append(dict(engine="GPT-SoVITS", line=lid, tag="gsv_D", ok=True, path=path,
                             cond=f"D 微調後 GPT-SoVITS，參考音 {r['id']}"))
        except Exception as e:
            rows.append(dict(engine="GPT-SoVITS", line=lid, tag="gsv_D", ok=False, error=repr(e)[:300], cond="D"))
        print({k: v for k, v in rows[-1].items() if k != "path"}, flush=True)
    if W.sv_cn_model is None:
        W.init_sv_cn()
    with torch.no_grad():                                        # E：混合方案，節奏取自 IndexTTS-2 的 A
        refers, sv = [], []
        for p in [rf[CALM]["path"]] + aux_paths:
            refer, audio = W.get_spepc(W.hps, p, W.dtype, W.device, True)
            refers.append(refer)
            sv.append(W.sv_cn_model.compute_embedding3(audio))
        for lid, cat, _, text in LINES:
            src, path = f"{R3}/v2/{lid}_A.wav", f"{R3}/gsv/{lid}_E.wav"
            try:
                wav, _ = librosa.load(src, sr=16000)
                wav = torch.from_numpy(wav).to(W.device)
                wav = wav.half() if W.is_half else wav
                ssl = W.ssl_model.model(wav.unsqueeze(0))["last_hidden_state"].transpose(1, 2)
                sem = W.vq_model.extract_latent(ssl)[0, 0].unsqueeze(0).unsqueeze(0)
                phones, _, _ = W.get_phones_and_bert(text, "all_zh", W.version)
                a = W.vq_model.decode(sem, torch.LongTensor(phones).to(W.device).unsqueeze(0), refers, speed=1,
                                      sv_emb=sv)[0][0].float().cpu().numpy()
                sf.write(path, a / max(1.0, float(np.abs(a).max())), 32000)
                rows.append(dict(engine="混合", line=lid, tag="hyb_E", ok=True, path=path,
                                 cond="E 混合：IndexTTS-2 的 A 換成微調模型的聲音"))
            except Exception as e:
                rows.append(dict(engine="混合", line=lid, tag="hyb_E", ok=False, error=repr(e)[:300], cond="E"))
            print({k: v for k, v in rows[-1].items() if k != "path"}, flush=True)
    json.dump(rows, open(f"{R3}/gsv/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"GSV_DONE ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


def mp3_tag(path):
    data, sr = sf.read(path)
    buf = io.BytesIO()
    try:
        sf.write(buf, data, sr, format="MP3")
        mime = "audio/mpeg"
    except Exception:
        buf = io.BytesIO()
        sf.write(buf, data, sr, format="FLAC")
        mime = "audio/flac"
    return f'<audio controls preload="none" src="data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"></audio>'


def report():
    import html
    import real_ab as R
    import round2
    from funasr import AutoModel
    rows = []
    for d in ("v2", "v25", "gsv"):
        p = f"{R3}/{d}/rows.json"
        if os.path.exists(p):
            rows += json.load(open(p, encoding="utf-8"))
    text_of = {lid: t for lid, _, _, t in LINES}
    sv = AutoModel(model="cam++", disable_update=True)
    asr = AutoModel(model="paraformer-zh", disable_update=True)

    def emb(p):
        e = sv.generate(input=R.to16k(p))[0]["spk_embedding"]
        e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
        return e / (np.linalg.norm(e) + 1e-9)

    cen = np.mean([emb(R.orig(KEY, v)) for v in R.CHARS[KEY]["pool"]], axis=0)
    cen /= np.linalg.norm(cen)
    for r in rows:
        if r["ok"]:
            t = text_of[r["line"]]
            r.update(round2.features(r["path"], t))
            r["sim"] = round(float(emb(r["path"]) @ cen), 3)
            r["asr"] = asr.generate(input=R.to16k(r["path"]))[0]["text"].replace(" ", "")
            r["cer"] = R.cer(t, r["asr"])
    agg = {}
    for r in rows:
        if r["ok"]:
            a = agg.setdefault(r["tag"], dict(n=0, sim=[], cer=[], rate=[], dur=[]))
            a["n"] += 1
            for k in ("sim", "cer", "rate", "dur"):
                a[k].append(r[k])
    agg = {k: dict(n=v["n"], sim=round(float(np.mean(v["sim"])), 3), cer=round(float(np.mean(v["cer"])), 3),
                   rate=round(float(np.mean(v["rate"])), 2), dur_total=round(float(np.sum(v["dur"])), 1)) for k, v in agg.items()}
    json.dump(dict(aggregate=agg, cats=CATS, rows=[{k: v for k, v in r.items() if k != "path"} for r in rows]),
              open(f"{R3}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    esc = html.escape
    rf = refs()
    ref_rows = "".join(f"<tr><td>{c}</td><td>{rid}</td><td>{esc(rf[rid]['text'])}</td><td>{mp3_tag(rf[rid]['path'])}</td>"
                       f"<td>{esc(desc)}</td></tr>" for c, (rid, desc) in CATS.items())
    ref_rows += f"<tr><td>對照</td><td>{CALM}</td><td>{esc(rf[CALM]['text'])}</td><td>{mp3_tag(rf[CALM]['path'])}</td><td>—</td></tr>"
    agg_rows = "".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v['sim']}</td><td>{v['cer']}</td><td>{v['rate']}</td></tr>"
                       for k, v in sorted(agg.items()))
    body = ""
    for lid, cat, scene, text in LINES:
        body += (f"<h3>{lid}［{cat}｜{scene}］{esc(text)}</h3><table><tr><th>引擎</th><th>做法</th><th>播放</th>"
                 "<th>長度</th><th>語速</th><th>相似度</th><th>字錯率</th><th>辨識</th></tr>")
        for r in sorted([x for x in rows if x["line"] == lid], key=lambda x: x["tag"]):
            if r["ok"]:
                body += (f"<tr><td>{r['engine']}</td><td>{esc(r['cond'])}</td><td>{mp3_tag(r['path'])}</td><td>{r['dur']}</td>"
                         f"<td>{r['rate']}</td><td>{r['sim']}</td><td>{r['cer']}</td><td><small>{esc(r['asr'])}</small></td></tr>")
            else:
                body += f"<tr><td>{r['engine']}</td><td>{esc(r['cond'])}</td><td colspan=6><i>失敗：{esc(r['error'][:140])}</i></td></tr>"
        body += "</table>"
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希 第三輪：平穩長句</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:220px;min-width:200px}}small{{color:#555}}h3{{font-size:15px;margin-top:22px}}</style></head><body>
<h1>凯尔希 第三輪：平穩長句，IndexTTS-2 與 2.5 同條件</h1>
<p>12 句取自她語氣平穩的場次。每個條件只合成一次，固定隨機種子 {SEED}。語速單位字/秒（她原聲的中位數 5.96）；
相似度是聲紋相似度（上限 0.894）；字錯率會被專有名詞的同音字灌水。這些台詞沒有原聲可比。</p>
<h2>各類別用的參考音與情緒描述</h2>
<table><tr><th>類別</th><th>參考音</th><th>文字</th><th>播放</th><th>C 做法的情緒描述</th></tr>{ref_rows}</table>
<h2>各做法 12 句的平均</h2>
<table><tr><th>做法</th><th>成功句數</th><th>相似度</th><th>字錯率</th><th>語速</th></tr>{agg_rows}</table>
<h2>逐句</h2>{body}</body></html>"""
    open(f"{R3}/report.html", "w", encoding="utf-8").write(page)
    print("ROUND3_REPORT_DONE", json.dumps(agg, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "idx":
        idx(sys.argv[2])
    else:
        {"gsv": gsv, "report": report}[sys.argv[1]]()
