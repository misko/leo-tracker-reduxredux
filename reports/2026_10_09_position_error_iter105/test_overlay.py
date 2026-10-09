"""Exact-key cache identity and persistent slice-cap controls."""

import hashlib

import pytest
from overlay import Overlay, claim_slice, read, write

from leo.contracts.digests import canonical_digest


def test_no_unsafe_key_alias_or_unverified_cache(tmp_path):
    value = {"result": {"bootstrap": {"vector": [1, 2]}, "fits": {}}, "reason": None}
    write(tmp_path / "value.json", value)
    source = {
        "old-config:point:1:2": dict(
            file="value.json",
            value_sha256=canonical_digest(value),
            file_sha256=hashlib.sha256((tmp_path / "value.json").read_bytes()).hexdigest(),
        )
    }
    checks = []
    cache = Overlay(
        tmp_path / "local",
        "protocol",
        tmp_path,
        source,
        compatible=False,
        verify_coarse=lambda row: checks.append(row),
    )
    assert cache.get("old-config:point:1:2") is None
    cache.compatible = True
    assert cache.get("b7-shared:point:1:2") is None
    assert cache.get("old-config:point:1:2") == value
    assert len(checks) == 1
    assert cache.get("old-config:point:1:2") == value and len(checks) == 1
    (tmp_path / "value.json").write_text("{}")
    with pytest.raises(AssertionError):
        cache.get("old-config:point:1:2")


def test_local_append_only_binding(tmp_path):
    cache = Overlay(tmp_path, "protocol", tmp_path, {})
    cache.put("key", {"result": 1})
    cache.put("key", {"result": 1})
    assert cache.get("key") == {"result": 1}
    with pytest.raises(AssertionError):
        cache.put("key", {"result": 2})
    other = Overlay(tmp_path, "different-protocol", tmp_path, {})
    with pytest.raises(AssertionError):
        other.get("key")


def test_claimed_crashes_count_toward_six_slice_cap(tmp_path):
    assert [claim_slice(tmp_path, "baseline", "protocol") for _ in range(6)] == list(range(1, 7))
    assert claim_slice(tmp_path, "baseline", "protocol") is None
    assert claim_slice(tmp_path, "candidate", "protocol") == 1
    assert len(list(tmp_path.glob("baseline-*.started.json"))) == 6
    with pytest.raises(AssertionError):
        claim_slice(tmp_path, "baseline", "replacement-protocol")
    assert read(tmp_path / "baseline-06.started.json")["slice"] == 6


def test_explicit_coarse_alias_requires_compatibility_and_exact_objective(tmp_path):
    value = {"result": {"bootstrap": {}, "fits": {}}, "reason": None}
    write(tmp_path / "value.json", value)
    entry = dict(
        file="value.json",
        value_sha256=canonical_digest(value),
        file_sha256=hashlib.sha256((tmp_path / "value.json").read_bytes()).hexdigest(),
    )
    source = {"current:point:1:2": entry, "current:point:1:2:calibration": entry}
    calls = []
    cache = Overlay(
        tmp_path / "local",
        "protocol",
        tmp_path,
        source,
        compatible=False,
        coarse_alias_prefix="current",
        verify_coarse=lambda row: calls.append(row),
    )
    assert cache.get("b7-shared:point:1:2") is None
    cache.compatible = True
    assert cache.get("b7-shared:point:1:2") == value
    assert len(calls) == 1
    assert cache.aliases["b7-shared:point:1:2"]["coarse_objective_verified"]
    assert cache.get("b7-shared:point:1:2:calibration") is None
    assert cache.get("b7-shared:recovery:point:1:2") is None

    def reject(row):
        raise AssertionError("objective mismatch")

    other = Overlay(
        tmp_path / "other",
        "protocol",
        tmp_path,
        source,
        compatible=True,
        coarse_alias_prefix="current",
        verify_coarse=reject,
    )
    with pytest.raises(AssertionError):
        other.get("b7-shared:point:1:2")
    assert not other.aliases
