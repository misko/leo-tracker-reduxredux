from hashlib import sha256
from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest

trial = import_module("reports.ALGO08.single-core-2x.full_member_lookahead_trial")


def test_reference_geometry_requires_digest_and_full_size_metadata(monkeypatch):
    contents = b"reference manifest fixture"
    digest = sha256(contents).hexdigest()
    chunks = [
        SimpleNamespace(window_count=64, uncompressed_bytes=102_400_000, compressed_bytes=size)
        for size in (78_000_001, 79_000_004, 77_000_003)
    ]
    monkeypatch.setattr(
        trial.ShortWindowManifestV2,
        "model_validate_json",
        lambda data: SimpleNamespace(chunks=chunks),
    )
    assert trial.geometry(contents, digest) == (78_000_001, 79_000_004, 77_000_003)
    with pytest.raises(ValueError, match="manifest changed"):
        trial.geometry(contents, "0" * 64)
    chunks[-1].compressed_bytes = 8_000_000
    with pytest.raises(ValueError, match="required full-sized geometry"):
        trial.geometry(contents, digest)


def test_cache_state_is_verified_separately_for_each_arm(monkeypatch):
    calls = []

    def measure(members, query, *, cold):
        calls.append(cold)
        return [0, 0, 0] if cold else [9, 10, 11]

    monkeypatch.setattr(trial, "cache_pages", measure)
    assert trial.verified_start(range(3), None, [9, 10, 11], cold=True) == [0, 0, 0]
    assert trial.verified_start(range(3), None, [9, 10, 11], cold=False) == [9, 10, 11]
    with pytest.raises(ValueError, match="Unmatched private compressed-file page cache"):
        trial.verified_start(range(3), None, [9, 10, 12], cold=False)
    assert calls == [True, False, False]


def test_generated_amplitude_adjustment_preserves_input_and_ci16_layout():
    initial = np.array([[[-1000, 1000], [-1, 1]]], dtype="<i2")
    before = initial.tobytes()
    adjusted = trial.rescale(initial, 200)
    assert initial.tobytes() == before
    assert adjusted.dtype == initial.dtype and adjusted.flags.c_contiguous
    assert adjusted.tolist() == [[[-500, 500], [-1, 0]]]


def test_prefetch_comparison_requires_exact_v3_and_one_cpu(monkeypatch):
    spec = {"member_lookahead": True}
    with pytest.raises(ValueError, match="frozen ALGO08v3"):
        trial.prefetch_comparison(spec)
    monkeypatch.setattr(trial, "ALGO08V3", trial.canonical_digest(spec))
    monkeypatch.setattr(trial.os, "sched_getaffinity", lambda _: {2, 3})
    with pytest.raises(ValueError, match="pinned to one CPU"):
        trial.prefetch_comparison(spec)
    monkeypatch.setattr(trial.os, "sched_getaffinity", lambda _: {2})
    trial.prefetch_comparison(spec)
