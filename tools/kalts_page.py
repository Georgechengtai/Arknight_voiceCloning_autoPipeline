"""BB-ST-1 凱爾希對照頁（一次性）：把她的台詞放回與特蕾西娅交錯的上下文裡，同一段戲換不同做法各聽一次。

輸出 out/act33side_st01/kalts.html（音檔內嵌，不入庫）。
"""
import base64
import html
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "out" / "act33side_st01"
TMP = D / "_k"
P = "act33side_st01_"
CSS = (ROOT / "tools" / "variants_page.py").read_text(encoding="utf-8").split('CSS = """')[1].split('"""')[0]


def clip(seq):
    """seq：[(音檔, 前面留幾秒)]。每個檔去頭去尾、句尾淡出、統一音量後依序接起來。"""
    TMP.mkdir(exist_ok=True)
    parts = []
    for n, (p, gap) in enumerate(seq):
        w = TMP / f"{n:02d}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-60dB:start_silence=0.08,afade=t=in:d=0.06,areverse,"
                        f"dynaudnorm=p=0.7:m=5,adelay={int(gap * 1000)}:all=1", "-ar", "44100", "-ac", "1", str(w)], check=True)
        parts.append(w)
    (TMP / "l.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    out = TMP / "o.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(TMP / "l.txt"),
                    "-af", "apad=pad_dur=0.5", "-b:a", "64k", str(out)], check=True)
    return base64.b64encode(out.read_bytes()).decode()


def row(label, sub, b64, cur=False):
    return (f'<div class="row"><div><b class="{"cur" if cur else ""}">{html.escape(label)}</b><small>{html.escape(sub)}</small></div>'
            f'<audio controls preload="none" src="data:audio/mpeg;base64,{b64}"></audio></div>')


def main():
    T = lambda k: D / "r4" / "wav" / f"{P}{k}_f.wav"          # 特蕾西娅固定用第四版
    body = ['<h1>BB-ST-1 凱爾希對照</h1><p class="mute">兩段戲都放回她和特蕾西娅交錯的上下文裡。特蕾西娅每條都一樣，只有凱爾希換做法。'
            "這一頁句與句之間都留了間隔（同一人接著說 0.9 秒，換人 0.8–1.0 秒），不再緊貼。標成褐色的是第四版用的做法。</p>"]

    body.append("<h2>一、目睹之後（悲痛短句）</h2><p class=\"mute\">順序：特蕾西娅……／（特）所以，到了该告别的时候了／阿米娅……博士……／这……／"
                "（特）我总是说…／（特）你的流浪…／我明知道…为什么……／我应该留下，是我……／（特）因为我相信…</p>")
    G = [("f", "r4", "併段＋情緒描述，強度 0.3", "第四版；三句一段、兩句一段", True),
         ("s", "r4", "併段＋情緒描述，強度 0.5", "回聽多出「啊」「呵」，可能是哭腔", False),
         ("n", "r4", "併段、不加描述", "語氣只跟參考音走", False),
         ("d", "r6", "逐句合成，感傷參考音＋情緒描述", "第一版的做法，補上句尾收音", False),
         ("e", "r6", "逐句合成，只靠感傷參考音", "你在更早的測試裡評過最好的做法", False)]
    for tag, src, label, sub, cur in G:
        K = lambda k: D / src / "wav" / f"{P}{k}_{tag}.wav"
        seq = [(K("0125"), 0), (T("0126"), 0.8), (K("0127"), 1.0), (K("0128"), 0.9), (T("0129"), 0.8), (T("0130"), 0.8),
               (K("0131"), 1.0), (K("0132"), 0.9), (T("0133"), 0.8)]
        body.append(row(label, sub, clip(seq), cur))

    body.append("<h2>二、闖入時（急喊）</h2><p class=\"mute\">順序：Mon3tr！／了结他。／（特）我知道，即使孤身一人…／阿米娅！博士！／系统无响应……这……／"
                "Mon3tr，切开门！／Mon3tr，熔毁！／（特）你相信孤独独属于你…／特蕾西娅——。旁白與刺客拿掉了，Mon3tr 的叫聲留 1 秒空白。</p>")
    ka = lambda k: D / "r2" / "wav" / f"{P}{k}_ka.wav"
    v1 = lambda k: D / "idx_v1" / f"{P}{k}.wav"
    f4 = lambda k: D / "r4" / "wav" / f"{P}{k}_f.wav"
    for label, sub, cur, mid, m108 in [("四句併成一段合成", "第四版", True, f4, f4("0108")),
                                       ("逐句合成", "第二版；「系统无响应」用的是另一段參考音", False, ka, v1("0108"))]:
        seq = [(ka("0099"), 0), (v1("0104"), 1.6), (T("0105"), 0.8), (mid("0106"), 0.8), (m108, 1.6), (mid("0109"), 0.6),
               (mid("0111"), 1.6), (T("0112"), 0.8), (ka("0116"), 1.6)]
        body.append(row(label, sub, clip(seq), cur))

    page = "<title>BB-ST-1 凱爾希對照</title>\n<style>" + CSS + "</style>\n<main>\n" + "\n".join(body) + "\n</main>\n"
    (D / "kalts.html").write_text(page, encoding="utf-8")
    for p in TMP.iterdir():
        p.unlink()
    TMP.rmdir()
    print(f"kalts.html {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
