from dataclasses import dataclass

import pytest

from leo.cli.adaptive_tle_position import (
    _json_diagnostics,
    adaptive_tle_position_complete,
    configuration,
)
from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV3
from tests.contracts.test_adaptive_tle_position import document_v3


@dataclass(frozen=True)
class _NumericalReceipt:
    nodes: tuple[int, ...]


def test_only_sacramento_runs_and_error_is_relative_to_receiver_reference():
    from types import SimpleNamespace

    from leo.cli.adaptive_tle_position import PRIORS, REFERENCE, _candidate

    assert tuple(PRIORS) == ("sacramento",)
    assert tuple(configuration()["priors"]) == ("sacramento",)
    score = SimpleNamespace(
        tracks=(),
        east_km=0,
        north_km=0,
        residual_rmse_hz=800,
        matched_track_count=0,
        unmatched_track_count=1,
        qualifying_observation_count=0,
    )
    assert _candidate(score, 100, *REFERENCE).horizontal_error_m == pytest.approx(0)
    error = _candidate(score, 100, *PRIORS["sacramento"][:2]).horizontal_error_m
    assert 100000 < error < 150000


def test_numerical_dataclass_tuples_are_normalized_before_contract_validation():
    value = _json_diagnostics(
        {"prediction_bank": _NumericalReceipt((1, 2)).__dict__, "ids": ("a", "b")}
    )
    assert value == {"prediction_bank": {"nodes": [1, 2]}, "ids": ["a", "b"]}
    with pytest.raises(ValueError):
        _json_diagnostics({"score": float("nan")})


def test_completion_rejects_stale_source_or_configuration(tmp_path):
    writer = AdaptiveTlePositionStoreV3(tmp_path, read_only=False)
    writer.publish(document_v3(), b"\x89PNG\r\n\x1a\nmap")
    assert not adaptive_tle_position_complete(tmp_path, "scan-1")
    changed = document_v3().model_copy(
        update={"configuration_sha256": canonical_digest(configuration())}
    )
    other = tmp_path / "other"
    other.mkdir()
    AdaptiveTlePositionStoreV3(other, read_only=False).publish(changed, b"\x89PNG\r\n\x1a\nmap")
    assert adaptive_tle_position_complete(other, "scan-1")
    assert not adaptive_tle_position_complete(other, "scan-1", expected_input="sha256:" + "9" * 64)
    assert not adaptive_tle_position_complete(
        other, "scan-1", expected_analysis="sha256:" + "9" * 64
    )
