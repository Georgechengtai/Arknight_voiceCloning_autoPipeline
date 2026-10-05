"""BB-ST-1 第二輪對照頁（一次性）：凱爾希急喊四種做法、特蕾西娅告別四種做法、曼弗雷德與尤莉叶的聲線候選。

輸入：out/act33side_st01/idx/（現用）、r2/wav/（對照實驗）、r2/qc.json、out/elevenlabs/previews/
輸出：out/act33side_st01/variants.html（音檔內嵌，不入庫）
"""
import base64
import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "out" / "act33side_st01"
TMP = D / "_var"
HEAD = 14

CSS = """
:root{--bg:#f6f3ee;--panel:#fffdf9;--fg:#23201c;--mute:#7a7268;--line:#e2dbd0;--accent:#9a5b1c}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17150f;--panel:#201d16;--fg:#ebe5d9;--mute:#9a9184;--line:#353026;--accent:#e0a35a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#17150f;--panel:#201d16;--fg:#ebe5d9;--mute:#9a9184;--line:#353026;--accent:#e0a35a;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.65 "Songti TC","PingFang TC",serif;margin:0;padding-inline:16px}
main{max-width:760px;margin:0 auto;padding-block:28px 60px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:18px;margin:36px 0 6px;border-top:1px solid var(--line);padding-top:22px}
h3{font-size:15px;margin:20px 0 6px}
p{margin:6px 0}.mute{color:var(--mute);font-size:13px}
.row{display:grid;grid-template-columns:minmax(0,210px) minmax(0,1fr);gap:6px 12px;align-items:center;padding:7px 0;border-bottom:1px dashed var(--line)}
.row b{font-weight:600}.row small{display:block;color:var(--mute);font-size:12px}
audio{width:100%;height:34px}
.cur{color:var(--accent)}
@media (max-width:520px){.row{grid-template-columns:minmax(0,1fr)}}
"""


def mp3(src, *filters):
    TMP.mkdir(exist_ok=True)
    out = TMP / "x.mp3"
    af = ",".join(filters) if filters else "anull"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-ac", "1", "-ar", "44100", "-b:a", "64k", str(out)], check=True)
    return base64.b64encode(out.read_bytes()).decode()


def concat(paths, gap=0.7):
    TMP.mkdir(exist_ok=True)
    parts = []
    for n, p in enumerate(paths):
        w = TMP / f"c{n:02d}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-af", f"loudnorm=I=-20:TP=-2,apad=pad_dur={gap}",
                        "-ar", "44100", "-ac", "1", str(w)], check=True)
        parts.append(w)
    (TMP / "l.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    out = TMP / "cat.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(TMP / "l.txt"), str(out)], check=True)
    return mp3(out)


def join(paths, name):
    """同一段切出來的幾句原樣接回去（中間不加空白），當成一個檔。"""
    if len(paths) == 1:
        return paths[0]
    TMP.mkdir(exist_ok=True)
    (TMP / "j.txt").write_text("".join(f"file '{p}'\n" for p in paths))
    out = TMP / f"{name}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(TMP / "j.txt"), str(out)], check=True)
    return out


GROUPS = [["0097", "0105"], ["0112"], ["0118", "0119", "0126"], ["0129", "0130", "0133", "0135"], ["0138", "0139"],
          ["0140", "0141", "0142", "0143", "0144"]]


def row(label, sub, b64, cur=False):
    return (f'<div class="row"><div><b class="{"cur" if cur else ""}">{html.escape(label)}</b><small>{html.escape(sub)}</small></div>'
            f'<audio controls preload="none" src="data:audio/mpeg;base64,{b64}"></audio></div>')


def main():
    lines = {l["line_id"][-4:]: l for l in json.loads((D / "director_idx.json").read_text(encoding="utf-8"))["lines"]}
    qc = {(r["line_id"][-4:], r["tag"]): r for r in json.loads((D / "r2" / "qc.json").read_text(encoding="utf-8"))}
    cur_qc = {r["line_id"][-4:]: r for r in json.loads((D / "idx_qc.json").read_text(encoding="utf-8"))}
    body = ['<h1>BB-ST-1 第二輪對照</h1><p class="mute">針對你聽完整場後的三點回饋。標成褐色的是整場成品裡現在用的版本。</p>']

    body.append("<h2>一、凱爾希的急喊</h2><p>上次你覺得好的樣本，參考音是「急促 A」（兩句戰鬥語音接成），而且沒有加情緒描述。"
                "整場成品我換成了新目錄裡的另一段拼接，又疊了情緒描述，兩個都可能沖淡急促感。下面把兩個因素拆開。</p>")
    KV = [("cur", "現用：新拼接＋情緒描述"), ("kc", "新拼接、不加描述"), ("ka", "急促 A、不加描述（＝上次的做法）"), ("kb", "急促 A＋情緒描述")]
    for k in ["0099", "0106", "0109", "0111", "0116"]:
        body.append(f"<h3>{html.escape(lines[k]['text'])}</h3>")
        for tag, label in KV:
            p = D / "idx" / f"act33side_st01_{k}.wav" if tag == "cur" else D / "r2" / "wav" / f"act33side_st01_{k}_{tag}.wav"
            q = cur_qc[k] if tag == "cur" else qc[(k, tag)]
            body.append(row(label, f"{q['dur']} 秒", mp3(p), tag == "cur"))

    body.append("<h2>二、特蕾西娅的告別（17 句連著聽）</h2><p>把她的 17 句依序接起來（中間別人的台詞拿掉），四種做法各一條。"
                "你的猜測對應的是後兩條：相鄰幾句併成一段一次合成，再照字幕切開。</p>")
    T = [k for k in sorted(lines) if lines[k]["char"] == "cetsyr"]
    TV = [("cur", "現用：逐句合成，每句換參考音", "17 句用了 7 段不同的原聲"),
          ("ta", "逐句合成，全程同一段參考音", "只排除「換參考音」這個因素"),
          ("tb", "併段合成＋情緒描述，同一段參考音", "17 句併成 6 段"),
          ("tc", "併段合成、不加描述，同一段參考音", "語氣完全跟著參考音走")]
    for tag, label, sub in TV:
        paths = [D / "idx" / f"act33side_st01_{k}.wav" if tag == "cur" else D / "r2" / "wav" / f"act33side_st01_{k}_{tag}.wav" for k in T]
        if tag in ("tb", "tc"):     # 併段的：段內照原樣連著，只在段與段之間留空
            paths = [join([D / "r2" / "wav" / f"act33side_st01_{k}_{tag}.wav" for k in g], f"g{n}{tag}") for n, g in enumerate(GROUPS)]
        body.append(row(label, sub, concat(paths), tag == "cur"))

    body.append("<h2>三、曼弗雷德與尤莉叶的聲線</h2><p>新的三個版本把描述改成中年、沉穩、有份量，明寫「不要年輕、不要明亮」。"
                "念的是角色自己的台詞。</p>")
    P = ROOT / "out" / "elevenlabs" / "previews"
    for name, cur, new, hz in [("曼弗雷德", "manfred_1", "manfred2", ["110", "80", "72", "80"]), ("尤莉叶", "yulie_3", "yulie2", ["155", "152", "137", "140"])]:
        body.append(f"<h3>{name}</h3>")
        body.append(row("現用", f"音高中位數 {hz[0]} Hz", mp3(P / f"{cur}.mp3"), True))
        for n, lab in enumerate("甲乙丙", 1):
            body.append(row(f"新 {lab}", f"音高中位數 {hz[n]} Hz", mp3(P / f"{new}_{n}.mp3")))

    page = f"<title>BB-ST-1 第二輪對照</title>\n<style>{CSS}</style>\n<main>\n" + "\n".join(body) + "\n</main>\n"
    (D / "variants.html").write_text(page, encoding="utf-8")
    for p in TMP.iterdir():
        p.unlink()
    TMP.rmdir()
    print(f"variants.html {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
