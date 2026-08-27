from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.research import satellite_pnt_long_arc_protocol as protocol_module
from leo.analysis.research.satellite_pnt_long_arc_protocol import (
    SatellitePntLongArcProtocolV1,
    load_satellite_pnt_long_arc_protocol,
)
from leo.contracts.digests import canonical_digest

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "config/analysis/satellite-pnt-long-arc-development-protocol-v1.json"


def _document() -> dict[str, Any]:
    value = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _reseal(document: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in document.items() if key != "protocol_digest"}
    return {**payload, "protocol_digest": canonical_digest(payload)}


def _write(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def test_protocol_closes_exact_registry_observations_time_and_claims() -> None:
    protocol = load_satellite_pnt_long_arc_protocol(PROTOCOL, repository_root=ROOT)

    assert protocol.expected_arc_ids == (
        "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
        "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
    )
    assert tuple(item.expected_observation_count for item in protocol.observations) == (881, 550)
    assert protocol.time_treatment.primary_tau_s == 0.0
    assert (
        protocol.time_treatment.sensitivity_lower_s,
        protocol.time_treatment.sensitivity_upper_s,
        protocol.time_treatment.sensitivity_step_s,
        protocol.time_treatment.expected_tau_state_count,
    ) == (-5.0, 5.0, 0.25, 41)
    assert protocol.time_treatment.wrong_epoch_fields_s == (-500, 500)
    assert protocol.candidate_population.fields_s == (-500, 0, 500)
    assert protocol.models.radio_only_polynomial_degrees == (1, 2, 3)
    assert protocol.models.primary_receiver_rate_sigma_hz_s == 0.0
    assert protocol.models.diagnostic_rate_may_change_identity is False
    assert protocol.claim_boundary.secure_norad_permitted is False
    assert protocol.claim_boundary.positioning_validation_permitted is False
    assert protocol.execution.execution_authorized is False
    assert protocol.execution.status == "frozen-not-executed"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    (
        (("time_treatment", "sensitivity_upper_s"), 6.0, "time-treatment"),
        (("time_treatment", "wrong_epoch_policy"), "hard-gate", "observe-only"),
        (("observer", "latitude_deg"), 37.9, "reviewed site"),
        (("candidate_population", "minimum_elevation_deg"), 5.0, "horizon"),
        (("candidate_population", "fields_s"), [-500, 500], "Field required"),
        (("split_and_scoring", "calendar_block_duration_s"), 2.0, "split"),
        (("models", "observation_sigma_hz"), 75.0, "hierarchy"),
        (("models", "diagnostic_rate_may_change_identity"), True, "False"),
        (("claim_boundary", "secure_norad_permitted"), True, "False"),
        (("execution", "execution_authorized"), True, "False"),
    ),
)
def test_protocol_semantics_cannot_be_resealed(
    path: tuple[str, str], value: object, message: str
) -> None:
    document = _document()
    section = document[path[0]]
    assert isinstance(section, dict)
    section[path[1]] = value

    with pytest.raises(ValidationError, match=message):
        SatellitePntLongArcProtocolV1.model_validate(_reseal(document))


def test_loader_rejects_registry_or_evidence_substitution(tmp_path: Path) -> None:
    document = _document()
    registry = document["registry"]
    assert isinstance(registry, dict)
    registry["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="file binding digest"):
        load_satellite_pnt_long_arc_protocol(
            _write(tmp_path, _reseal(document)), repository_root=ROOT
        )

    document = _document()
    observations = document["observations"]
    assert isinstance(observations, list)
    first = observations[0]
    assert isinstance(first, dict)
    evidence = first["cfo_evidence"]
    assert isinstance(evidence, dict)
    evidence["path"] = (
        "reports/figures/2026_08_25_counter_continuous_frame_timing/epoch-doppler-curvature.json"
    )
    evidence["sha256"] = "sha256:24bf59d774c2ca20dd896dd090fdafe146abca5218c54f161c1e07c3ac203f7d"
    with pytest.raises(ValueError, match="absent from arc registry"):
        load_satellite_pnt_long_arc_protocol(
            _write(tmp_path, _reseal(document)), repository_root=ROOT
        )


def test_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    payload = PROTOCOL.read_text(encoding="utf-8")
    poisoned = payload.replace(
        '"protocol_id": "satellite-pnt-long-arc-development-v1",',
        '"protocol_id": "satellite-pnt-long-arc-development-v1",\n'
        '  "protocol_id": "satellite-pnt-long-arc-development-v1",',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(poisoned, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_satellite_pnt_long_arc_protocol(path, repository_root=ROOT)


def test_protocol_loader_has_no_iq_storage_or_propagation_path() -> None:
    source = inspect.getsource(protocol_module)
    assert "leo.storage" not in source
    assert "leo.infrastructure" not in source
    assert "propagate_grid" not in source
    assert "read_iq" not in source
    assert "/mnt/qnap01" not in source
