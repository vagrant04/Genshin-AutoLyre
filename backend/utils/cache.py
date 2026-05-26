"""URL-hash file cache.

Used by the parse route to avoid re-downloading the same MIDI URL.
Pure path math + filesystem ops; no network.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_CACHE_DIR = Path("/tmp/genshin_lyre")


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def cache_path_for_url(url: str, *, base: Path = DEFAULT_CACHE_DIR) -> Path:
    return base / f"{_hash_url(url)}.mid"


def is_cached(url: str, *, base: Path = DEFAULT_CACHE_DIR) -> bool:
    return cache_path_for_url(url, base=base).is_file()


def ensure_cache_dir(base: Path = DEFAULT_CACHE_DIR) -> None:
    base.mkdir(parents=True, exist_ok=True)
