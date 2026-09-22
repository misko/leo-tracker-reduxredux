import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe

PATH = Path(__file__).parents[2] / "tools/research/export_position_glrt_alternatives.py"
SPEC = importlib.util.spec_from_file_location("export_position_glrt_alternatives", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def candidate(rank, cfo, passed=True):
    return TrackingCandidate(rank, 0, 0.0, cfo, 0.5 - rank / 10, 0.1, 0.4 - rank / 10, passed)


def fixture():
    probe = TrackingProbe(
        1,
        0,
        2,
        20,
        3,
        "lower",
        MODULE.CANONICAL_RF_HZ,
        100,
        200,
        (
            candidate(0, 12.0),
            candidate(1, -9.0, False),
            replace(candidate(2, 12.005), fractional_epoch_offset_samples=0.005),
        ),
    )
    source = TrackingInput(
        "scan",
        "adaptive",
        2_500_000,
        "radio",
        "generation",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        "sha256:" + "c" * 64,
        None,
        True,
        (probe,),
    )
    group = MODULE.source_group_id(source, probe)
    shard = {
        "schema": "position-research-rf-shard-v1",
        "session": {
            "session_id": "scan",
            "input_manifest_sha256": source.input_manifest_sha256,
            "analysis_manifest_sha256": source.analysis_manifest_sha256,
            "raw_recording_authority_digest": source.raw_recording_authority_digest,
        },
        "accounting": {
            "saved_probe_count": 1,
            "saved_fractional_candidate_count": 3,
            "margin_passing_candidate_count": 2,
            "exported_observation_count": 1,
        },
        "tracks": [
            {
                "observations": [
                    {
                        "source_group_id": group,
                        "fractional_candidate_rank": 0,
                        "fractional_exact_score": 0.5,
                        "fractional_control_score": 0.1,
                        "fractional_margin": 0.4,
                        "measured_cfo_hz": 12.0,
                        "source_sample_start": 10,
                        "source_sample_end": 20,
                        "support_start_utc_ns": 100,
                        "support_center_utc_ns": 110,
                        "support_end_utc_ns": 120,
                    }
                ]
            }
        ],
    }
    return source, shard


def projector(source):
    group = MODULE.source_group_id(source, source.probes[0])
    return [
        SimpleNamespace(
            source_group_id=group,
            candidate_rank=0,
            measured_cfo_hz=12.0,
            source_sample_start=10,
            source_sample_end=20,
            support_start_utc_ns=100,
            support_center_utc_ns=110,
            support_end_utc_ns=120,
        )
    ]


def test_exports_all_saved_alternatives_for_selected_group():
    source, shard = fixture()
    result = MODULE.export_session(source, shard, projector=projector)
    assert result["selected_source_group_count"] == 1
    assert result["selected_group_fractional_candidate_count"] == 3
    assert result["selected_group_passing_candidate_count"] == 2
    assert [row["candidate_rank"] for row in result["groups"][0]["candidates"]] == [0, 1, 2]
    assert result["alternative_diagnostics"]["duplicate_passing_candidate_count"] == 1


def test_rejects_authority_or_selected_candidate_drift():
    source, shard = fixture()
    with pytest.raises(ValueError, match="authority differ"):
        MODULE.export_session(
            replace(source, analysis_manifest_sha256="sha256:" + "d" * 64),
            shard,
            projector=projector,
        )
    shard["tracks"][0]["observations"][0]["fractional_exact_score"] = 0.4
    with pytest.raises(ValueError, match="differs from"):
        MODULE.export_session(source, shard, projector=projector)
