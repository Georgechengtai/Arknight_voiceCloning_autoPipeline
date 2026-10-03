"""GPT-SoVITS 少量樣本微調試驗：用一位幹員的整池中文原聲訓練，再合成與 real_ab.py 相同的台詞。

在 GPT-SoVITS 倉庫根目錄、aktts-gsv 環境下執行（由 gsv_finetune.sh 依序呼叫）：
    python gsv_pipeline.py data      # 下載語音表與原聲，產生訓練標註檔
    python gsv_pipeline.py prepare   # 文字/語音特徵抽取（官方介面「一鍵三連」的四個腳本）
    python gsv_pipeline.py train_s2  # 訓練 SoVITS（音色）
    python gsv_pipeline.py train_s1  # 訓練 GPT（語氣韻律）
    python gsv_pipeline.py infer     # 用未微調底模與微調後模型各合成一遍

流程與參數照抄官方 webui.py 的預設值（v2Pro：SoVITS 8 輪、GPT 15 輪）。
「同文對比」用到的原聲（HOLDOUT）不進訓練集，確保對比公平。
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from types import SimpleNamespace

ROOT = os.environ["AKTTS_ROOT"]
CHAR_KEY, CHAR_ID, CHAR_NAME = "kalts", "char_003_kalts", "凯尔希"
EXP = f"aktts_{CHAR_KEY}"
VERSION = "v2Pro"
WORK = f"{ROOT}/work/gsv_{CHAR_KEY}"
DATA = f"{WORK}/data"
LIST = f"{WORK}/train.list"
HOLDOUT = {"CN_036", "CN_002"}
PM = "GPT_SoVITS/pretrained_models"
S2G, S2D, S1 = f"{PM}/v2Pro/s2Gv2Pro.pth", f"{PM}/v2Pro/s2Dv2Pro.pth", f"{PM}/s1v3.ckpt"
BERT, HUBERT = f"{PM}/chinese-roberta-wwm-ext-large", f"{PM}/chinese-hubert-base"
SV = f"{PM}/sv/pretrained_eres2netv2w24s4ep4.ckpt"
VOICE_SRC = "https://raw.githubusercontent.com/PseudoMon/arknights-audio/master/voice_cn"
TABLE_SRC = ("https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/"
             "zh_CN/gamedata/excel/charword_table.json")
SEED = 1234

# 與 real_ab.py 相同的台詞
SAME = [("CN_036", "你似乎更加适应自己的工作和职责了，更像一个领导者了。"),
        ("CN_002", "我会定期为你进行理学检查，记录你的生命征象与意识状态，其他人没有这个权限。"
                   "任何人想对你进行进一步的检查，你都有权拒绝，明白吗？")]
STORY = [("Monster，切开门！", "urgent"), ("阿米娅！博士！", "urgent"), ("特蕾西娅……", "soft"),
         ("我明知道这样的可能性始终存在……为什么……", "soft"), ("我应该留下，是我……", "soft")]
CALM_REF = "CN_011"
# 情緒相近的參考音候選（依台詞內容挑的，未經人聽確認）；實際取第一個長度落在 3–10 秒內的
EMO_REFS = {"urgent": ["CN_031", "CN_032", "CN_020", "CN_030", "CN_029"],
            "soft": ["CN_010", "CN_013", "CN_014"]}
AUX_REFS = ["CN_003", "CN_005", "CN_007", "CN_008", "CN_009"]  # 輔助參考音（音色融合）


def fetch(url, path):
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(url, path)


def voice_table():
    p = f"{WORK}/charword_table.json"
    fetch(TABLE_SRC, p)
    rows = {}
    for v in json.load(open(p, encoding="utf-8"))["charWords"].values():
        if v.get("charId") == CHAR_ID and v["voiceId"].startswith("CN_") and v["voiceId"] not in rows:
            t = v["voiceText"].replace("Dr.{@nickname}", "博士").replace("{@nickname}", "博士")
            rows[v["voiceId"]] = re.sub(r"\s+", "", t).replace("|", "，")
    return dict(sorted(rows.items()))


def data():
    import soundfile as sf
    table = voice_table()
    lines, total = [], 0.0
    for vid, text in table.items():
        mp3 = f"{DATA}/{vid}.mp3"
        fetch(f"{VOICE_SRC}/{CHAR_ID}/{vid}.mp3", mp3)
        dur = sf.info(mp3).duration
        if vid in HOLDOUT:
            continue
        lines.append(f"{vid}.mp3|{CHAR_KEY}|ZH|{text}")
        total += dur
    open(LIST, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(dict(texts=table, n_train=len(lines), train_minutes=round(total / 60, 2), holdout=sorted(HOLDOUT)),
              open(f"{WORK}/meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"DATA_DONE lines={len(lines)} minutes={total / 60:.2f} (holdout {sorted(HOLDOUT)})", flush=True)


def run(script, env):
    e = dict(os.environ, **env)
    print("+", script, flush=True)
    subprocess.run([sys.executable, "-s", script], env=e, check=True)


def prepare():
    opt = f"logs/{EXP}"
    os.makedirs(opt, exist_ok=True)
    common = dict(inp_text=LIST, inp_wav_dir=DATA, exp_name=EXP, opt_dir=opt, i_part="0", all_parts="1",
                  _CUDA_VISIBLE_DEVICES="0", is_half="True", version=VERSION)
    run("GPT_SoVITS/prepare_datasets/1-get-text.py", dict(common, bert_pretrained_dir=BERT))
    shutil.move(f"{opt}/2-name2text-0.txt", f"{opt}/2-name2text.txt")
    feat = dict(common, cnhubert_base_dir=HUBERT, sv_path=SV)
    run("GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py", feat)
    run("GPT_SoVITS/prepare_datasets/2-get-sv.py", feat)
    run("GPT_SoVITS/prepare_datasets/3-get-semantic.py",
        dict(common, pretrained_s2G=S2G, s2config_path=f"GPT_SoVITS/configs/s2{VERSION}.json"))
    body = open(f"{opt}/6-name2semantic-0.tsv", encoding="utf-8").read().strip("\n")
    open(f"{opt}/6-name2semantic.tsv", "w", encoding="utf-8").write("item_name\tsemantic_audio\n" + body + "\n")
    os.remove(f"{opt}/6-name2semantic-0.tsv")
    n = len(open(f"{opt}/2-name2text.txt", encoding="utf-8").read().strip().split("\n"))
    # 官方腳本逐檔吞掉例外，壞了也會照常結束；這裡逐個目錄數檔案，缺了就停
    counts = {d: len(os.listdir(f"{opt}/{d}")) if os.path.isdir(f"{opt}/{d}") else 0
              for d in ("3-bert", "4-cnhubert", "5-wav32k", "7-sv_cn")}
    print(f"PREPARE_DONE text_lines={n} semantic_lines={len(body.splitlines())} features={counts}", flush=True)
    assert all(c >= n for c in counts.values()) and len(body.splitlines()) >= n, f"特徵不齊：{counts}"


def train_s2():
    d = json.load(open(f"GPT_SoVITS/configs/s2{VERSION}.json"))
    s2_dir = f"logs/{EXP}"
    os.makedirs(f"{s2_dir}/logs_s2_{VERSION}", exist_ok=True)
    d["train"].update(batch_size=12, epochs=8, text_low_lr_rate=0.4, pretrained_s2G=S2G, pretrained_s2D=S2D,
                      if_save_latest=True, if_save_every_weights=True, save_every_epoch=4, gpu_numbers="0",
                      grad_ckpt=False, lora_rank="32")
    d["model"]["version"] = VERSION
    d["data"]["exp_dir"] = d["s2_ckpt_dir"] = s2_dir
    d["save_weight_dir"], d["name"], d["version"] = f"SoVITS_weights_{VERSION}", EXP, VERSION
    os.makedirs("TEMP", exist_ok=True)
    os.makedirs(d["save_weight_dir"], exist_ok=True)  # 官方介面啟動時會建；不建的話訓練照跑但權重存不下來
    json.dump(d, open("TEMP/tmp_s2.json", "w"))
    t = time.time()
    subprocess.run([sys.executable, "-s", "GPT_SoVITS/s2_train.py", "--config", "TEMP/tmp_s2.json"],
                   env=dict(os.environ, version=VERSION), check=True)
    weights = glob.glob(f"SoVITS_weights_{VERSION}/{EXP}_e*")
    print(f"S2_DONE seconds={time.time() - t:.0f} weights={weights}", flush=True)
    assert weights, "SoVITS 權重沒有存下來"


def train_s1():
    import yaml
    d = yaml.load(open("GPT_SoVITS/configs/s1longer-v2.yaml"), Loader=yaml.FullLoader)
    s1_dir = f"logs/{EXP}"
    os.makedirs(f"{s1_dir}/logs_s1", exist_ok=True)
    d["train"].update(batch_size=12, epochs=15, save_every_n_epoch=5, if_save_every_weights=True,
                      if_save_latest=True, if_dpo=False, half_weights_save_dir=f"GPT_weights_{VERSION}", exp_name=EXP)
    d["pretrained_s1"] = S1
    d["train_semantic_path"] = f"{s1_dir}/6-name2semantic.tsv"
    d["train_phoneme_path"] = f"{s1_dir}/2-name2text.txt"
    d["output_dir"] = f"{s1_dir}/logs_s1_{VERSION}"
    os.makedirs("TEMP", exist_ok=True)
    os.makedirs(f"GPT_weights_{VERSION}", exist_ok=True)
    yaml.dump(d, open("TEMP/tmp_s1.yaml", "w"), default_flow_style=False)
    t = time.time()
    subprocess.run([sys.executable, "-s", "GPT_SoVITS/s1_train.py", "--config_file", "TEMP/tmp_s1.yaml"],
                   env=dict(os.environ, _CUDA_VISIBLE_DEVICES="0", hz="25hz", version=VERSION), check=True)
    weights = glob.glob(f"GPT_weights_{VERSION}/{EXP}-e*")
    print(f"S1_DONE seconds={time.time() - t:.0f} weights={weights}", flush=True)
    assert weights, "GPT 權重沒有存下來"


def latest(pattern, rx):
    files = glob.glob(pattern)
    assert files, f"找不到權重：{pattern}"
    return max(files, key=lambda f: int(re.search(rx, f).group(1)))


def infer():
    import soundfile as sf
    import torch
    os.environ.update(version=VERSION, gpt_path=S1, sovits_path=S2G, is_half="True")
    from tools.i18n.i18n import I18nAuto
    from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
    i18n = I18nAuto(language=os.environ.get("language", "Auto"))  # must match the language inference_webui uses, else KeyError("Chinese")
    table = json.load(open(f"{WORK}/meta.json", encoding="utf-8"))["texts"]
    dur = lambda vid: sf.info(f"{DATA}/{vid}.mp3").duration
    emo_ref = {k: next((v for v in c if 3.2 <= dur(v) <= 9.8), CALM_REF) for k, c in EMO_REFS.items()}
    aux = [SimpleNamespace(name=f"{DATA}/{v}.mp3") for v in AUX_REFS]

    def items(with_emo):
        out = [dict(id=f"same_{vid}", text=t, ref=CALM_REF, line=f"same_{vid}") for vid, t in SAME]
        for i, (t, kind) in enumerate(STORY, 1):
            out.append(dict(id=f"story{i}_calm", text=t, ref=CALM_REF, line=f"story{i}"))
            if with_emo:
                out.append(dict(id=f"story{i}_emo", text=t, ref=emo_ref[kind], line=f"story{i}"))
        return out

    ft_s2 = latest(f"SoVITS_weights_{VERSION}/{EXP}_e*_s*.pth", r"_e(\d+)_s")
    ft_s1 = latest(f"GPT_weights_{VERSION}/{EXP}-e*.ckpt", r"-e(\d+)\.ckpt")
    results = dict(emo_ref=emo_ref, emo_ref_text={k: table[v] for k, v in emo_ref.items()},
                   calm_ref=CALM_REF, aux_refs=AUX_REFS, weights=dict(sovits=ft_s2, gpt=ft_s1), rows=[])
    for tag, s2, s1, with_emo in (("base", S2G, S1, False), ("ft", ft_s2, ft_s1, True)):
        change_gpt_weights(gpt_path=s1)
        # 不帶語言參數時，官方函式在載完模型後更新介面的那一步會丟 UnboundLocalError（實測）
        for _ in change_sovits_weights(sovits_path=s2, prompt_language=i18n("中文"), text_language=i18n("中文")):
            pass
        os.makedirs(f"{WORK}/gen/{tag}", exist_ok=True)
        for it in items(with_emo):
            path = f"{WORK}/gen/{tag}/{it['id']}.wav"
            torch.manual_seed(SEED)
            t = time.time()
            try:
                lang = i18n("中英混合") if re.search(r"[A-Za-z]", it["text"]) else i18n("中文")
                out = list(get_tts_wav(
                    ref_wav_path=f"{DATA}/{it['ref']}.mp3", prompt_text=table[it["ref"]], prompt_language=i18n("中文"),
                    text=it["text"], text_language=lang,
                    how_to_cut=i18n("凑四句一切") if len(it["text"]) > 50 else i18n("不切"),
                    top_k=15, top_p=1, temperature=1, inp_refs=aux))
                sr, audio = out[-1]
                sf.write(path, audio, sr)
                row = dict(tag=tag, ok=True, gen_s=round(time.time() - t, 2), audio_s=round(len(audio) / sr, 2), **it)
            except Exception as e:
                row = dict(tag=tag, ok=False, error=repr(e)[:300], **it)
            results["rows"].append(row)
            print(f"[{tag}] {row}", flush=True)
    json.dump(results, open(f"{WORK}/gen/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(r["ok"] for r in results["rows"])
    print(f"INFER_DONE ok={ok} fail={len(results['rows']) - ok} emo_ref={emo_ref}", flush=True)


if __name__ == "__main__":
    {"data": data, "prepare": prepare, "train_s2": train_s2, "train_s1": train_s1, "infer": infer}[sys.argv[1]]()
