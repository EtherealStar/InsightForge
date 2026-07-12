"""正文正规化和稳定指纹算法，不依赖数据库或缓存。"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from models.document_governance import SimHashFingerprint

NORMALIZATION_VERSION = "normalization-v1"
SHINGLE_VERSION = "shingle-v1"


def normalize_content(text: str) -> str:
    # 链接目标是抓取实现细节，用户可见链接文字仍然保留。
    text = re.sub(r"!?(\[([^]]+)\])\([^)]*\)", r"\2", text)
    text = re.sub(r"[`*_>#~]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def _shingles(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?", text)
    latin = {" ".join(words[i : i + 3]) for i in range(max(0, len(words) - 2))}
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    han = {"".join(cjk[i : i + 3]) for i in range(max(0, len(cjk) - 2))}
    return latin | han


def simhash(text: str) -> SimHashFingerprint:
    tokens = list(_shingles(text)) or [text]
    bits = [0] * 64
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        for bit in range(64):
            bits[bit] += 1 if value & (1 << bit) else -1
    value = sum((1 << bit) for bit, score in enumerate(bits) if score >= 0)
    return SimHashFingerprint(
        value=value,
        high_bands=tuple((value >> (16 * i)) & 0xFFFF for i in range(4)),
        gray_bands=tuple((value >> (8 * i)) & 0xFF for i in range(8)),
    )


def fingerprint(text: str) -> tuple[str, SimHashFingerprint, set[str]]:
    normalized = normalize_content(text)
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return content_hash, simhash(normalized), _shingles(normalized)


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def shingle_similarity(left: set[str], right: set[str]) -> tuple[float, float]:
    if not left or not right:
        return 0.0, 0.0
    overlap = len(left & right)
    return overlap / len(left | right), overlap / min(len(left), len(right))
