"""GPT-SoVITS 微調試驗的試聽頁：原聲 / IndexTTS-2（上一輪）/ GPT-SoVITS 未微調 / 微調後。

在 aktts 環境下執行（需要 funasr）： python gsv_report.py
沿用 real_ab.py 的工具函式與上一輪 IndexTTS-2 的輸出、指標。
"""
import html
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.environ["AKTTS_ROOT"])
import real_ab as R  # noqa: E402

CK = "kalts"
GW = f"{R.ROOT}/work/gsv_{CK}"
res = json.load(open(f"{GW}/gen/results.json", encoding="utf-8"))
meta = json.load(open(f"{GW}/meta.json", encoding="utf-8"))
prev = json.load(open(f"{R.WORK}/results.json", encoding="utf-8"))  # 上一輪 IndexTTS 的指標
rows = {(r["tag"], r["id"]): r for r in res["rows"]}
gpath = lambda tag, i: f"{GW}/gen/{tag}/{i}.wav"
notes, M = [], {}

try:
    from funasr import AutoModel
    sv = AutoModel(model="cam++", disable_update=True)

    def emb(p):
        e = sv.generate(input=R.to16k(p))[0]["spk_embedding"]
        e = np.asarray(e.detach().cpu() if hasattr(e, "detach") else e, dtype=np.float32).reshape(-1)
        return e / (np.linalg.norm(e) + 1e-9)

    cen = np.mean([emb(R.orig(CK, v)) for v in R.CHARS[CK]["pool"]], axis=0)
    cen /= np.linalg.norm(cen)
    for (tag, i), r in rows.items():
        if r["ok"]:
            M.setdefault((tag, i), {})["sim"] = round(float(emb(gpath(tag, i)) @ cen), 3)
except Exception as e:
    notes.append(f"聲紋相似度計算失敗：{e!r}")

try:
    from funasr import AutoModel
    asr = AutoModel(model="paraformer-zh", disable_update=True)
    for (tag, i), r in rows.items():
        if r["ok"]:
            hyp = asr.generate(input=R.to16k(gpath(tag, i)))[0]["text"]
            M.setdefault((tag, i), {}).update(asr=hyp, cer=R.cer(r["text"], hyp))
except Exception as e:
    notes.append(f"字錯率計算失敗：{e!r}")


def cell(tag, i):
    r = rows.get((tag, i))
    if r is None:
        return "<i>（未做）</i>"
    if not r["ok"]:
        return f"<i>合成失敗：{html.escape(r['error'][:120])}</i>"
    m = M.get((tag, i), {})
    info = "　".join(x for x in (f"相似度 {m['sim']}" if "sim" in m else "", f"字錯率 {m['cer']}" if "cer" in m else "",
                                 f"參考音 {r['ref']}") if x)
    asr_line = f"<br><small>辨識：{html.escape(m['asr'])}</small>" if m.get("asr") else ""
    return f"{R.audio_tag(gpath(tag, i))}<br><small>{info}</small>{asr_line}"


def prev_cell(pid):
    m = prev["metrics"].get("v2", {}).get(pid, {})
    info = "　".join(x for x in (f"相似度 {m['sim']}" if "sim" in m else "", f"字錯率 {m['cer']}" if "cer" in m else "") if x)
    return f"{R.audio_tag(f'{R.WORK}/gen/v2/{pid}.wav')}<br><small>{info}</small>"


lines = [(f"same_{vid}", text, vid, f"{CK}_same_{vid}_refA") for vid, text in R.CHARS[CK]["holdout"]]
lines += [(f"story{i}", s[0], None, f"{CK}_story{i}_none") for i, s in enumerate(R.CHARS[CK]["story"], 1)]
body = []
for key, text, orig_vid, prev_id in lines:
    is_same = orig_vid is not None
    body.append(
        f"<tr><td>{html.escape(text)}</td><td>{R.audio_tag(R.orig(CK, orig_vid)) if is_same else '<i>（無原聲）</i>'}</td>"
        f"<td>{prev_cell(prev_id)}</td><td>{cell('base', key if is_same else key + '_calm')}</td>"
        f"<td>{cell('ft', key if is_same else key + '_calm')}</td>"
        f"<td>{'<i>（同左）</i>' if is_same else cell('ft', key + '_emo')}</td></tr>")


def mean(tag, pred):
    xs = [M[k]["sim"] for k in M if k[0] == tag and pred(k[1]) and "sim" in M[k]]
    return round(float(np.mean(xs)), 3) if xs else None


agg = dict(base_same=mean("base", lambda i: i.startswith("same")), base_story=mean("base", lambda i: i.endswith("_calm")),
           ft_same=mean("ft", lambda i: i.startswith("same")), ft_story_calm=mean("ft", lambda i: i.endswith("_calm")),
           ft_story_emo=mean("ft", lambda i: i.endswith("_emo")),
           indextts2_same=prev["aggregate"]["v2"][CK]["sim_same"], indextts2_story=prev["aggregate"]["v2"][CK]["sim_story"],
           baseline=prev["metrics"].get("baseline", {}).get(CK))
json.dump(dict(aggregate=agg, metrics={f"{t}/{i}": m for (t, i), m in M.items()}, notes=notes,
               train=dict(n_lines=meta["n_train"], minutes=meta["train_minutes"]), infer=res),
          open(f"{GW}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

emo = res["emo_ref"]
page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希：整池原聲微調試聽</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px}}td,th{{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}}
audio{{width:220px;min-width:200px;vertical-align:middle}}small{{color:#555}}</style></head><body>
<h1>凯尔希：用整池原聲微調 GPT-SoVITS</h1>
<p>訓練資料：{meta['n_train']} 句中文原聲、共 {meta['train_minutes']} 分鐘（「同一句話」對比用的 {'、'.join(meta['holdout'])} 沒有放進訓練）。
官方預設參數（SoVITS 8 輪、GPT 15 輪），未調校；每個條件只合成一次。</p>
<p>平穩參考音 {res['calm_ref']}：{R.audio_tag(R.orig(CK, res['calm_ref']))}<br>
情緒相近參考音（依台詞內容挑的，未經人聽確認）——急促：{emo['urgent']}「{html.escape(res['emo_ref_text']['urgent'])}」
{R.audio_tag(f"{GW}/data/{emo['urgent']}.mp3")}　低沉：{emo['soft']}「{html.escape(res['emo_ref_text']['soft'])}」
{R.audio_tag(f"{GW}/data/{emo['soft']}.mp3")}</p>
<p><small>聲紋相似度刻度：原聲對原聲 {(agg['baseline'] or {}).get('ceiling')}（上限），換成另一個角色 {(agg['baseline'] or {}).get('floor')}（下限）。
平均值 {html.escape(json.dumps({k: v for k, v in agg.items() if k != 'baseline'}, ensure_ascii=False))}</small></p>
{''.join(f'<p style="color:#b00">{html.escape(n)}</p>' for n in notes)}
<table><tr><th>台詞</th><th>原聲</th><th>IndexTTS-2（上一輪，單一參考音）</th><th>GPT-SoVITS 未微調</th>
<th>GPT-SoVITS 微調後（平穩參考音）</th><th>GPT-SoVITS 微調後（情緒相近參考音）</th></tr>{''.join(body)}</table></body></html>"""
open(f"{GW}/report.html", "w", encoding="utf-8").write(page)
print("GSV_REPORT_DONE", json.dumps(dict(aggregate=agg, notes=notes), ensure_ascii=False), flush=True)
