from __future__ import annotations

from pathlib import Path

import pytest

from leo.api.png_cache import StandardPngDiskCache

_PNG = b"\x89PNG\r\n\x1a\nverified-presentation"


def test_png_cache_publishes_once_and_reads_exact_bytes(tmp_path: Path) -> None:
    cache = StandardPngDiskCache(tmp_path)
    key = "a" * 64

    assert cache.read(key) is None
    assert cache.publish(key, _PNG) == _PNG
    assert cache.read(key) == _PNG
    assert cache.publish(key, _PNG + b"different") == _PNG


def test_png_cache_rejects_invalid_keys_bytes_and_qnap(tmp_path: Path) -> None:
    cache = StandardPngDiskCache(tmp_path)

    with pytest.raises(ValueError, match="cache key"):
        cache.read("../escape")
    with pytest.raises(ValueError, match="PNG bytes"):
        cache.publish("b" * 64, b"not a png")
    with pytest.raises(ValueError, match="approved"):
        StandardPngDiskCache(Path("/mnt/qnap01/leo"))
