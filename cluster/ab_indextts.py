"""IndexTTS-2 與 IndexTTS-2.5 的試聽對比（設計決定 D3 的版本取捨用）。

用法（在 index-tts 倉庫目錄下、已 source env.sh）： python ab_indextts.py v2|v25
同一組句子、同一組參考音，各版本各合成一遍，輸出到 $AKTTS_ROOT/work/ab_test/<版本>/。
參考音用 IndexTTS 官方示例音（不是遊戲素材）；句子是自擬的，不是遊戲腳本。
"""
import glob
import json
import os
import sys
import time

import soundfile as sf
import torch

ver = sys.argv[1]
root = os.environ["AKTTS_ROOT"]
out_dir = f"{root}/work/ab_test/{ver}"
os.makedirs(out_dir, exist_ok=True)

TEXTS = [
    "博士，今天的作战记录已经整理好了，请您过目。",
    "我们没有退路了。但只要还有一个人站着，这座城市就不会沦陷。",
    "……你真的觉得，这样就能改变什么吗？",
    "萨卡兹的雇佣兵从不相信誓言，他们只相信握在手里的刀。",
]
voices = [v for v in ("examples/voice_01.wav", "examples/voice_07.wav") if os.path.exists(v)]
if len(voices) < 2:
    voices = sorted(glob.glob("examples/voice_*.wav"))[:2]
assert voices, "找不到示例參考音（examples/voice_*.wav）"

t0 = time.time()
if ver == "v2":
    from indextts.infer_v2 import IndexTTS2
    md = f"{root}/models/IndexTTS-2"
    tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md,
                    use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
    extra = {}
elif ver == "v25":
    from indextts.infer_v2_5 import IndexTTS2
    md = f"{root}/models/IndexTTS-2.5"
    tts = IndexTTS2(cfg_path=f"{md}/config.yaml", model_dir=md, use_bf16=True)
    extra = {"lang": "ZH"}
else:
    sys.exit("版本參數必須是 v2 或 v25")
load_s = time.time() - t0

rows = []
for vi, voice in enumerate(voices, 1):
    for ti, text in enumerate(TEXTS, 1):
        path = f"{out_dir}/voice{vi}_s{ti}.wav"
        t1 = time.time()
        tts.infer(spk_audio_prompt=voice, text=text, output_path=path, verbose=False, **extra)
        gen_s = time.time() - t1
        dur = sf.info(path).duration
        rows.append({"file": os.path.basename(path), "voice": voice, "text": text,
                     "gen_s": round(gen_s, 2), "audio_s": round(dur, 2),
                     "rtf": round(gen_s / dur, 3)})
        print(f"[{ver}] {rows[-1]}", flush=True)

summary = {
    "version": ver,
    "model_load_s": round(load_s, 1),
    "gpu": torch.cuda.get_device_name(0),
    "peak_gpu_mem_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    "mean_rtf": round(sum(r["gen_s"] for r in rows) / sum(r["audio_s"] for r in rows), 3),
    "rows": rows,
}
with open(f"{out_dir}/summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
print(f"AB_DONE {ver} load={summary['model_load_s']}s rtf={summary['mean_rtf']} "
      f"peak_gpu={summary['peak_gpu_mem_gb']}GB", flush=True)
