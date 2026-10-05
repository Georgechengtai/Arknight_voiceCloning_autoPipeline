"""把 ElevenLabs 生成結果（creative_get_flow_run_status 存下的 JSON）下載成每段一個檔。

以 prompt 全文對回 out/<scene>/director_el.json 的 block；網址兩小時失效，所以生成後要馬上跑。
用法：python3 tools/el_fetch.py act33side_st01 <status.json> [...]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(scene, status_files):
    scene_dir = ROOT / "out" / scene
    norm = lambda s: "".join(s.split())
    by_prompt = {norm(b["prompt"]): b for b in json.loads((scene_dir / "director_el.json").read_text(encoding="utf-8"))}
    out = scene_dir / "el"
    out.mkdir(exist_ok=True)
    for path in status_files:
        for g in json.loads(Path(path).read_text(encoding="utf-8"))["generations"]:
            key = norm(g["prompt"])
            block = by_prompt.get(key) or next((b for p, b in by_prompt.items() if len(key) > 150 and p.startswith(key)), None)  # 狀態回傳的 prompt 會截到 200 字
            if not block or g["status"] != "completed":
                print("略過", g["status"], g["prompt"][:20].replace("\n", " "))
                continue
            dest = out / f"{block['block']}.mp3"
            subprocess.run(["curl", "-sf", "-o", str(dest), g["content_url"]], check=True)
            print(block["block"], block["voice"], f"{g['duration_secs']:.1f}s", dest.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
