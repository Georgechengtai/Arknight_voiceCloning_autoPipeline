"""混合方案試驗：IndexTTS 決定「怎麼說」，微調後的 SoVITS 決定「誰在說」。

GPT-SoVITS 分兩段：前段（GPT）由文字預測一串「語義碼」，語速、停頓、節奏都在這串碼裡；
後段（SoVITS）把語義碼配上參考音變成角色的聲音。這裡不用前段，改從 IndexTTS 已合成的
音頻直接抽出語義碼，交給用角色整池原聲微調過的後段重新發聲。

    python hybrid.py convert   # aktts-gsv 環境、GPT-SoVITS 倉庫目錄
    python hybrid.py report    # aktts 環境

另外把兩句原聲也照同樣流程走一遍（原聲 → 語義碼 → 後段），當作後段本身音質的上限參考。
"""
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

ROOT = os.environ["AKTTS_ROOT"]
sys.path.insert(0, ROOT)
KEY = "kalts"
REF = f"{ROOT}/work/refs/{KEY}"
RAB = f"{ROOT}/work/real_ab"
R2 = f"{ROOT}/work/round2_{KEY}"
OUT = f"{ROOT}/work/hybrid_{KEY}"
TIMBRE_REFS = ["CN_011", "CN_003", "CN_005", "CN_007", "CN_008", "CN_009"]   # 與追加測試四相同
SAME = [("same_CN_036", "CN_036", "你似乎更加适应自己的工作和职责了，更像一个领导者了。"),
        ("same_CN_002", "CN_002", "我会定期为你进行理学检查，记录你的生命征象与意识状态，其他人没有这个权限。"
                                  "任何人想对你进行进一步的检查，你都有权拒绝，明白吗？")]
STORY = [("story1", "Monster，切开门！", "urgentA"), ("story2", "阿米娅！博士！", "urgentA"), ("story3", "特蕾西娅……", "sad1"),
         ("story4", "我明知道这样的可能性始终存在……为什么……", "sad1"), ("story5", "我应该留下，是我……", "sad1")]


def sources():
    """(台詞代號, 文字, 來源說明, 來源音檔, 輸出代號)"""
    out = []
    for line, vid, text in SAME:
        out.append((line, text, "原聲", f"{REF}/audio/{vid}.mp3", f"{line}_orig"))
        out.append((line, text, "IndexTTS-2，參考音 CN_011", f"{RAB}/gen/v2/{KEY}_{line}_refA.wav", f"{line}_idx2"))
        out.append((line, text, "IndexTTS-2.5，參考音 CN_011", f"{RAB}/gen/v25/{KEY}_{line}_refA.wav", f"{line}_idx25"))
    for line, text, emo in STORY:
        out.append((line, text, "IndexTTS-2，參考音 CN_011、不控情緒", f"{RAB}/gen/v2/{KEY}_{line}_none.wav", f"{line}_idx2"))
        out.append((line, text, "IndexTTS-2.5，參考音 CN_011、不控情緒", f"{RAB}/gen/v25/{KEY}_{line}_none.wav", f"{line}_idx25"))
        out.append((line, text, f"IndexTTS-2，{emo} 當音色參考音", f"{R2}/idx/{line}_spk_{emo}.wav", f"{line}_idx2_spk"))
        out.append((line, text, f"IndexTTS-2，CN_011＋{emo} 當情緒參考音", f"{R2}/idx/{line}_emo_{emo}.wav", f"{line}_idx2_emo"))
    return out


def convert():
    import librosa
    import torch
    import gsv_pipeline as G
    os.environ.update(version=G.VERSION, gpt_path=G.S1, sovits_path=G.S2G, is_half="True")
    import GPT_SoVITS.inference_webui as W
    zh = W.i18n("中文")
    for _ in W.change_sovits_weights(sovits_path=G.latest(f"SoVITS_weights_{G.VERSION}/{G.EXP}_e*_s*.pth", r"_e(\d+)_s"),
                                     prompt_language=zh, text_language=zh):
        pass
    if W.sv_cn_model is None:
        W.init_sv_cn()
    os.makedirs(OUT, exist_ok=True)
    rows = []
    with torch.no_grad():
        refers, sv = [], []
        for v in TIMBRE_REFS:                                   # 音色來源：角色原聲
            refer, audio = W.get_spepc(W.hps, f"{REF}/audio/{v}.mp3", W.dtype, W.device, True)
            refers.append(refer)
            sv.append(W.sv_cn_model.compute_embedding3(audio))
        for line, text, label, src, tag in sources():
            path = f"{OUT}/{tag}.wav"
            try:
                wav, _ = librosa.load(src, sr=16000)            # 節奏來源：IndexTTS 的輸出（或原聲）
                wav = torch.from_numpy(wav).to(W.device)
                wav = wav.half() if W.is_half else wav
                ssl = W.ssl_model.model(wav.unsqueeze(0))["last_hidden_state"].transpose(1, 2)
                sem = W.vq_model.extract_latent(ssl)[0, 0].unsqueeze(0).unsqueeze(0)
                lang = "zh" if re.search(r"[A-Za-z]", text) else "all_zh"
                phones, _, _ = W.get_phones_and_bert(text, lang, W.version)
                audio = W.vq_model.decode(sem, torch.LongTensor(phones).to(W.device).unsqueeze(0), refers,
                                          speed=1, sv_emb=sv)[0][0]
                a = audio.float().cpu().numpy()
                sf.write(path, a / max(1.0, float(np.abs(a).max())), 32000)
                rows.append(dict(line=line, text=text, source=label, src=src, tag=tag, ok=True, path=path))
            except Exception as e:
                rows.append(dict(line=line, text=text, source=label, src=src, tag=tag, ok=False, error=repr(e)[:300]))
            print({k: v for k, v in rows[-1].items() if k not in ("text", "src")}, flush=True)
    json.dump(rows, open(f"{OUT}/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"HYBRID_DONE ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


def report():
    import html
    import real_ab as R
    import round2
    from funasr import AutoModel
    rows = json.load(open(f"{OUT}/rows.json", encoding="utf-8"))
    sv = AutoModel(model="cam++", disable_update=True)
    asr = AutoModel(model="paraformer-zh", disable_update=True)

    def emb(p):
        e = sv.generate(input=R.to16k(p))[0]["spk_embedding"]
        e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
        return e / (np.linalg.norm(e) + 1e-9)

    cen = np.mean([emb(R.orig(KEY, v)) for v in R.CHARS[KEY]["pool"]], axis=0)
    cen /= np.linalg.norm(cen)

    def measure(p, text):
        m = round2.features(p, text)
        m["sim"] = round(float(emb(p) @ cen), 3)
        m["asr"] = asr.generate(input=R.to16k(p))[0]["text"].replace(" ", "")
        return m

    for r in rows:
        r["m_src"] = measure(r["src"], r["text"]) if os.path.exists(r["src"]) else None
        r["m_out"] = measure(r["path"], r["text"]) if r["ok"] else None
    prev = {}                                                   # 追加測試四的 GPT-SoVITS 純合成，當對照
    for line, _, _ in SAME:
        prev[line] = f"{ROOT}/work/gsv_{KEY}/gen/ft/{line}.wav"
    for line, _, _ in STORY:
        prev[line] = f"{ROOT}/work/gsv_{KEY}/gen/ft/{line}_calm.wav"
    texts = {r["line"]: r["text"] for r in rows}
    prev_m = {line: measure(p, texts[line]) for line, p in prev.items() if os.path.exists(p)}
    json.dump(dict(rows=[{k: v for k, v in r.items() if k not in ("path", "src")} for r in rows], gsv_only=prev_m),
              open(f"{OUT}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    esc = html.escape
    cell = lambda p, m: (f"{R.audio_tag(p)}<br><small>語速 {m['rate']}　相似度 {m['sim']}<br>辨識：{esc(m['asr'])}</small>"
                         if m else "<i>（無）</i>")
    body = ""
    for line in dict.fromkeys(r["line"] for r in rows):
        body += (f"<h3>{esc(texts[line])}</h3><p>GPT-SoVITS 純合成（追加測試四，對照）：{cell(prev.get(line), prev_m.get(line))}</p>"
                 "<table><tr><th>節奏來源</th><th>來源原樣</th><th>混合後（節奏照來源，聲音換成微調模型）</th></tr>")
        for r in [x for x in rows if x["line"] == line]:
            out = cell(r["path"], r["m_out"]) if r["ok"] else f"<i>失敗：{esc(r['error'][:120])}</i>"
            body += f"<tr><td>{esc(r['source'])}</td><td>{cell(r['src'], r['m_src'])}</td><td>{out}</td></tr>"
        body += "</table>"
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希 混合方案試聽</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:230px;min-width:200px}}small{{color:#555}}</style></head><body>
<h1>凯尔希 混合方案：IndexTTS 的節奏＋微調模型的聲音</h1>
<p>每列左邊是節奏來源（IndexTTS 的輸出，或原聲），右邊是把它的節奏交給微調後的聲音模型重新發聲的結果。
「原聲」那一列是把她本人的錄音走同樣流程，用來看這個流程本身會損失多少音質。
語速單位字/秒；相似度是聲紋相似度（上限 0.894、下限 0.490）。</p>{body}</body></html>"""
    open(f"{OUT}/report.html", "w", encoding="utf-8").write(page)
    print("HYBRID_REPORT_DONE", flush=True)


if __name__ == "__main__":
    {"convert": convert, "report": report}[sys.argv[1]]()
