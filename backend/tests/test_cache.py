"""Tests for utils.cache. Spec §8.2.1 (URL-hash caching)."""
from __future__ import annotations

from pathlib import Path

import pytest

from utils.cache import cache_path_for_url, ensure_cache_dir, is_cached


def test_cache_path_is_deterministic(tmp_path: Path):
    p1 = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    p2 = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert p1 == p2


def test_different_urls_produce_different_paths(tmp_path: Path):
    p1 = cache_path_for_url("https://example.com/a.mid", base=tmp_path)
    p2 = cache_path_for_url("https://example.com/b.mid", base=tmp_path)
    assert p1 != p2


def test_cache_path_lives_under_base(tmp_path: Path):
    p = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert tmp_path in p.parents


def test_cache_path_uses_mid_extension(tmp_path: Path):
    p = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert p.suffix == ".mid"


def test_is_cached_false_when_missing(tmp_path: Path):
    assert is_cached("https://example.com/missing.mid", base=tmp_path) is False


def test_is_cached_true_after_write(tmp_path: Path):
    p = cache_path_for_url("https://example.com/exists.mid", base=tmp_path)
    p.write_bytes(b"MThd")
    assert is_cached("https://example.com/exists.mid", base=tmp_path) is True


def test_ensure_cache_dir_creates_directory(tmp_path: Path):
    target = tmp_path / "nested" / "cache"
    ensure_cache_dir(target)
    assert target.is_dir()


def test_ensure_cache_dir_idempotent(tmp_path: Path):
    target = tmp_path / "cache"
    ensure_cache_dir(target)
    ensure_cache_dir(target)  # must not raise
    assert target.is_dir()
