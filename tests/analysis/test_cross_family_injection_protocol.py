from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from leo.analysis.research.cross_family_injection_protocol import (
    CrossFamilyInjectionProtocol,
    load_cross_family_injection_protocol,
)
from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.contracts.digests import canonical_digest

PROJECT_ROOT = Path(__file__).parents[2]
PROTOCOL_PATH = (
    PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json"
)
POLICY_PATH = PROJECT_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"


def _load(path: Path = PROTOCOL_PATH) -> CrossFamilyInjectionProtocol:
    policy = load_doppler_dataset_policy(POLICY_PATH)
    return load_cross_family_injection_protocol(
        path,
        dataset_policy=policy,
        repository_root=PROJECT_ROOT,
    )


def _mutated(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> Path:
    payload: dict[str, Any] = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    payload["protocol_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "protocol_digest"}
    )
    output = tmp_path / "protocol.json"
    output.write_text(json.dumps(payload), encoding="utf-8")
    return output


def test_protocol_freezes_three_paired_hard_null_backgrounds() -> None:
    protocol = _load()

    assert tuple(item.background_session_id for item in protocol.pairs) == (
        "cap-20260825T062228-886fe2dd9cde",
        "cap-20260825T105640-facdadeffb3b",
        "cap-20260825T111222-a2d4ce2afb9a",
    )
    assert tuple(item.true_catalog_number for item in protocol.pairs) == (64611, 67947, 58209)
    assert all(item.tle_collected_utc_ns < item.span_start_utc_ns for item in protocol.pairs)
    assert all(
        protocol.background(item.background_session_id).sample_count == 5_000_000
        for item in protocol.pairs
    )
    assert protocol.training_fraction == 0.6
    assert protocol.future_fraction == 0.4


def test_protocol_digest_tamper_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["pairs"][0]["true_catalog_number"] = 1
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="digest does not match"):
        _load(path)


def test_future_tle_collection_is_rejected_after_reseal(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda payload: payload["pairs"][0].__setitem__(
            "tle_collected_utc_ns", payload["pairs"][0]["span_start_utc_ns"]
        ),
    )

    with pytest.raises(ValueError, match="must be causal"):
        _load(path)


def test_sample_coordinates_cannot_be_rewrapped_as_later_utc(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda payload: payload["pairs"][1].__setitem__(
            "span_start_utc_ns", payload["pairs"][1]["span_start_utc_ns"] + 1
        ),
    )

    with pytest.raises(ValueError, match="sample coordinates"):
        _load(path)


def test_pair_cannot_use_an_unapproved_background(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda payload: payload["pairs"][0].__setitem__("background_session_id", "other"),
    )

    with pytest.raises(ValueError, match="absent"):
        _load(path)


def test_claim_boundary_cannot_be_promoted_by_reseal(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda payload: payload["interpretation_limits"].__setitem__(
            "secure_norad_permitted", True
        ),
    )

    with pytest.raises(ValueError, match="claim boundary"):
        _load(path)
