"""Battle.net product.db (raw protobuf) as found in a Wine/Proton prefix.

Layout (same fields WowUp and Lutris read): top-level field 1 repeated = product install
{1 uid, 2 product code, 3 settings {1 install path, 13 game subfolder},
 4 cached state {1 base state {1 installed, 2 playable, 3 update complete, 7 version}}, 6 family}.
Match on the product code, not the uid (e.g. uid wow_classic_anniversary vs code wow_anniversary).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .log import logger


def _varint(b: bytes, i: int) -> Tuple[int, int]:
    shift = result = 0
    while True:
        if i >= len(b):
            raise ValueError("truncated varint")
        c = b[i]
        i += 1
        result |= (c & 0x7F) << shift
        if not c & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _fields(b: bytes) -> List[Tuple[int, int, Any]]:
    out, i = [], 0
    while i < len(b):
        key, i = _varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _varint(b, i)
            if i + ln > len(b):
                raise ValueError("truncated length-delimited field")
            v, i = b[i:i + ln], i + ln
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        out.append((fn, wt, v))
    return out


def _all(fields: List[Tuple[int, int, Any]], n: int) -> List[Any]:
    return [v for f, _, v in fields if f == n]


def _str(fields: List[Tuple[int, int, Any]], n: int) -> str:
    vals = [v for v in _all(fields, n) if isinstance(v, (bytes, bytearray))]
    return vals[0].decode("utf-8", "replace") if vals else ""


def decode_product_db(data: bytes) -> List[Dict[str, Any]]:
    products = []
    for raw in _all(_fields(data), 1):
        if not isinstance(raw, (bytes, bytearray)):
            continue
        f = _fields(raw)
        item: Dict[str, Any] = {"uid": _str(f, 1), "code": _str(f, 2), "family": _str(f, 6),
                                "installPath": "", "subfolder": "", "version": "",
                                "installed": None, "playable": None, "updateComplete": None}
        for st in _all(f, 3):
            sf = _fields(st)
            item["installPath"] = _str(sf, 1)
            item["subfolder"] = _str(sf, 13)
        for cs in _all(f, 4):
            for base in _all(_fields(cs), 1):
                bf = _fields(base)
                for key, n in (("installed", 1), ("playable", 2), ("updateComplete", 3)):
                    vals = [v for v in _all(bf, n) if isinstance(v, int)]
                    if vals:
                        item[key] = bool(vals[0])
                item["version"] = _str(bf, 7) or item["version"]
        products.append(item)
    return products


def read_products(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "rb") as f:
            return decode_product_db(f.read())
    except (OSError, ValueError) as e:
        logger.warning("cannot read product.db %s: %s", path, e)
        return []
