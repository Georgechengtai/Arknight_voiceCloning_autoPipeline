"""查幹員表：python3 tools/identity/find_operator.py 名字 [名字…]。印出同名的所有 charId 與其語音語言。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import EXCEL_DIR

chars = json.loads((EXCEL_DIR / "character_table.json").read_text(encoding="utf-8"))
langs = json.loads((EXCEL_DIR / "charword_table.json").read_text(encoding="utf-8"))["voiceLangDict"]
for want in sys.argv[1:]:
    hits = [(cid, c) for cid, c in chars.items()
            if want.lower() in (c.get("name") or "").lower() or want.lower() in (c.get("appellation") or "").lower() or want.lower() in cid]
    if not hits:
        print(f"{want}: 無")
    for cid, c in hits:
        voice = sorted(langs.get(cid, {}).get("dict", {}).keys())
        print(f"{want}: {cid} name={c.get('name')} appellation={c.get('appellation')} profession={c.get('profession')} voice={voice}")
