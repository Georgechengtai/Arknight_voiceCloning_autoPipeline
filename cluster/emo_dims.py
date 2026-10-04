"""拆變因：第四輪 Q（手填情緒向量）為什麼不好。只用 IndexTTS-2，三句、每句六種向量。

用法（index-tts 倉庫目錄、aktts 環境）： python emo_dims.py gen ； python emo_dims.py report
情緒向量順序：[高興, 憤怒, 悲傷, 恐懼, 反感, 低落, 驚訝, 自然]
"""
import json
import os
import sys

ROOT = os.environ["AKTTS_ROOT"]
sys.path.insert(0, ROOT)
import round3  # noqa: E402
import round4  # noqa: E402

OUT = f"{ROOT}/work/emo_dims_kalts"
PICK = ["L05", "L06", "L12"]
VECS = [("只有低落 0.25", [0, 0, 0, 0, 0, 0.25, 0, 0]), ("只有悲傷 0.25", [0, 0, 0.25, 0, 0, 0, 0, 0]),
        ("只有恐懼 0.1", [0, 0, 0, 0.1, 0, 0, 0, 0]), ("只有自然 0.25", [0, 0, 0, 0, 0, 0, 0, 0.25]),
        ("悲傷 0.15＋恐懼 0.1（混兩種，不含低落）", [0, 0, 0.15, 0.1, 0, 0, 0, 0]),
        ("低落 0.15＋自然 0.1（混兩種，含低落）", [0, 0, 0, 0, 0, 0.15, 0, 0.1])]


def gen():
    import torch
    from indextts.infer_v2 import IndexTTS2
    md = f"{ROOT}/models/IndexTTS-2"
    tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
    rf = round3.refs()
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for lid, _, _, text in round3.LINES:
        if lid not in PICK:
            continue
        ref = round4.DIRECT[lid][0]
        for i, (label, vec) in enumerate(VECS):
            path = f"{OUT}/{lid}_{i}.wav"
            torch.manual_seed(1234)
            tts.infer(spk_audio_prompt=rf[ref]["path"], text=text, output_path=path, verbose=False, emo_vector=vec, use_random=False)
            rows.append(dict(line=lid, label=label, vec=vec, path=path))
            print(lid, label, flush=True)
    json.dump(rows, open(f"{OUT}/rows.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("EMO_DIMS_GEN_DONE", len(rows), flush=True)


def report():
    import html
    import round2
    rows = json.load(open(f"{OUT}/rows.json", encoding="utf-8"))
    text_of = {lid: t for lid, _, _, t in round3.LINES}
    body = ""
    for lid in PICK:
        ref, why, qvec, desc = round4.DIRECT[lid]
        body += (f"<h3>{lid} {html.escape(text_of[lid])}</h3><p><small>參考音 {ref}。第四輪的 Q 用的是 {qvec}。</small></p>"
                 "<table><tr><th>做法</th><th>播放</th><th>長度</th><th>語速</th></tr>")
        prev = [(f"第四輪 P（不加情緒）", f"{round4.R4}/v2/{lid}_P.wav"), (f"第四輪 R（描述「{desc}」強度 0.3）", f"{round4.R4}/v2/{lid}_R.wav"),
                (f"第四輪 Q（手填 {qvec}）", f"{round4.R4}/v2/{lid}_Q.wav")]
        for label, p in prev + [(f"{r['label']} {r['vec']}", r["path"]) for r in rows if r["line"] == lid]:
            m = round2.features(p, text_of[lid])
            body += f"<tr><td>{html.escape(label)}</td><td>{round3.mp3_tag(p)}</td><td>{m['dur']}</td><td>{m['rate']}</td></tr>"
        body += "</table>"
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>情緒維度拆解</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px;font-size:14px}}td,th{{border:1px solid #ccc;padding:6px;text-align:left}}
audio{{width:240px;min-width:200px}}small{{color:#555}}</style></head><body>
<h1>情緒維度拆解（IndexTTS-2，凯尔希）</h1>
<p>三句各用同一段參考音，只換情緒向量，看是哪個維度把聲音帶壞。前三列是第四輪原本的 P、R、Q。</p>{body}</body></html>"""
    open(f"{OUT}/report.html", "w", encoding="utf-8").write(page)
    print("EMO_DIMS_REPORT_DONE", flush=True)


if __name__ == "__main__":
    gen() if sys.argv[1] == "gen" else report()
