"""劇情腳本的單行 tokenizer。

一行腳本有四種形態：
  [cmd(k=v, k="v", ...)]      帶參數的指令
  [cmd]                       無參數指令
  [name="X"]台詞              對白（方括號內直接是 k=v，沒有指令名與圓括號）
  純文字                       旁白

參數值可含逗號、括號與空格（Sticker 的 text、size="1280, 100"），
所以用逐字元的狀態機，不用 split。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_INT = re.compile(r"[+-]?\d+\Z")
_FLOAT = re.compile(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?\Z")
# 引號內的值結束後，下一個有意義的字元只可能是這些
_AFTER_VALUE = ",)]"


class TokenizeError(ValueError):
    pass


@dataclass
class Token:
    kind: str                      # "command" | "text" | "blank" | "comment"
    raw: str
    cmd: str | None = None         # 小寫化的指令名；[name="X"] 形式為 "name"
    args: dict = field(default_factory=dict)
    text: str | None = None        # command：] 之後的文字；text：整行
    error: str | None = None       # 以 [ 開頭但解析失敗時的原因


def convert_value(s: str):
    """未加引號的值：true/false → bool，數字 → int/float，其餘保留字串。"""
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _read_quoted(s: str, i: int) -> tuple[str, int]:
    """s[i] 是開頭的引號。回傳 (內容, 結尾引號之後的位置)。

    腳本不轉義引號，台詞裡可能出現裸的 "；因此只有後面（略過空白）
    緊接 , ) ] 或行尾的引號才算結尾。
    """
    j = i + 1
    while True:
        k = s.find('"', j)
        if k < 0:
            raise TokenizeError("引號未閉合")
        nxt = _skip_ws(s, k + 1)
        if nxt >= len(s) or s[nxt] in _AFTER_VALUE:
            return s[i + 1:k], k + 1
        j = k + 1


def _read_bare(s: str, i: int) -> tuple[str, int]:
    j = i
    while j < len(s) and s[j] not in _AFTER_VALUE:
        j += 1
    return s[i:j].strip(), j


def _parse_args(s: str, i: int, closer: str) -> tuple[dict, int]:
    """從 s[i] 起讀 k=v 列表直到 closer。回傳 (args, closer 之後的位置)。鍵一律小寫。"""
    args: dict = {}
    while True:
        i = _skip_ws(s, i)
        if i >= len(s):
            raise TokenizeError(f"缺少 {closer}")
        if s[i] == closer:
            return args, i + 1
        if s[i] == ",":
            i += 1
            continue
        m = _IDENT.match(s, i)
        if not m:
            raise TokenizeError(f"第 {i} 字元處應為參數名")
        key = m.group(0).lower()
        i = _skip_ws(s, m.end())
        if i >= len(s) or s[i] != "=":
            raise TokenizeError(f"參數 {key} 缺少 =")
        i = _skip_ws(s, i + 1)
        if i < len(s) and s[i] == '"':
            value, i = _read_quoted(s, i)
        else:
            bare, i = _read_bare(s, i)
            value = convert_value(bare)
        args[key] = value


def _parse_bracket(line: str) -> Token:
    i = _skip_ws(line, 1)
    m = _IDENT.match(line, i)
    if not m:
        raise TokenizeError("缺少指令名")
    ident = m.group(0)
    j = _skip_ws(line, m.end())
    if j >= len(line):
        raise TokenizeError("缺少 ]")
    if line[j] == "=":
        # [name="X"]台詞：方括號內直接是參數列表
        args, end = _parse_args(line, i, "]")
        cmd = ident.lower()
    elif line[j] == "(":
        args, end = _parse_args(line, j + 1, ")")
        end = _skip_ws(line, end)
        if end >= len(line) or line[end] != "]":
            raise TokenizeError("缺少 ]")
        end += 1
        cmd = ident.lower()
    elif line[j] == "]":
        args, end, cmd = {}, j + 1, ident.lower()
    else:
        raise TokenizeError(f"指令名後出現非預期字元 {line[j]!r}")
    return Token("command", line, cmd=cmd, args=args, text=line[end:].strip())


def tokenize_line(line: str) -> Token:
    line = line.rstrip("\r\n")
    stripped = line.strip()
    if not stripped:
        return Token("blank", line)
    if stripped.startswith("//"):
        return Token("comment", line)
    if not stripped.startswith("["):
        return Token("text", line, text=stripped)
    try:
        tok = _parse_bracket(stripped)
        tok.raw = line
        return tok
    except TokenizeError as e:
        # 不報錯：交給上層當未知指令原樣保留
        return Token("command", line, cmd="_unparsed", error=str(e))
