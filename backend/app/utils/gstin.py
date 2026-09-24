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


STATE_NAMES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}


def state_label(code: str | None) -> str:
    """'29' → 'Karnataka (29)'."""
    name = STATE_NAMES.get(code or "")
    return f"{name} ({code})" if name else f"state {code}"
