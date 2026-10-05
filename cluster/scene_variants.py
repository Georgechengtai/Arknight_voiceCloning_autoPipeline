"""整場合成的對照實驗：同一批台詞用不同做法各合成一次（換參考音、拿掉情緒描述、幾句併成一段再切開）。

    cd $AKTTS_ROOT/index-tts && python ../scene_variants.py <job.json>
job.json：{"scene": 輸出目錄名, "items": [{"tag", "char", "ref" 或 "ref_path", "emo_text"（null＝不加情緒描述）,
          "emo_alpha"（預設 0.3）, "seed"（預設 1234）, "tail"（墊在最後、合成後丟掉的一句）, "lines": [{"line_id", "text"}, ...]}]}
一個 item 有多句時，整段一次合成，再用語音辨識的逐字時間對回原文，在句與句之間最安靜的地方切開。
tail 的用途：模型常在最後一個字還沒收完音就停止輸出（句尾是「……」時尤其明顯），聽起來像話沒說完。
在後面墊一句再切掉，真正的最後一句就能完整收尾。
輸出：work/scenes/<scene>/wav/<line_id>_<tag>.wav、qc.json
"""
import json
import os
import sys

import numpy as np

ROOT = os.environ["AKTTS_ROOT"]
sys.path.insert(0, ROOT)
from scene_tts import cer, units  # noqa: E402


def align(ref, hyp):
    """編輯距離回溯：回傳 ref 每個單位對到 hyp 的哪個位置（刪除的對到前一個）。"""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0], d[0, :] = np.arange(n + 1), np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    pos, i, j = [0] * n, n, m
    while i > 0:
        if j > 0 and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            pos[i - 1] = j - 1; i -= 1; j -= 1
        elif j > 0 and d[i, j] == d[i, j - 1] + 1:
            j -= 1
        else:
            pos[i - 1] = max(j - 1, 0); i -= 1
    return pos


def main(job_path):
    import soundfile as sf
    import torch
    from funasr import AutoModel
    from indextts.infer_v2 import IndexTTS2

    job = json.load(open(job_path, encoding="utf-8"))
    out = f"{ROOT}/work/scenes/{job['scene']}"
    os.makedirs(f"{out}/wav", exist_ok=True)
    md = f"{ROOT}/models/IndexTTS-2"
    tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
    asr = AutoModel(model="paraformer-zh", disable_update=True)
    refs, qc = {}, []
    for it in job["items"]:
        if it.get("ref_path"):
            ref_path = it["ref_path"].replace("$ROOT", ROOT)
        else:
            if it["char"] not in refs:
                d = json.load(open(f"{ROOT}/work/refs/{it['char']}/refs.json", encoding="utf-8"))
                refs[it["char"]] = {r["id"]: r for r in d["refs"]}
            ref_path = refs[it["char"]][it["ref"]]["path"]
        kw = dict(use_emo_text=True, emo_text=it["emo_text"], emo_alpha=it.get("emo_alpha", 0.3), use_random=False) if it.get("emo_text") else {}
        lines = it["lines"] + ([dict(line_id=None, text=it["tail"])] if it.get("tail") else [])
        whole = f"{out}/wav/_whole_{lines[0]['line_id']}_{it['tag']}.wav"
        torch.manual_seed(it.get("seed", 1234))
        tts.infer(spk_audio_prompt=ref_path, text="".join(l["text"] for l in lines), output_path=whole, verbose=False, **kw)
        y, sr = sf.read(whole)
        cuts, how, last_ms = [0], "single", {}
        if len(lines) > 1:
            res = asr.generate(input=whole)[0]
            toks, ts = res["text"].split(), res.get("timestamp") or []
            ref_units = [units(l["text"]) for l in lines]
            flat = [u for us in ref_units for u in us]
            hyp = [u for t in toks for u in (units(t) or ["_"])][:len(ts)] if ts and len(ts) == len(toks) else None
            if hyp:
                pos, k, how = align(flat, hyp), 0, "asr"
                for n_line, us in enumerate(ref_units[:-1]):
                    k += len(us)
                    last_ms[n_line] = ts[pos[k - 1]][1] - ts[pos[k - 1]][0]     # 這句最後一個字念了多久
                    a, b = ts[pos[k - 1]][1], ts[min(pos[k], len(ts) - 1)][0]
                    if b - a < 60:      # 兩句黏在一起，或後一句沒被認出來：往後找 0.5 秒
                        b = a + 500
                    lo, hi = int(a / 1000 * sr), min(int(b / 1000 * sr), len(y) - 1)
                    w = int(0.02 * sr)  # 在兩句之間挑最安靜的 20 毫秒當切點
                    mono = y if y.ndim == 1 else y.mean(1)
                    cands = list(range(lo, max(hi - w, lo) + 1, w // 2)) or [lo]
                    cuts.append(min(cands, key=lambda c: float(np.mean(mono[c:c + w] ** 2))) + w // 2)
            else:
                k, how = 0, "proportional"
                for us in ref_units[:-1]:
                    k += len(us)
                    cuts.append(int(len(y) * k / len(flat)))
        cuts.append(len(y))
        for n_line, (l, a, b) in enumerate(zip(lines, cuts, cuts[1:])):
            if l["line_id"] is None:
                continue
            path = f"{out}/wav/{l['line_id']}_{it['tag']}.wav"
            seg = y[a:b].copy()
            f = min(int(0.02 * sr), len(seg) // 4)
            if f:
                seg[:f] *= np.linspace(0, 1, f); seg[-f:] *= np.linspace(1, 0, f)
            sf.write(path, seg, sr)
            heard = asr.generate(input=path)[0]["text"].replace(" ", "")
            dur = len(seg) / sr
            row = dict(line_id=l["line_id"], tag=it["tag"], split=how, dur=round(dur, 2),
                       rate=round(max(len(units(l["text"])), 1) / dur, 2), cer=round(cer(l["text"], heard), 3), heard=heard,
                       last_char_ms=last_ms.get(n_line))
            qc.append(row)
            print(row, flush=True)
        os.remove(whole)
    json.dump(qc, open(f"{out}/qc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"SCENE_VARIANTS_DONE {job['scene']} n={len(qc)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
