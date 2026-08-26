from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
OUTPUT = ROOT / "reports" / "figures" / "2026_08_25_v3_v4_downstream_rate"
REPORT = ROOT / "reports" / "2026_08_25_v3_v4_downstream_rate_benchmark.md"


def _tool():
    path = ROOT / "tools" / "benchmark_v3_v4_downstream_rate.py"
    name = "benchmark_v3_v4_downstream_rate_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _row(*, v3: str, v4: str, alignment: bool, accepted: bool) -> dict[str, object]:
    return {
        "row_key": f"sha256:{'1' * 64}",
        "v3": {
            "status": v3,
            "initial_alignment": (
                {
                    "status": "complete",
                    "epoch_sample": 20,
                    "absolute_cfo_hz": 1_000.0,
                }
                if alignment
                else {"status": "no_result"}
            ),
        },
        "v4": {
            "numerical_status": v4,
            "component_inventory": (
                [
                    {
                        "accepted": True,
                        "rank": 2,
                        "candidate_id": "b",
                        "epoch_sample": 21,
                        "absolute_cfo_hz": 1_100.0,
                        "tracking_status": "complete",
                    },
                    {
                        "accepted": True,
                        "rank": 1,
                        "candidate_id": "a",
                        "epoch_sample": 22,
                        "absolute_cfo_hz": 1_200.0,
                        "tracking_status": "complete",
                    },
                ]
                if accepted
                else []
            ),
        },
    }


def test_yield_keeps_acquisition_and_numerical_completion_separate() -> None:
    tool = _tool()
    rows = {
        0: _row(v3="complete", v4="no_result", alignment=True, accepted=False),
        1: _row(v3="no_result", v4="complete", alignment=False, accepted=True),
    }

    summary = tool._yield_summary(rows)

    assert summary["v3_alignment_complete_count"] == 1
    assert summary["v4_accepted_mode_count"] == 1
    assert summary["v3_numerical_complete_count"] == 1
    assert summary["v4_numerical_complete_count"] == 1
    assert len(summary["row_ledger"]) == 2


def test_v4_coordinate_is_frozen_to_lowest_rank_accepted_mode() -> None:
    tool = _tool()
    row = _row(v3="complete", v4="complete", alignment=True, accepted=True)

    coordinate = tool._v4_coordinate(row)

    assert coordinate is not None
    assert coordinate.epoch_sample == 22
    assert coordinate.absolute_cfo_hz == 1_200.0


def test_output_root_rejects_capture_and_qnap_paths(tmp_path: Path) -> None:
    tool = _tool()
    capture = tmp_path / "capture"
    capture.mkdir()

    with pytest.raises(ValueError, match="cannot be written"):
        tool._validate_output_root(capture / "result", capture)
    with pytest.raises(ValueError, match="cannot be written"):
        tool._validate_output_root(Path("/mnt/qnap01/research-result"), capture)


def test_committed_evidence_manifest_and_common_masks_are_self_consistent() -> None:
    manifest = json.loads((OUTPUT / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "org.leo.research.v3-v4-downstream-rate-artifacts/v1"
    for name, binding in manifest["artifacts"].items():
        path = OUTPUT / name
        assert path.stat().st_size == binding["bytes"]
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]

    result = json.loads((OUTPUT / "benchmark-results.json").read_text(encoding="utf-8"))
    assert result["schema"] == "org.leo.research.v3-v4-downstream-rate-benchmark/v1"
    assert result["capture"] == {
        "opened_canary_not_holdout": True,
        "post_refill_fix": True,
        "recording_manifest_sha256": (
            "sha256:ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e"
        ),
        "session_id": "cap-20260825T150802-473cb5bbcbd6",
    }
    assert result["yield"]["population_row_count"] == 537
    assert len(result["yield"]["row_ledger"]) == 537
    assert len(result["downstream"]["anchor_ledger"]) == 20
    assert result["interpretation"]["standard_promotion"] is False
    assert result["interpretation"]["common_fixed_500_point_ratio_within_bound"] is True
    assert result["interpretation"]["common_fixed_500_noninferiority_established"] is False

    prediction_bytes = (OUTPUT / "predictions.csv").read_bytes()
    assert b"\r\n" not in prediction_bytes
    with (OUTPUT / "predictions.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    common: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["population"] == "both_method_common_mode":
            common.setdefault(row["pair_id"], []).append(row)
    assert common
    for pair in common.values():
        assert {row["method"] for row in pair} == {"v3_alignment", "v4_acquisition"}
        assert len({row["training_frame_count"] for row in pair}) == 1
        assert len({row["training_first_ordinal"] for row in pair}) == 1
        assert len({row["training_last_ordinal"] for row in pair}) == 1

    with gzip.open(OUTPUT / "frame-inventory.json.gz", "rt", encoding="utf-8") as source:
        inventory = json.load(source)
    assert inventory["schema"] == "org.leo.research.v3-v4-split-frame-inventory/v1"
    assert len(inventory["frames"]) == result["downstream"]["frame_inventory_count"]

    report = REPORT.read_text(encoding="utf-8")
    assert "Only **3 of the 20**" in report
    assert "figures/2026_08_25_v3_v4_downstream_rate/acquisition-yield.png" in report
    assert "figures/2026_08_25_v3_v4_downstream_rate/paired-future-odd-prediction.png" in report
    assert "figures/2026_08_25_v3_v4_downstream_rate/anchor-residuals.png" in report
