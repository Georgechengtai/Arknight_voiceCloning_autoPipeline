"""回聽對齊：對一批已合成的音檔做語音辨識，把逐字時間對回原文。只辨識、不合成、不改音檔。

    python voice_align.py <job.json>
job.json：{"scene": 輸出目錄名, "items": [{"key", "wav"（相對於 job.json 的路徑）, "lines": [{"line_id", "text"}]}]}
輸出：與 job.json 同目錄的 align.json。每個 item 有兩套辨識結果（para＝FunASR paraformer-zh；whisper＝large-v3，
裝不起來就略過），各自帶：
  toks、ts（每個辨識單位的起訖毫秒）、cer（拼音字錯率）、
  lines[]：ref（原文拆成的單位）、hyp（各單位對到第幾個辨識單位，-1＝沒念或沒被認出）、ok（拼音是否相同）、
  ins[]：辨識結果裡多出來的單位（i＝第幾個辨識單位、line＝落在第幾句）。
比對一律比去聲調的拼音，同音字不算錯。Mac 端的 tools/voice_manifest.py 用這份結果找切點與列出疑似念錯的地方。
"""
import json
import os
import re
import sys

import numpy as np

TOKEN = re.compile(r"[一-鿿]|[A-Za-z0-9]+")


def tokens(text):
    return TOKEN.findall(text)


def py(tok):
    from pypinyin import lazy_pinyin
    return "".join(lazy_pinyin(tok)).lower()


def align(ref, hyp):
    """編輯距離回溯。回傳 (ref 每個單位對到的 hyp 位置或 -1, 多出來的 hyp 位置, 距離)。"""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0], d[0, :] = np.arange(n + 1), np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    pos, ins, i, j = [-1] * n, [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            pos[i - 1] = j - 1; i -= 1; j -= 1
        elif j > 0 and d[i, j] == d[i, j - 1] + 1:
            ins.append(j - 1); j -= 1
        else:
            i -= 1
    return pos, sorted(ins), int(d[n, m])


def compare(lines, toks, ts):
    ref_toks = [tokens(l["text"]) for l in lines]
    flat = [py(t) for ts_ in ref_toks for t in ts_]
    hyp = [py(t) for t in toks]
    pos, ins, dist = align(flat, hyp)
    out, k = [], 0
    owner = [None] * len(hyp)           # 每個辨識單位屬於第幾句（多出來的字歸給前一個對上的字所在的句）
    for n, rt in enumerate(ref_toks):
        p = pos[k:k + len(rt)]
        out.append(dict(line_id=lines[n]["line_id"], ref=rt, hyp=p, ok=[q >= 0 and flat[k + x] == hyp[q] for x, q in enumerate(p)]))
        for q in p:
            if q >= 0:
                owner[q] = n
        k += len(rt)
    last = 0
    for q in range(len(hyp)):
        if owner[q] is None:
            owner[q] = last
        last = owner[q]
    return dict(toks=toks, ts=ts, cer=round(dist / max(len(flat), 1), 3), lines=out,
                ins=[dict(i=q, tok=toks[q], line=owner[q]) for q in ins])


def run_para(asr, path):
    res = asr.generate(input=path)[0]
    toks, ts = res["text"].split(), res.get("timestamp") or []
    if len(ts) != len(toks):            # 沒有逐字時間（不該發生）：留文字，時間給空
        return [t for w in toks for t in tokens(w)], []
    out_t, out_ts = [], []
    for w, (a, b) in zip(toks, ts):
        parts = tokens(w) or []
        for x, t in enumerate(parts):   # 一個單位裡若有多個字，時間平均分
            out_t.append(t)
            out_ts.append([int(a + (b - a) * x / len(parts)), int(a + (b - a) * (x + 1) / len(parts))])
    return out_t, out_ts


def run_whisper(model, path):
    import soundfile as sf
    audio, sr = sf.read(path, dtype="float32")      # 叢集沒有 ffmpeg，自己讀檔（Mac 端已轉成 16 kHz 單聲道）
    assert sr == 16000 and audio.ndim == 1, path
    res = model.transcribe(audio, language="zh", word_timestamps=True, condition_on_previous_text=False,
                           initial_prompt="以下是普通话的句子。")
    out_t, out_ts = [], []
    for seg in res["segments"]:
        for w in seg.get("words", []):
            parts = tokens(w["word"])
            a, b = w["start"] * 1000, w["end"] * 1000
            for x, t in enumerate(parts):
                out_t.append(t)
                out_ts.append([int(a + (b - a) * x / len(parts)), int(a + (b - a) * (x + 1) / len(parts))])
    return out_t, out_ts


def main(job_path):
    import soundfile as sf
    from funasr import AutoModel

    base = os.path.dirname(os.path.abspath(job_path))
    job = json.load(open(job_path, encoding="utf-8"))
    asr = AutoModel(model="paraformer-zh", disable_update=True)
    asr_vad = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", disable_update=True)
    wh = None
    try:
        import whisper
        wh = whisper.load_model("large-v3", download_root=os.path.join(os.environ["AKTTS_ROOT"], "models", "whisper"))
    except Exception as e:               # 第二套辨識只是交叉比對用，沒有也能做
        print("WHISPER_UNAVAILABLE", repr(e), flush=True)
    items = []
    for it in job["items"]:
        path = os.path.join(base, it["wav"])
        row = dict(key=it["key"], dur=round(sf.info(path).duration, 3))
        for name, fn in (("para", lambda p: run_para(asr, p)), ("para_vad", lambda p: run_para(asr_vad, p)),
                         ("whisper", (lambda p: run_whisper(wh, p)) if wh else None)):
            if fn is None:
                continue
            try:
                toks, ts = fn(path)
                row[name] = compare(it["lines"], toks, ts)
            except Exception as e:
                row[name] = dict(error=repr(e))
        items.append(row)
        print(it["key"], row["dur"], {k: row[k].get("cer", "ERR") for k in ("para", "para_vad", "whisper") if k in row},
              "".join(row["para"].get("toks", [])), flush=True)
    json.dump(dict(scene=job["scene"], items=items), open(os.path.join(base, "align.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"VOICE_ALIGN_DONE {job['scene']} n={len(items)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
