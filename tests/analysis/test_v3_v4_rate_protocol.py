from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo.analysis.research.v3_v4_rate_protocol import load_v3_v4_rate_protocol

ROOT = Path(__file__).parents[2]
PROTOCOL = ROOT / "config" / "analysis" / "v3-v4-downstream-rate-benchmark-v1.json"


def test_committed_protocol_closes_the_canary_population_and_anchors() -> None:
    protocol = load_v3_v4_rate_protocol(PROTOCOL, repository_root=ROOT)

    assert protocol.document["dataset_policy"]["role"] == "v3_v4_canary"
    assert len(protocol.scientific_receipt["rows"]) == 537
    assert len(protocol.anchors) == 20
    assert len({item.source_branch_id for item in protocol.anchors}) == 20
    assert protocol.document["measurement"]["odd_may_select_mask_or_fit"] is False
    assert protocol.document["forecast"]["fixed_500ms"] == {
        "minimum_frames": 300,
        "minimum_span_ms": 450,
    }


def test_protocol_denies_anchor_substitution(tmp_path: Path) -> None:
    document = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    document["downstream_anchor_selection"]["anchors"][0]["row_index"] = 1
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="first frozen row"):
        load_v3_v4_rate_protocol(path, repository_root=ROOT)


def test_protocol_denies_holdout_role(tmp_path: Path) -> None:
    document = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    document["dataset_policy"]["role"] = "holdout_foundation"
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="exact V3/V4 canary"):
        load_v3_v4_rate_protocol(path, repository_root=ROOT)


def test_protocol_denies_odd_selected_mask(tmp_path: Path) -> None:
    document = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    document["measurement"]["odd_may_select_mask_or_fit"] = True
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="measurement settings"):
        load_v3_v4_rate_protocol(path, repository_root=ROOT)
