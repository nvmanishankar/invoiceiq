"""GSTIN format, state code and checksum (build guide section 9, stage 4)."""

import re

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalise_gstin(g: str | None) -> str:
    return (g or "").upper().replace(" ", "")


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def valid_gstin(g: str | None) -> bool:
    g = normalise_gstin(g)
    return bool(GSTIN_RE.match(g)) and 1 <= int(g[:2]) <= 38 and gstin_checksum(g[:14]) == g[14]


def state_code(g: str) -> str:
    return normalise_gstin(g)[:2]


def pan(g: str) -> str:
    return normalise_gstin(g)[2:12]
