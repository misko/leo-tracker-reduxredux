from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.polynomial_injection_protocol import (
    load_polynomial_injection_protocol,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame, template_sha256

PROJECT_ROOT = Path(__file__).parents[2]
DATASET_POLICY_PATH = PROJECT_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
PROTOCOL_PATH = PROJECT_ROOT / "config/analysis/polynomial-phase-injection-protocol-v1.json"


def _load(path: Path = PROTOCOL_PATH):
    policy = load_doppler_dataset_policy(DATASET_POLICY_PATH)
    return load_polynomial_injection_protocol(
        path,
        dataset_policy=policy,
        repository_root=PROJECT_ROOT,
    )


def _document() -> dict[str, Any]:
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_committed_protocol_freezes_exact_authorized_spans_and_design() -> None:
    protocol = _load()

    assert protocol.basis_repository_commit == "2e17b4477b38494e14bab7ff39303cf3a219bb03"
    assert [item.session_id for item in protocol.backgrounds] == [
        "cap-20260825T062228-886fe2dd9cde",
        "cap-20260825T105640-facdadeffb3b",
        "cap-20260825T111222-a2d4ce2afb9a",
    ]
    assert [
        (item.sample_start, item.sample_count, item.chunk.chunk_index)
        for item in protocol.backgrounds
    ] == [
        (20_000_000, 5_000_000, 1),
        (55_000_000, 5_000_000, 3),
        (90_000_000, 5_000_000, 5),
    ]
    assert all(item.stream_id == "stream-0" for item in protocol.backgrounds)
    assert all(item.radio_id == "radio_pluto_5d4d" for item in protocol.backgrounds)
    assert all(item.receiver_id == 1 for item in protocol.backgrounds)
    assert len(protocol.scenarios) == 18
    assert Counter(item.background_session_id for item in protocol.scenarios) == {
        item.session_id: 6 for item in protocol.backgrounds
    }
    assert tuple(item.name for item in protocol.histories) == (
        "causal_20ms_linear",
        "fixed_125ms_linear",
        "fixed_500ms_linear",
    )


def test_exact_qin_template_digest_and_lattice_placement_are_frozen() -> None:
    template = qin_edge_pilot_frame(2_500_000, "lower")
    assert template.dtype == "complex64"
    assert template.size == 3_333
    assert template_sha256(template) == (
        "15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"
    )

    starts = [round(index * 10_000 / 3) for index in range(1_500)]
    assert set(right - left for left, right in zip(starts, starts[1:], strict=False)) == {
        3_333,
        3_334,
    }
    assert all(
        left + template.size <= right for left, right in zip(starts, starts[1:], strict=False)
    )
    assert starts[-1] + template.size <= 5_000_000


def test_even_odd_and_rolled_control_roles_are_response_separated() -> None:
    estimator = _document()["estimator_model"]
    assert isinstance(estimator, dict)
    assert estimator["odd_qin_may_influence_training"] is False
    assert estimator["even_rolled_control_is_training_gate"] is True
    assert estimator["odd_rolled_control_may_influence_training"] is False
    assert "even-trained odd-held-out" in str(estimator["frame_cfo_method"])


def test_protocol_backgrounds_are_disjoint_from_holdout() -> None:
    policy = load_doppler_dataset_policy(DATASET_POLICY_PATH)
    protocol = _load()
    assert not (
        {item.session_id for item in protocol.backgrounds}
        & set(policy.role("holdout_foundation").capture_ids)
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("dynamic_discovery", "must be true"),
        ("policy_digest", "policy bytes"),
        ("unlisted_capture", "not authorized"),
        ("span_crosses_chunk", "wholly inside"),
        ("duplicate_seed", "seeds must be unique"),
        ("unbalanced_rate", "rate factor"),
        ("wrong_history", "history estimators"),
        ("iq_opened", "IQ remained closed"),
    ],
)
def test_protocol_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    document = copy.deepcopy(_document())
    authority = document["input_authority"]
    backgrounds = document["backgrounds"]
    selection = document["span_selection"]
    estimator = document["estimator_model"]
    design = document["balanced_design"]
    assert isinstance(authority, dict)
    assert isinstance(backgrounds, list)
    assert isinstance(selection, dict)
    assert isinstance(estimator, dict)
    assert isinstance(design, dict)
    scenarios = design["scenarios"]
    assert isinstance(scenarios, list)

    if mutation == "dynamic_discovery":
        authority["dynamic_discovery_forbidden"] = False
    elif mutation == "policy_digest":
        authority["dataset_policy_sha256"] = f"sha256:{'0' * 64}"
    elif mutation == "unlisted_capture":
        assert isinstance(backgrounds[0], dict)
        backgrounds[0]["session_id"] = "cap-20260825T150802-473cb5bbcbd6"
    elif mutation == "span_crosses_chunk":
        assert isinstance(backgrounds[0], dict)
        backgrounds[0]["sample_start"] = 30_000_000
    elif mutation == "duplicate_seed":
        assert isinstance(scenarios[0], dict) and isinstance(scenarios[1], dict)
        scenarios[1]["seed"] = scenarios[0]["seed"]
    elif mutation == "unbalanced_rate":
        assert isinstance(scenarios[0], dict)
        scenarios[0]["rate_hz_s"] = 3_500.0
    elif mutation == "wrong_history":
        histories = estimator["history_estimators"]
        assert isinstance(histories, list) and isinstance(histories[0], dict)
        histories[0]["name"] = "retrospective_20ms"
    elif mutation == "iq_opened":
        selection["raw_iq_opened_before_freeze"] = True
    else:  # pragma: no cover - parameter table is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(ValueError, match=message):
        _load(_write(tmp_path, document))


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    source = PROTOCOL_PATH.read_text(encoding="utf-8")
    malformed = source.replace(
        '"protocol_status": "frozen_before_scoring",',
        '"protocol_status": "frozen_before_scoring",\n  "protocol_status": "changed",',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(malformed, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _load(path)
