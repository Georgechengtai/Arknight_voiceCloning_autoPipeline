"""BB-ST-1 看片後三個問題的候選頁（一次性）：「结局」末字、結尾的「那么……」、旁白的說書人版本。

輸出 out/act33side_st01/fix3.html（音檔內嵌，不入庫）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kalts_page as K  # noqa: E402

D, P = K.D, K.P


def main():
    r4 = lambda k: D / "r4" / "wav" / f"{P}{k}_f.wav"
    r7 = lambda k, t: D / "r7" / "wav" / f"{P}{k}_{t}.wav"
    body = ['<h1>BB-ST-1 看片後的三個問題</h1><p class="mute">標成褐色的是影片裡現在用的版本。</p>']

    body.append("<h2>一、「我不会抱怨自己的结局。」最後一個字</h2>"
                "<p>查過音檔：這一句沒有被切到，後面是完整的靜音。「局」字是模型自己念得又輕又短，大約 0.2 秒就收掉了。"
                "這種情形換一個隨機種子重念通常就不一樣，下面是同樣做法、不同種子的三個版本。</p>")
    body.append(K.row("現用", "影片 11:47 起的那一句", K.clip([(r4("0138"), 0)]), True))
    for n, t in enumerate(("j1", "j2", "j4"), 1):
        body.append(K.row(f"重念 {'甲乙丙'[n - 1]}", "連同下一句「巴别塔的使命结束了…」一起重念，這裡只放這一句", K.clip([(r7("0138", t), 0)])))

    body.append("<h2>二、結尾的「那么……」</h2>"
                "<p>原因我找到一個：為了讓句尾收乾淨，我在每段後面墊了一句不要的話再切掉，墊的是「就这样。」。"
                "模型於是把「那么……就这样。」當成一句平常的話來念，「那么」成了順口帶過的連接詞，不到 1 秒。"
                "這場戲的標題是「未完成的告别」，她沒說出口的是道別，所以我把墊的話改成「再见了，凯尔希。」——"
                "模型念「那么……」時是朝著道別去的，然後我們把道別切掉。下面每條都從「从前，现在，未来……」念起，聽最後兩個字。</p>")
    body.append(K.row("現用", "「那么……」長 0.9 秒", K.clip([(r4("0142"), 0), (r4("0143"), 0.8), (r4("0144"), 0.8)]), True))
    for t, label, sub in [("n1", "改墊道別", "不加描述；「那么……」長 2.3 秒，但機器回聽前面多一個「啊」"),
                          ("n2", "改墊道別，換種子", "2.9 秒"),
                          ("n3", "改墊道別＋描述「輕聲道別，不捨，欲言又止」0.3", "2.3 秒"),
                          ("n4", "改墊道別＋同樣描述 0.5", "3.8 秒；這是全場最後一句，算得上關鍵時刻"),
                          ("n5", "改墊道別，換一段更輕更慢的參考音", "2.1 秒")]:
        body.append(K.row(label, sub, K.clip([(r7("0142", t), 0), (r7("0143", t), 0.8), (r7("0144", t), 0.8)])))

    body.append("<h2>三、旁白：說書人的念法</h2>"
                "<p>聲線不變。原本我替旁白下標記時刻意克制（多數句子不加），結果就是平。說書版每句都照內容給了念法："
                "夢境壓低放慢、短句之間留停頓、動手的地方收緊、轉折處用氣聲；並在文字裡多加了幾個逗號和破折號來製造頓挫（畫面上的字不變）。</p>")
    for b, name in [("b01", "開場的夢（男孩在梦中哭泣…）"), ("b15", "阿斯卡纶下手（她的手越握越紧…）"), ("b38", "凯尔希意識到這次不一樣（消亡，新生，万物轮回。不。…）")]:
        body.append(f"<h3>{name}</h3>")
        body.append(K.row("現用", "", K.clip([(D / "el" / f"{b}.mp3", 0)]), True))
        body.append(K.row("說書版", "", K.clip([(D / "el_story" / f"{b}.mp3", 0)])))

    page = "<title>BB-ST-1 三個問題的候選</title>\n<style>" + K.CSS + "</style>\n<main>\n" + "\n".join(body) + "\n</main>\n"
    (D / "fix3.html").write_text(page, encoding="utf-8")
    for p in K.TMP.iterdir():
        p.unlink()
    K.TMP.rmdir()
    print(f"fix3.html {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
