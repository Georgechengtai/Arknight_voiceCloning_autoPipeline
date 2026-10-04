"""第四輪：同樣 12 句長句，參考音改為逐句依上下文挑選，情緒只疊很輕的一層。

專案擁有者聽完第三輪的結論：GPT-SoVITS 與混合方案棒讀感太強，不再使用；參考音不合語境就棒讀；
情緒描述理解得對但用力過猛（強度 0.6），2.5 尤其敏感；固定用 CN_011 的適用情境有限。

    python round4.py idx v2|v25   # aktts 環境、index-tts 倉庫目錄
    python round4.py report       # aktts 環境

每句三種做法（兩版相同）：
  P 逐句挑的參考音當音色參考音，不加情緒
  Q 同一參考音＋直接指定的情緒向量（總量 ≤ 0.4）
  R 同一參考音＋文字情緒描述，強度 0.3
頁面另附第三輪的 B（CN_011、不控情緒）當對照，不重新合成。
情緒向量順序：[高興, 憤怒, 悲傷, 恐懼, 反感, 低落, 驚訝, 自然]
"""
import json
import os
import sys
import time

import numpy as np

ROOT = os.environ["AKTTS_ROOT"]
sys.path.insert(0, ROOT)
import round3  # noqa: E402

R3, R4, SEED = round3.R3, f"{ROOT}/work/round4_kalts", 1234
# 台詞代號 → (參考音, 為什麼挑它（上下文）, 情緒向量, 文字描述)
DIRECT = {
    "L01": ("CN_003_s1", "向擔心殿下安危的博士分析局勢，語氣是平鋪直敘的說明；參考音同為說明性陳述",
            [0, 0, 0, 0, 0, 0, 0, 0.3], "平静地说明"),
    "L02": ("CN_004_s1", "話鋒一轉指出隱憂；參考音是她提醒博士「必须警惕」的告誡語氣",
            [0, 0, 0, 0.1, 0, 0.1, 0, 0.2], "平静中带着一点担忧"),
    "L03": ("CN_003_s1", "向殿下匯報進展，中途「哥伦比亚……」稍有遲疑；參考音為說明性陳述",
            [0, 0, 0, 0, 0, 0, 0, 0.3], "平静地汇报"),
    "L04": ("CN_004_s1", "評估王庭的威脅，語氣凝重；參考音為告誡語氣",
            [0, 0, 0, 0, 0, 0.15, 0, 0.2], "凝重"),
    "L05": ("CN_008_s3", "回憶送她名字的人，輕而懷念；參考音同樣是在轉述故人說過的話",
            [0, 0, 0.1, 0, 0, 0.25, 0, 0], "怀念，略带伤感"),
    "L06": ("CN_001_s3", "說出萬年來揮之不去的寒意；參考音是她音高最低的一段（153 Hz）",
            [0, 0, 0, 0.1, 0, 0.25, 0, 0], "低落，带着隐隐的恐惧"),
    "L07": ("CN_007_s1", "對透支自己的博士剖白，懇切而憂心；參考音是她對博士說「不用太担心我的事情」",
            [0, 0, 0.15, 0, 0, 0.05, 0, 0.15], "恳切，带着担忧"),
    "L08": ("CN_005_s2", "蹲下來對年幼的阿米娅說話，溫和安撫；參考音是她談到孩子的那段",
            [0.05, 0, 0, 0, 0, 0, 0, 0.3], "温和地安慰"),
    "L09": ("CN_009_s3", "博士不肯輕易許諾，她回以「我們等你」，平穩而堅定的承諾；參考音同樣是承諾（「我会站在这里，直到最后」）",
            [0, 0, 0, 0, 0, 0, 0, 0.3], "平静而坚定"),
    "L10": ("CN_029", "行動中對小隊下令，乾脆俐落；參考音是任務結束後的指示語氣",
            [0, 0, 0, 0, 0, 0, 0, 0.2], "平静干脆"),
    "L11": ("CN_004_s2", "低聲要可露希尔抹除記錄，不容商量但不嚴厲；參考音是她給建議時的堅定語氣",
            [0, 0, 0, 0, 0, 0, 0, 0.3], "平静而坚决"),
    "L12": ("CN_006_s1", "把憂慮攤開後向殿下發問；參考音同樣是沉重的發問（「你会质疑自己存在的意义吗」）",
            [0, 0, 0, 0.1, 0, 0.15, 0, 0.1], "忧虑地发问"),
}


def idx(ver):
    import torch
    md = f"{ROOT}/models/IndexTTS-2" if ver == "v2" else f"{ROOT}/models/IndexTTS-2.5"
    if ver == "v2":
        from indextts.infer_v2 import IndexTTS2
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
        extra = {}
    else:
        from indextts.infer_v2_5 import IndexTTS2
        tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_bf16=True, use_qwen_emo=True)
        extra = {"lang": "ZH"}
    rf = round3.refs()
    name = "IndexTTS-2" if ver == "v2" else "IndexTTS-2.5"
    os.makedirs(f"{R4}/{ver}", exist_ok=True)
    rows = []
    for lid, _, _, text in round3.LINES:
        ref, _, vec, desc = DIRECT[lid]
        for tag, kw, cond in (
                ("P", {}, f"P 參考音 {ref}，不加情緒"),
                ("Q", dict(emo_vector=vec, use_random=False), f"Q 參考音 {ref}＋情緒向量 {vec}"),
                ("R", dict(use_emo_text=True, emo_text=desc, emo_alpha=0.3, use_random=False),
                 f"R 參考音 {ref}＋描述「{desc}」強度 0.3")):
            path = f"{R4}/{ver}/{lid}_{tag}.wav"
            torch.manual_seed(SEED)
            try:
                tts.infer(spk_audio_prompt=rf[ref]["path"], text=text, output_path=path, verbose=False, **extra, **kw)
                rows.append(dict(engine=name, line=lid, tag=f"{ver}_{tag}", cond=cond, ok=True, path=path))
            except Exception as e:
                rows.append(dict(engine=name, line=lid, tag=f"{ver}_{tag}", cond=cond, ok=False, error=repr(e)[:300]))
            print({k: v for k, v in rows[-1].items() if k != "path"}, flush=True)
    json.dump(rows, open(f"{R4}/{ver}/rows.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"IDX_DONE {ver} ok={sum(r['ok'] for r in rows)} fail={sum(not r['ok'] for r in rows)}", flush=True)


def report():
    import html
    import real_ab as R
    import round2
    from funasr import AutoModel
    rows = []
    for ver in ("v2", "v25"):
        rows += json.load(open(f"{R4}/{ver}/rows.json", encoding="utf-8"))
        for r in json.load(open(f"{R3}/{ver}/rows.json", encoding="utf-8")):   # 第三輪的 B 當對照
            if r["ok"] and r["tag"].endswith("_B"):
                rows.append(dict(r, tag=r["tag"].replace("_B", "_0B"), cond="（第三輪）參考音 CN_011、不控情緒"))
    text_of = {lid: t for lid, _, _, t in round3.LINES}
    sv = AutoModel(model="cam++", disable_update=True)
    asr = AutoModel(model="paraformer-zh", disable_update=True)

    def emb(p):
        e = sv.generate(input=R.to16k(p))[0]["spk_embedding"]
        e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
        return e / (np.linalg.norm(e) + 1e-9)

    cen = np.mean([emb(R.orig("kalts", v)) for v in R.CHARS["kalts"]["pool"]], axis=0)
    cen /= np.linalg.norm(cen)
    for r in rows:
        if r["ok"]:
            t = text_of[r["line"]]
            r.update(round2.features(r["path"], t))
            r["sim"] = round(float(emb(r["path"]) @ cen), 3)
            r["asr"] = asr.generate(input=R.to16k(r["path"]))[0]["text"].replace(" ", "")
            r["cer"] = R.cer(t, r["asr"])
            r["extra_chars"] = len(round2.re.sub(r"[^一-鿿]", "", r["asr"])) - len(round2.re.sub(r"[^一-鿿]", "", t))
    agg = {}
    for r in rows:
        if r["ok"]:
            a = agg.setdefault(r["tag"], dict(sim=[], cer=[], rate=[]))
            for k in a:
                a[k].append(r[k])
    agg = {k: dict(n=len(v["sim"]), sim=round(float(np.mean(v["sim"])), 3), cer=round(float(np.mean(v["cer"])), 3),
                   rate=round(float(np.mean(v["rate"])), 2)) for k, v in agg.items()}
    json.dump(dict(aggregate=agg, direct=DIRECT, rows=[{k: v for k, v in r.items() if k != "path"} for r in rows]),
              open(f"{R4}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    esc = html.escape
    rf = round3.refs()
    body = ""
    for lid, cat, scene, text in round3.LINES:
        ref, why, _, _ = DIRECT[lid]
        body += (f"<h3>{lid}［{scene}］{esc(text)}</h3><p><small>上下文與選擇理由：{esc(why)}</small><br>"
                 f"參考音 {ref}「{esc(rf[ref]['text'])}」 {round3.mp3_tag(rf[ref]['path'])}</p>"
                 "<table><tr><th>引擎</th><th>做法</th><th>播放</th><th>長度</th><th>語速</th><th>相似度</th><th>字錯率</th><th>辨識</th></tr>")
        for r in sorted([x for x in rows if x["line"] == lid], key=lambda x: x["tag"]):
            if r["ok"]:
                flag = f"（多 {r['extra_chars']} 字）" if r["extra_chars"] > 0 else (f"（少 {-r['extra_chars']} 字）" if r["extra_chars"] < 0 else "")
                body += (f"<tr><td>{r['engine']}</td><td>{esc(r['cond'])}</td><td>{round3.mp3_tag(r['path'])}</td><td>{r['dur']}</td>"
                         f"<td>{r['rate']}</td><td>{r['sim']}</td><td>{r['cer']}</td><td><small>{esc(r['asr'])}{flag}</small></td></tr>")
            else:
                body += f"<tr><td>{r['engine']}</td><td>{esc(r['cond'])}</td><td colspan=6><i>失敗：{esc(r['error'][:140])}</i></td></tr>"
        body += "</table>"
    agg_rows = "".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v['sim']}</td><td>{v['cer']}</td><td>{v['rate']}</td></tr>"
                       for k, v in sorted(agg.items()))
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希 第四輪：逐句挑參考音</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top;text-align:left}}
audio{{width:220px;min-width:200px;vertical-align:middle}}small{{color:#555}}h3{{font-size:15px;margin-top:24px}}</style></head><body>
<h1>凯尔希 第四輪：參考音逐句依上下文挑選，情緒只疊很輕的一層</h1>
<p>同第三輪的 12 句。每句上方寫了我讀到的上下文與挑這段參考音的理由，請一併檢查理由對不對。
P 只用參考音；Q 再加我直接指定的情緒向量（總量 ≤ 0.4）；R 再加文字描述（強度 0.3，第三輪是 0.6）。
每個條件只合成一次，固定隨機種子 {SEED}。</p>
<h2>各做法 12 句的平均</h2>
<table><tr><th>做法</th><th>句數</th><th>相似度</th><th>字錯率</th><th>語速</th></tr>{agg_rows}</table>
<h2>逐句</h2>{body}</body></html>"""
    open(f"{R4}/report.html", "w", encoding="utf-8").write(page)
    print("ROUND4_REPORT_DONE", json.dumps(agg, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    idx(sys.argv[2]) if sys.argv[1] == "idx" else report()
