"""
Central file I/O helpers.

Every text file CuraVar reads or writes goes through here, and every call uses
an explicit UTF-8 encoding. This exists because Python's open() defaults to the
platform encoding: UTF-8 on Linux/macOS, but cp1252 on Windows, which cannot
represent the em-dashes, arrows, and math symbols in the reports -- so a plain
open(path, "w").write(html) raises UnicodeEncodeError on Windows. Routing all
I/O through these functions makes the behavior identical on every OS.
"""

from __future__ import annotations

import json
from typing import Any


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_json(path: str, obj: Any, indent: int = 2) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
