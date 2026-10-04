"""直接測 IndexTTS 的情緒文字模型（QwenEmotion）：看它把台詞與描述轉成哪 8 個數字。
用法（index-tts 倉庫目錄、aktts 環境）： python emo_probe.py
"""
import filecmp
import os

from indextts.infer_v2 import QwenEmotion as Q2
from indextts.infer_v2_5 import QwenEmotion as Q25

ROOT = os.environ["AKTTS_ROOT"]
d2, d25 = f"{ROOT}/models/IndexTTS-2/qwen0.6bemo4-merge", f"{ROOT}/models/IndexTTS-2.5/qwen0.6bemo4-merge"
same = all(filecmp.cmp(f"{d2}/{f}", f"{d25}/{f}", shallow=False) for f in os.listdir(d2) if os.path.isfile(f"{d2}/{f}"))
print("SAME_WEIGHTS", same, sorted(os.listdir(d2)) == sorted(os.listdir(d25)), flush=True)
AUTO = ["Monster，切开门！", "阿米娅！博士！", "特蕾西娅……", "我明知道这样的可能性始终存在……为什么……", "我应该留下，是我……",
        "博士和阿米娅……不能再出事……不能！", "欢迎回来，博士。", "不要想着调查，你查不到。",
        "魔王在萨卡兹传统里的地位超乎想象，特蕾西娅的功绩也有目共睹。军事委员会反而不敢有过激的举动。",
        "会痛，但我知道你是坚强的孩子，博士已经写信告诉我了。",
        "而与之对应的，另一个空虚而冰寒的想法，在这万年的岁月里，总是在半夜化作凉意，钻入我的脊髓。"]
DESC = ["冷静、克制，条理清晰地分析局势", "温和而关切，放轻声音", "果断、简短、不容置疑地下达命令", "严肃而忧虑地发问",
        "低沉、缓慢，带着遥远的怀念与感伤", "焦急地大喊", "愤怒地命令", "惊恐地呼喊同伴的名字", "强忍悲痛，声音发抖", "冷峻"]
for name, q in (("v2", Q2(d2)), ("v2.5", Q25(d25))):
    for kind, texts in (("AUTO", AUTO), ("DESC", DESC)):
        for t in texts:
            r = {k: round(v, 2) for k, v in q.inference(t).items() if v > 0}
            print(f"{name}|{kind}|{t[:24]}|{r}", flush=True)
