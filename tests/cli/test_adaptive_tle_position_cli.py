from dataclasses import dataclass

import pytest

from leo.cli.adaptive_tle_position import (
    _json_diagnostics,
    adaptive_tle_position_complete,
    configuration,
)
from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore
from tests.contracts.test_adaptive_tle_position import document


@dataclass(frozen=True)
class _NumericalReceipt:
    nodes: tuple[int, ...]


def test_numerical_dataclass_tuples_are_normalized_before_contract_validation():
    value = _json_diagnostics(
        {"prediction_bank": _NumericalReceipt((1, 2)).__dict__, "ids": ("a", "b")}
    )
    assert value == {"prediction_bank": {"nodes": [1, 2]}, "ids": ["a", "b"]}
    with pytest.raises(ValueError):
        _json_diagnostics({"score": float("nan")})


def test_completion_rejects_stale_source_or_configuration(tmp_path):
    writer = AdaptiveTlePositionStore(tmp_path, read_only=False)
    writer.publish(document(), b"\x89PNG\r\n\x1a\nmap")
    assert not adaptive_tle_position_complete(tmp_path, "scan-1")
    changed = document().model_copy(
        update={"configuration_sha256": canonical_digest(configuration())}
    )
    other = tmp_path / "other"
    other.mkdir()
    AdaptiveTlePositionStore(other, read_only=False).publish(
        changed, b"\x89PNG\r\n\x1a\nmap"
    )
    assert not adaptive_tle_position_complete(
        other, "scan-1", expected_input="sha256:" + "9" * 64
    )
    assert not adaptive_tle_position_complete(
        other, "scan-1", expected_analysis="sha256:" + "9" * 64
    )
