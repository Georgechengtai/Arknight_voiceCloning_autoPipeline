"""由劇本＋人工判定產出身份表。

輸入（入庫）：
  config/identity/name_map.tsv           顯示名（可限定台上立繪）→ 規範身份
  config/identity/overrides/<scene>.tsv  逐場逐句的人工判定（通讀全文後寫的）
  config/identity/operators.tsv          規範身份 → 幹員 charId
輸出（入庫）：
  config/identity/act33side.tsv          每個要配音的行一列
  config/identity/speakers.yaml          每個規範身份一條
  docs/identity-review.md                confidence: low 的待確認清單（附上下文）

用法：python3 tools/identity/build.py
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import EXCEL_DIR, ROOT, parse_scene, scene_list

CFG = ROOT / "config" / "identity"
NARRATOR = "旁白"
DOCTOR = "博士"
TAG_RE = re.compile(r"<[^>]+>")
KINDS = {"dialogue", "narration", "monologue", "unknown_language", "silent"}
MAJOR_NPC_LINES = 30
CONTEXT = 3  # 待確認清單每條前後各附幾行原文
MAX_ASKED_SHOWN = 4  # 同一條裡最多完整列出幾句待確認的原文


def clean(text):
    """去掉 <color=…>、<i> 之類的富文本標籤（不屬於台詞本身）。"""
    return TAG_RE.sub("", text)


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_name_map():
    exact, by_name = {}, {}
    for r in read_tsv(CFG / "name_map.tsv"):
        if r["sprite"] == "*":
            by_name[r["shown_as"]] = r
        else:
            exact[(r["shown_as"], r["sprite"])] = r
    return exact, by_name


def load_overrides(scene):
    path = CFG / "overrides" / f"{scene}.tsv"
    rules = []
    if not path.exists():
        return rules
    for r in read_tsv(path):
        spec, _, only_name = r["seq"].partition("@")
        lo, _, hi = spec.partition("-")
        rules.append({"lo": int(lo), "hi": int(hi or lo), "only": only_name or None, **r})
    return rules


def judge(scene, lines, exact, by_name):
    rows = []
    for ln in lines:
        shown = ln["shown_as"]
        row = {"scene": scene, "seq": ln["seq"], "text": ln["text"], "shown_as": shown, "kind": ln["auto_kind"],
               "sprite": ln["speaker_sprite"], "confidence": "high"}
        if not shown:
            row["identity"] = NARRATOR
            row["basis"] = "無名行，預設旁白" if ln["src"] != "subtitle" else "Subtitle 字幕，無說話者標記，預設旁白"
        else:
            hit = exact.get((shown, ln["speaker_sprite"])) or by_name.get(shown)
            if hit:
                row.update(identity=hit["identity"], confidence=hit["confidence"], basis=hit["basis"])
            else:
                row["identity"] = shown
                row["basis"] = "劇本顯示名" + (f"；立繪 {ln['speaker_sprite']}" if ln["speaker_sprite"] else "")
        rows.append(row)

    used = set()
    for i, rule in enumerate(load_overrides(scene)):
        for row in rows:
            if not rule["lo"] <= row["seq"] <= rule["hi"]:
                continue
            if rule["only"] and row["shown_as"] != rule["only"]:
                continue
            used.add(i)
            if rule["identity"] != "-":
                row["identity"] = rule["identity"]
            if rule["kind"] != "-":
                row["kind"] = rule["kind"]
            row["confidence"] = rule["confidence"]
            row["basis"] = rule["basis"]
    unused = [r["seq"] for i, r in enumerate(load_overrides(scene)) if i not in used]
    if unused:
        sys.exit(f"{scene}: 覆寫規則沒有套用到任何行：{unused}")

    for row in rows:
        auto = auto_note(row)
        if auto and auto not in row["basis"]:
            row["basis"] += "；" + auto
        if row["kind"] not in KINDS:
            sys.exit(f"{scene}#{row['seq']}: 未知的 kind {row['kind']}")
    return rows


def auto_note(row):
    if row["kind"] == "silent" and "沒有可念的字" not in row["basis"]:
        return "只有標點或括號內的動作／叫聲描述，沒有可念的字"
    if row["kind"] == "unknown_language":
        return "帶「（未知语言）」標記，不配音"
    return ""


def write_table(rows):
    path = CFG / "act33side.tsv"
    cols = ["scene", "seq", "text_head", "shown_as", "identity", "kind", "confidence", "basis"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r["scene"], r["seq"], clean(r["text"])[:12], r["shown_as"], r["identity"], r["kind"],
                        r["confidence"], r["basis"]])


def operator_info():
    chars = json.loads((EXCEL_DIR / "character_table.json").read_text(encoding="utf-8"))
    langs = json.loads((EXCEL_DIR / "charword_table.json").read_text(encoding="utf-8"))["voiceLangDict"]
    ops = {}
    for r in read_tsv(CFG / "operators.tsv"):
        cid = r["operator_char_id"]
        if cid not in chars:
            sys.exit(f"operators.tsv: {cid} 不在 character_table.json")
        if "CN_MANDARIN" not in langs.get(cid, {}).get("dict", {}):
            sys.exit(f"operators.tsv: {cid} 沒有中文語音（CN_MANDARIN）")
        ops[r["identity"]] = {"char_id": cid, "name": chars[cid]["name"], "note": r["note"]}
    return ops


def yq(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_speakers(rows, ops):
    by_id = defaultdict(list)
    for r in rows:
        by_id[r["identity"]].append(r)
    same_as = {}
    for ident in by_id:
        m = re.match(r"^(.+?)（(幼年|借阿米娅之身)）$", ident)
        if m:
            same_as[ident] = m.group(1)

    def role(ident):
        """同一人的變體（幼年、借他人之身）沿用本人的 role，行數也合併計算。"""
        base = same_as.get(ident, ident)
        if base == NARRATOR:
            return "narrator"
        if base == DOCTOR:
            return "doctor"
        if base in ops:
            return "operator"
        total = sum(len(v) for k, v in by_id.items() if same_as.get(k, k) == base)
        return "npc_major" if total >= MAJOR_NPC_LINES else "npc_minor"

    def sprites_of(rs):
        """只看有顯示名的行當下聚焦的立繪；出現一次的多半是別人站在台上，除非它就是唯一的一張。"""
        c = Counter(r["sprite"] for r in rs if r["shown_as"] and r["sprite"])
        top = c.most_common()
        return [s for i, (s, n) in enumerate(top) if i == 0 or n >= max(2, 0.05 * sum(c.values()))]

    out = ["# 由 tools/identity/build.py 產生，請勿手改；要改判定請改 name_map.tsv、overrides/、operators.tsv 後重跑。",
           "# line_count 含不配音的行；voiced_lines 只算 dialogue / narration / monologue。",
           "# role：operator＝有中文語音的幹員；npc_major＝無幹員語音且（含變體）≥ 30 行；npc_minor＝其餘。",
           "# same_person_as：同一個人的另一種狀態（幼年、借他人身體說話），用不用同一個聲音由選角決定。",
           "# sprite_groups：該身份說話時聚焦的立繪組（已濾掉偶然同台的別人）。",
           "speakers:"]
    order = sorted(by_id, key=lambda k: (-len(by_id[k]), k))
    for ident in order:
        rs = by_id[ident]
        kinds = Counter(r["kind"] for r in rs)
        aliases = sorted({r["shown_as"] for r in rs if r["shown_as"] and r["shown_as"] != ident})
        sprites = sprites_of(rs)
        scenes = sorted({r["scene"].replace("level_act33side_", "") for r in rs})
        voiced = sum(kinds[k] for k in ("dialogue", "narration", "monologue"))
        out.append(f"  {yq(ident)}:")
        out.append(f"    role: {role(ident)}")
        out.append(f"    line_count: {len(rs)}")
        out.append(f"    voiced_lines: {voiced}")
        out.append("    kinds: {" + ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items())) + "}")
        out.append("    aliases: [" + ", ".join(yq(a) for a in aliases) + "]")
        out.append("    sprite_groups: [" + ", ".join(sprites) + "]")
        out.append("    scenes: [" + ", ".join(scenes) + "]")
        if ident in ops:
            out.append(f"    operator_char_id: {ops[ident]['char_id']}")
            out.append(f"    operator_name: {yq(ops[ident]['name'])}")
            if ops[ident]["note"]:
                out.append(f"    note: {yq(ops[ident]['note'])}")
        if ident in same_as:
            out.append(f"    same_person_as: {yq(same_as[ident])}")
            out.append(f"    variant: {yq(ident[len(same_as[ident]) + 1:-1])}")
            base_op = ops.get(same_as[ident])
            if base_op:
                out.append(f"    same_person_operator_char_id: {base_op['char_id']}")
    (CFG / "speakers.yaml").write_text("\n".join(out) + "\n", encoding="utf-8")
    missing = [i for i in ops if i not in by_id]
    if missing:
        sys.exit(f"operators.tsv 有不存在於身份表的身份：{missing}")
    return by_id


KIND_ZH = {"dialogue": "說出口的話", "monologue": "沒說出口的心裡話", "narration": "的旁白",
           "silent": "（無可念的字）", "unknown_language": "的未知語言台詞（不配音）"}


def write_review(rows, scenes):
    by_scene = defaultdict(list)
    for r in rows:
        by_scene[r["scene"]].append(r)
    # 一條 = 同一場裡相鄰（或同一身份、相隔不遠）的 low 行。只有「……」的 silent 行不配音，不拿來問。
    groups = []
    for s in scenes:
        cur = None
        for r in by_scene[s["scene"]]:
            if r["confidence"] != "low" or r["kind"] == "silent":
                continue
            gap = r["seq"] - cur["rows"][-1]["seq"] if cur else None
            if cur and (gap == 1 or (gap <= 6 and r["identity"] == cur["rows"][-1]["identity"])):
                cur["rows"].append(r)
            else:
                cur = {"scene": s, "rows": [r]}
                groups.append(cur)

    def fmt(r, mark):
        who = r["shown_as"] or "（無名行）"
        return f"{mark} {r['seq']:>4}  {who}：{clean(r['text'])}"

    def seq_spans(seqs):
        spans, start, prev = [], seqs[0], seqs[0]
        for x in seqs[1:] + [None]:
            if x is None or x != prev + 1:
                spans.append(f"{start}" if start == prev else f"{start}–{prev}")
                start = x
            prev = x
        return "、".join(spans)

    asked = sum(len(g["rows"]) for g in groups)
    low_total = sum(1 for r in rows if r["confidence"] == "low")
    out = ["# 身份待確認清單（巴别塔 act33side）",
           "",
           f"由 `tools/identity/build.py` 產生。全活動 {len(rows)} 行裡，我沒把握的有 {low_total} 行，整理成下面 {len(groups)} 條"
           f"（{asked} 句；另外 {low_total - asked} 句只有「……」、不配音，跟著同一條的結論走，不另外問）。",
           "其餘的行我有把握，沒有列在這裡。",
           "",
           "每條先說我的判斷與理由，再附劇本原文。原文裡 `>>` 開頭的是要你確認的句子，其餘是前後文"
           f"（前後各至多 {CONTEXT} 行；同一條句子太多時只列頭幾句）。行首數字是該場的第幾句。",
           "",
           "回覆方式：對每一條說「對」或「不對，應該是誰」就可以。",
           ""]
    for n, g in enumerate(groups, 1):
        s, rs = g["scene"], g["rows"]
        scene_rows = {r["seq"]: r for r in by_scene[s["scene"]]}
        lo, hi = rs[0]["seq"], rs[-1]["seq"]
        span = f"第 {lo} 句" if lo == hi else f"第 {lo}–{hi} 句之間的 {len(rs)} 句"
        out.append(f"## {n}. {s['code']}《{s['name']}》{s['tag']}，{span}")
        out.append("")
        verdicts = defaultdict(list)
        for r in rs:
            verdicts[(r["identity"], r["kind"], r["basis"])].append(r["seq"])
        out.append("**我的判斷與理由**")
        out.append("")
        for (ident, kind, basis), seqs in verdicts.items():
            out.append(f"- 第 {seq_spans(seqs)} 句：是「{ident}」{KIND_ZH[kind]}。{basis}。")
        out.append("")
        out.append("**這樣判對嗎？**")
        out.append("")
        out.append("```")
        shown_low = [r["seq"] for r in rs[:MAX_ASKED_SHOWN]]
        last_shown = shown_low[-1]
        for seq in range(lo - CONTEXT, last_shown + 1):
            if seq in scene_rows and (seq < lo or seq in shown_low or seq < last_shown):
                out.append(fmt(scene_rows[seq], ">>" if seq in shown_low else "  "))
        if len(rs) > MAX_ASKED_SHOWN:
            rest = [r["seq"] for r in rs[MAX_ASKED_SHOWN:]]
            out.append(f"   ……（同一人還有第 {seq_spans(rest)} 句，從略）")
        for seq in range(hi + 1, hi + CONTEXT + 1):
            if seq in scene_rows:
                out.append(fmt(scene_rows[seq], "  "))
        out.append("```")
        out.append(f"（場次檔：`{s['scene']}`）")
        out.append("")
    (ROOT / "docs" / "identity-review.md").write_text("\n".join(out), encoding="utf-8")
    return groups


def main():
    exact, by_name = load_name_map()
    scenes = scene_list()
    rows = []
    for s in scenes:
        lines, _ = parse_scene(s["scene"])
        rows.extend(judge(s["scene"], lines, exact, by_name))
    write_table(rows)
    by_id = write_speakers(rows, operator_info())
    groups = write_review(rows, scenes)

    kinds = Counter(r["kind"] for r in rows)
    print(f"場次 {len(scenes)}，行數 {len(rows)}，身份 {len(by_id)} 個")
    print("kind：", dict(sorted(kinds.items())))
    print("confidence：", dict(Counter(r["confidence"] for r in rows)))
    print(f"待確認：{len(groups)} 條、{sum(len(g['rows']) for g in groups)} 句")
    left = [r for r in rows if r["identity"] == "？？？"]
    print("仍是「？？？」的行：", [(r["scene"], r["seq"]) for r in left])


if __name__ == "__main__":
    main()
