"""把一場的成品音軌做成單檔試聽頁（音檔內嵌），給 Artifact 發布用。

輸入 out/<scene>/scene.mp3、cues.json；輸出 out/<scene>/scene.html（不入庫）。
頁面只列每句的開頭幾個字當定位用，不放完整劇本。
用法：python3 tools/scene_page.py act33side_st01 "BB-ST-1 整場配音" [備註檔.html]
"""
import base64
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEAD = 14
PALETTE = ["#b4552d", "#2f6f8f", "#5d7a2e", "#8a4f9e", "#a8793a", "#3f7f6b", "#9c4660", "#55618f", "#7a6a3a", "#666"]

CSS = """
:root{--bg:#f6f3ee;--panel:#fffdf9;--fg:#23201c;--mute:#7a7268;--line:#e2dbd0;--hl:#fbeed3;--accent:#9a5b1c}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17150f;--panel:#201d16;--fg:#ebe5d9;--mute:#9a9184;--line:#353026;--hl:#3a2f17;--accent:#e0a35a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#17150f;--panel:#201d16;--fg:#ebe5d9;--mute:#9a9184;--line:#353026;--hl:#3a2f17;--accent:#e0a35a;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.6 "Noto Serif TC","Songti TC","PingFang TC",serif;margin:0;padding-inline:16px}
main{max-width:720px;margin:0 auto;padding-block:28px 120px}
h1{font-size:24px;margin:0 0 4px;text-wrap:balance}
.sub{color:var(--mute);font-size:13px;margin:0 0 20px}
.note{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;font-size:14px;margin-bottom:20px}
.note ul{margin:6px 0 0;padding-left:20px}
.cast{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;margin-bottom:18px}
.cast span{display:inline-flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.seg{display:grid;grid-template-columns:52px 96px minmax(0,1fr);gap:10px;align-items:baseline;width:100%;text-align:left;font:inherit;color:inherit;background:none;border:0;border-bottom:1px solid var(--line);padding:9px 6px;cursor:pointer}
.seg:hover{background:var(--panel)}
.seg.on{background:var(--hl)}
.seg .t{font:12px ui-monospace,Menlo,monospace;color:var(--mute);font-variant-numeric:tabular-nums}
.seg .who{font-size:13px;display:flex;align-items:center;gap:6px;min-width:0}
.seg .tx{color:var(--mute);font-size:14px;min-width:0;overflow-wrap:anywhere}
.seg.on .tx{color:var(--fg)}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--panel);border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom,0px))}
.bar div{max-width:720px;margin:0 auto}
audio{width:100%;display:block}
@media (max-width:480px){.seg{grid-template-columns:44px minmax(0,1fr)}.seg .tx{grid-column:2}}
"""

JS = """
const a=document.getElementById('a'),segs=[...document.querySelectorAll('.seg')];
segs.forEach(b=>b.addEventListener('click',()=>{a.currentTime=+b.dataset.s;a.play()}));
let cur=null;
a.addEventListener('timeupdate',()=>{const t=a.currentTime;let hit=null;
  for(const b of segs){if(t>=+b.dataset.s-0.05)hit=b;else break}
  if(hit!==cur){cur&&cur.classList.remove('on');hit&&hit.classList.add('on');
    if(hit&&!a.paused)hit.scrollIntoView({block:'center',behavior:'smooth'});cur=hit}});
"""


def main(scene, title, note_path=None):
    d = ROOT / "out" / scene
    cues = json.loads((d / "cues.json").read_text(encoding="utf-8"))
    audio = base64.b64encode((d / "scene.mp3").read_bytes()).decode()
    speakers = list(dict.fromkeys(c["speaker"] for c in cues))
    color = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(speakers)}
    esc = html.escape
    rows = []
    for c in cues:
        heads = " ／ ".join(esc(l["text"][:HEAD]) + ("…" if len(l["text"]) > HEAD else "") for l in c["lines"])
        m, s = divmod(int(c["start"]), 60)
        rows.append(f'<button class="seg" data-s="{c["start"]}"><span class="t">{m}:{s:02d}</span>'
                    f'<span class="who"><i class="dot" style="background:{color[c["speaker"]]}"></i>{esc(c["speaker"])}</span>'
                    f'<span class="tx">{heads}</span></button>')
    cast = "".join(f'<span><i class="dot" style="background:{color[s]}"></i>{esc(s)}</span>' for s in speakers)
    total = cues[-1]["end"]
    note = Path(note_path).read_text(encoding="utf-8") if note_path else ""
    page = (f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n<main>\n<h1>{esc(title)}</h1>\n"
            f'<p class="sub">全長 {int(total // 60)} 分 {int(total % 60)} 秒・{len(cues)} 段・點任一段從那裡開始播</p>\n'
            f"{note}\n<div class=\"cast\">{cast}</div>\n" + "\n".join(rows) + "\n</main>\n"
            f'<div class="bar"><div><audio id="a" controls preload="metadata" src="data:audio/mpeg;base64,{audio}"></audio></div></div>\n'
            f"<script>{JS}</script>\n")
    (d / "scene.html").write_text(page, encoding="utf-8")
    print(f"{(d / 'scene.html').relative_to(ROOT)} {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
