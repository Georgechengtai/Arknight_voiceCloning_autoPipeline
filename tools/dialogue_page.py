"""BB-ST-1 對話段對照頁（一次性）：特雷西斯、尤莉叶、曼弗雷德那場戲，原版與「照對方的話來寫語氣」的版本。

輸出 out/act33side_st01/dialogue.html（音檔內嵌，不入庫）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kalts_page as K  # noqa: E402  借用它的接軌與版面

D = K.D
ORDER = [f"b{n}" for n in range(19, 34)]


def main():
    old = {b["block"]: b for b in json.loads((D / "director_el.json").read_text(encoding="utf-8"))}
    new = {b["block"]: b for b in json.loads((D / "director_el_dlg.json").read_text(encoding="utf-8"))}
    # 原版的間隔照整場成品：指定值優先，否則換人 0.6 秒
    seq_old = [(D / "el" / f"{b}.mp3", 0 if n == 0 else old[b].get("gap_before", 0.6) + (1.0 if b == "b20" else 0)) for n, b in enumerate(ORDER)]
    seq_new = [(D / "el_dlg" / f"{b}.mp3", 0 if n == 0 else new[b]["gap_before"]) for n, b in enumerate(ORDER)]
    body = ['<h1>BB-ST-1 對話段對照</h1><p class="mute">特雷西斯、尤莉叶、曼弗雷德在倫蒂尼姆的那場戲（整場成品 5:13–7:34），從「那么……」到「我会把对你的憎恨，带进坟墓」。'
            "兩條的聲線、台詞都一樣，差別只在每句的語氣標記與句間的間隔怎麼定。</p>",
            K.row("原版：每個角色各自寫語氣", "整場第六版用的；換人說話一律隔 0.6 秒", K.clip(seq_old), True),
            K.row("對戲版：照對方剛說的話來寫", "搶話處縮短、沉默處拉長；語氣標記改成對上一句的反應", K.clip(seq_new)),
            '<h2>對戲版具體改了什麼</h2><ul>'
            "<li>曼弗雷德兩次質問改成搶話（前面只隔 0.3 秒），第二次用喊的；特雷西斯那聲「曼弗雷德。」直接切進來打斷他。</li>"
            "<li>特雷西斯重複她的話「如她所愿，是吗」之前停得更久，語氣由冷改為低而帶哀。</li>"
            "<li>尤莉叶回答質問時不辯解、只是疲憊；聽到任務時先是意外再轉為謹慎；「我们是不是，不可能活着离开那里？」放慢，「好。」之前先吐一口氣。</li>"
            "<li>特雷西斯的「大可去争取。」「曼弗雷德会看好你们。」由平板改成低聲、帶倦意；「……还有什么事吗？」之前留 2 秒。</li>"
            "<li>尤莉叶最後一段：「贱命胚子」那句帶自嘲，「永别了」之前長停頓，最後一句改成近乎耳語。</li></ul>"]
    page = "<title>BB-ST-1 對話段對照</title>\n<style>" + K.CSS + "</style>\n<main>\n" + "\n".join(body) + "\n</main>\n"
    (D / "dialogue.html").write_text(page, encoding="utf-8")
    for p in K.TMP.iterdir():
        p.unlink()
    K.TMP.rmdir()
    print(f"dialogue.html {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
