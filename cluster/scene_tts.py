"""整場合成（幹員部分）：照導演表逐句用 IndexTTS-2 合成，附自動質檢與重試。

定案做法（docs/00-decisions.md）：逐句挑的參考音直接當音色參考音，情緒用文字描述、強度 0.3。
    cd $AKTTS_ROOT/index-tts && python ../scene_tts.py <job.json>
job.json：{"scene": 場景代號, "lines": [{"line_id", "char"（參考音目錄短名）, "ref", "text", "emo_text"}]}
輸出：work/scenes/<scene>/wav/<line_id>.wav、qc.json（每句的長度、語速、回聽文字、拼音字錯率、用了第幾次）

質檢：回聽文字與原文比拼音（去聲調，同音字不算錯）。字錯率 > 0.2 或語速離譜就換種子重來，最多 3 次，留最好的一次。
"""
import json
import os
import re
import sys

ROOT = os.environ["AKTTS_ROOT"]
SEEDS = (1234, 2345, 3456)
KEEP = re.compile(r"[一-鿿A-Za-z0-9]")


def units(text):
    from pypinyin import lazy_pinyin
    return lazy_pinyin("".join(KEEP.findall(text)).lower())


def cer(ref, hyp):
    a, b = units(ref), units(hyp)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] / len(a)


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
    refs = {}
    qc = []
    for ln in job["lines"]:
        if ln["char"] not in refs:
            d = json.load(open(f"{ROOT}/work/refs/{ln['char']}/refs.json", encoding="utf-8"))
            refs[ln["char"]] = {r["id"]: r for r in d["refs"]}
        ref = refs[ln["char"]][ln["ref"]]
        best = None
        for n, seed in enumerate(SEEDS, 1):
            path = f"{out}/wav/{ln['line_id']}.try{n}.wav"
            torch.manual_seed(seed)
            tts.infer(spk_audio_prompt=ref["path"], text=ln["text"], output_path=path, verbose=False,
                      use_emo_text=True, emo_text=ln["emo_text"], emo_alpha=0.3, use_random=False)
            dur = sf.info(path).duration
            heard = asr.generate(input=path)[0]["text"].replace(" ", "")
            n_units = max(len(units(ln["text"])), 1)
            row = dict(line_id=ln["line_id"], char=ln["char"], ref=ln["ref"], tries=n, dur=round(dur, 2),
                       rate=round(n_units / dur, 2), heard=heard, cer=round(cer(ln["text"], heard), 3), path=path)
            row["ok"] = row["cer"] <= 0.2 and 1.0 <= row["rate"] <= 9.0
            if best is None or (row["ok"], -row["cer"]) > (best["ok"], -best["cer"]):
                best = row
            if row["ok"]:
                break
        os.replace(best.pop("path"), f"{out}/wav/{ln['line_id']}.wav")
        for n in range(1, len(SEEDS) + 1):
            p = f"{out}/wav/{ln['line_id']}.try{n}.wav"
            if os.path.exists(p):
                os.remove(p)
        qc.append(best)
        print(best, flush=True)
    json.dump(qc, open(f"{out}/qc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"SCENE_TTS_DONE {job['scene']} n={len(qc)} bad={sum(not r['ok'] for r in qc)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
