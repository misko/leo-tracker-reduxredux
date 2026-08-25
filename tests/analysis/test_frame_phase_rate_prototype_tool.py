from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.frame_phase_rate import (
    FramePhaseRateFrame,
    FramePhaseRateObservation,
    FramePhaseRateResult,
)
from leo.analysis.starlink import NumericalStatus
from tools import report_frame_phase_rate_prototype as report


def _observation(
    frame_index: int,
    reference_sample: float,
    *,
    continuity_segment: int = 0,
    training_supported: bool = True,
) -> FramePhaseRateObservation:
    return FramePhaseRateObservation(
        frame_index=frame_index,
        frame_start_sample=100 + frame_index,
        reference_sample=reference_sample,
        continuity_segment=continuity_segment,
        training_supported=training_supported,
        even_absolute_cfo_hz=1_000.0 + frame_index,
        even_frequency_uncertainty_hz=5.0,
        even_exact_coherence=0.8,
        even_control_coherence=0.02,
        even_channel_vector=np.ones(8, dtype=np.complex128),
        odd_absolute_cfo_hz=1_002.0 + frame_index,
        odd_channel_vector=np.ones(8, dtype=np.complex128),
    )


def _result(
    *,
    status: NumericalStatus = NumericalStatus.COMPLETE,
    frame_count: int = 2,
    validation_frame_count: int = 2,
    odd_cfo_rms_hz: float | None = 5.0,
    phase_candidate_odd_cfo_rms_hz: float | None = 1.0,
    phase_arc_qualified: bool = True,
    phase_feedback_qualified: bool = True,
    relative_timing_rate_samples_s: float | None = 1.25,
    frames: tuple[FramePhaseRateFrame, ...] = (),
) -> FramePhaseRateResult:
    return FramePhaseRateResult(
        status=status,
        reason="test result",
        frame_count=frame_count,
        validation_frame_count=validation_frame_count,
        reference_time_s=0.0,
        frequency_only_cfo_hz=1_000.0,
        frequency_only_doppler_rate_hz_s=-100.0,
        frequency_only_rate_sigma_hz_s=2.0,
        phase_candidate_cfo_hz=1_000.5,
        phase_candidate_doppler_rate_hz_s=-99.0,
        relative_timing_samples=0.1,
        relative_timing_rate_samples_s=relative_timing_rate_samples_s,
        relative_timing_boundary_fraction=0.0,
        iteration_count=2,
        converged=True,
        training_phase_rms_rad=0.05,
        odd_cfo_rms_hz=odd_cfo_rms_hz,
        phase_candidate_odd_cfo_rms_hz=phase_candidate_odd_cfo_rms_hz,
        odd_phase_rms_rad=0.04,
        odd_stack_efficiency=0.98,
        odd_validation_valid=True,
        odd_validation_reason="test validation is finite and paired",
        phase_arc_qualified=phase_arc_qualified,
        phase_arc_reason="held-out phase-arc test result",
        phase_feedback_qualified=phase_feedback_qualified,
        phase_feedback_reason="held-out test result",
        frames=frames,
    )


def test_partition_locklets_is_order_independent_and_splits_gaps_and_continuity() -> None:
    observations = (
        _observation(5, 31.0, continuity_segment=1),
        _observation(3, 20.0),
        _observation(1, 5.0, training_supported=False),
        _observation(4, 21.0, continuity_segment=1),
        _observation(2, 9.0),
        _observation(0, 0.0),
    )

    forward = report._partition_locklets(
        observations,
        sample_rate_hz=1_000.0,
        maximum_gap_s=0.010,
    )
    reverse = report._partition_locklets(
        tuple(reversed(observations)),
        sample_rate_hz=1_000.0,
        maximum_gap_s=0.010,
    )

    assert [[item.frame_index for item in locklet] for locklet in forward] == [
        [0, 2],
        [3],
        [4, 5],
    ]
    assert [[item.frame_index for item in locklet] for locklet in reverse] == [
        [0, 2],
        [3],
        [4, 5],
    ]
    assert all(item.training_supported for locklet in forward for item in locklet)


def test_robust_center_resists_one_large_baseline_outlier_and_is_translation_equivariant() -> None:
    values = np.asarray([10.0, 11.0, 12.0, 1_000.0])
    weights = np.ones(4)

    center = report._robust_center(values, weights)
    translated = report._robust_center(values + 250.0, weights)

    assert 12.0 < center < 20.0
    assert center < float(np.average(values, weights=weights)) / 10.0
    assert translated == pytest.approx(center + 250.0, abs=1e-9)


def test_result_document_serializes_numerical_status_as_contract_string() -> None:
    result = _result(status=NumericalStatus.INSUFFICIENT, phase_feedback_qualified=False)

    document = report._result_document(result)
    round_tripped = json.loads(report._json_bytes(document))

    assert document["status"] == "insufficient"
    assert round_tripped["status"] == "insufficient"
    assert round_tripped["odd_symbols_influenced_fit"] is False
    assert round_tripped["primary_rate_source"] == "independent even-Qin frame CFO"


def _summary_result(
    *,
    validation_frame_count: int,
    odd_cfo_rms_hz: float,
    phase_candidate_odd_cfo_rms_hz: float,
    phase_arc_qualified: bool = True,
    phase_feedback_qualified: bool,
    relative_timing_rate_samples_s: float | None = None,
) -> dict[str, object]:
    return {
        "status": "complete",
        "validation_frame_count": validation_frame_count,
        "odd_cfo_rms_hz": odd_cfo_rms_hz,
        "phase_candidate_odd_cfo_rms_hz": phase_candidate_odd_cfo_rms_hz,
        "phase_arc_qualified": phase_arc_qualified,
        "phase_feedback_qualified": phase_feedback_qualified,
        "relative_timing_rate_samples_s": relative_timing_rate_samples_s,
    }


def test_dwell_summary_promotes_candidate_only_after_odd_heldout_qualification() -> None:
    locklets = [
        {
            "frame_count": 8,
            "glrt_recentered_odd_cfo_rms_hz": 50.0,
            "phase_timing_fixed": _summary_result(
                validation_frame_count=4,
                odd_cfo_rms_hz=20.0,
                phase_candidate_odd_cfo_rms_hz=2.0,
                phase_feedback_qualified=False,
            ),
            "phase_timing_iterative": _summary_result(
                validation_frame_count=4,
                odd_cfo_rms_hz=10.0,
                phase_candidate_odd_cfo_rms_hz=1.0,
                phase_feedback_qualified=True,
                relative_timing_rate_samples_s=-2.0,
            ),
        },
        {
            "frame_count": 20,
            "glrt_recentered_odd_cfo_rms_hz": 70.0,
            "phase_timing_fixed": _summary_result(
                validation_frame_count=12,
                odd_cfo_rms_hz=40.0,
                phase_candidate_odd_cfo_rms_hz=4.0,
                phase_feedback_qualified=True,
            ),
            "phase_timing_iterative": _summary_result(
                validation_frame_count=12,
                odd_cfo_rms_hz=30.0,
                phase_candidate_odd_cfo_rms_hz=0.0,
                phase_feedback_qualified=False,
                relative_timing_rate_samples_s=6.0,
            ),
        },
        {
            "frame_count": 999,
            "glrt_recentered_odd_cfo_rms_hz": 10_000.0,
            "phase_timing_fixed": {"phase_feedback_qualified": True},
            "phase_timing_iterative": {"status": "insufficient"},
        },
    ]

    summary = report._summarize_dwell("T01", "explore", locklets)

    assert summary["locklet_count"] == 3
    assert summary["complete_locklet_count"] == 2
    assert summary["eligible_frame_count"] == 28
    assert summary["timing_fixed_phase_arc_qualified_locklet_count"] == 2
    assert summary["timing_fixed_phase_feedback_candidate_locklet_count"] == 1
    assert summary["iterative_timing_phase_arc_qualified_locklet_count"] == 2
    assert summary["iterative_timing_phase_feedback_candidate_locklet_count"] == 1
    assert summary["glrt_recentered_odd_cfo_rms_hz"] == pytest.approx(math.sqrt(4_300.0))
    assert summary["frequency_only_odd_cfo_rms_hz"] == pytest.approx(math.sqrt(700.0))
    assert summary["timing_fixed_fit_withheld_selected_odd_cfo_rms_hz"] == pytest.approx(
        math.sqrt(112.0)
    )
    assert summary["iterative_timing_fit_withheld_selected_odd_cfo_rms_hz"] == pytest.approx(
        math.sqrt(675.25)
    )
    assert summary["all_complete_candidate_relative_timing_rate_median_samples_s"] == 2.0
    assert summary["all_complete_candidate_relative_timing_rate_p95_abs_samples_s"] == (
        pytest.approx(5.8)
    )


@pytest.mark.parametrize(
    ("phase", "labels", "maximum_regions", "message"),
    (
        ("future", None, 1, "phase selection is unsupported"),
        ("all", None, 0, "maximum regions must lie"),
        ("all", None, 7, "maximum regions must lie"),
        ("all", ("T01", "T01"), 1, "dwell labels must be unique"),
    ),
)
def test_run_report_rejects_invalid_selection_before_reading_inputs(
    tmp_path: Path,
    phase: str,
    labels: tuple[str, ...] | None,
    maximum_regions: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        report.run_report(
            bulk_root=tmp_path / "missing-bulk",
            frame_cfo_root=tmp_path / "missing-inputs",
            output_root=tmp_path / "output",
            phase=phase,
            labels=labels,
            maximum_regions=maximum_regions,
        )


def test_run_report_rejects_unsupported_input_version_before_opening_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    (input_root / "summary.json").write_text(
        json.dumps({"schema": "org.leo.research.frame-cfo-prototype/v2"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        report.RecordingStore,
        "open_pinned",
        lambda _root: pytest.fail("store must not open for an unsupported input version"),
    )

    with pytest.raises(ValueError, match="unsupported frame-CFO prototype summary"):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=input_root,
            output_root=tmp_path / "output",
            phase="all",
            labels=None,
            maximum_regions=1,
        )


def _write_minimal_inputs(input_root: Path) -> None:
    input_root.mkdir()
    summary = {
        "schema": "org.leo.research.frame-cfo-prototype/v1",
        "dwells": [
            {
                "label": "T01",
                "phase": "explore",
                "evaluation_trajectory_id": "trajectory-1",
                "hypotheses": [
                    {
                        "trajectory_id": "trajectory-1",
                        "alias_index": 0,
                    }
                ],
                "session_id": "session-1",
                "stream_id": "stream-1",
                "receiver_id": 7,
                "edge": "lower",
                "recording_manifest_digest": "recording-sha256",
                "regions": [
                    {
                        "region_id": "region-1",
                        "role": "middle_median_margin",
                        "probe": {
                            "probe_index": 0,
                            "canonical_observation_id": "canonical-1",
                            "source_observation_id": "source-1",
                            "detection_time_s": 0.0,
                            "detection_sample_start": 100,
                            "local_epoch_sample": 0,
                            "raw_source_cfo_hz": 990.0,
                            "observation_alias_index": 0,
                            "exact_score": 0.8,
                            "control_score": 0.02,
                            "margin": 0.78,
                        },
                        "sample_start": 100,
                        "sample_count": 4,
                        "strong_glrt_region": True,
                        "refill_boundary_sample": None,
                    }
                ],
            }
        ],
    }
    (input_root / "summary.json").write_text(
        json.dumps(summary, sort_keys=True),
        encoding="utf-8",
    )
    rows = [
        {
            "schema": "org.leo.research.frame-cfo-prototype-row/v1",
            "dwell_label": "T01",
            "phase": "explore",
            "trajectory_id": "trajectory-1",
            "region_id": "region-1",
            "frame_start_sample": 100 + index,
            "source_bound_seed_hz": 990.0,
            "trajectory_model_cfo_hz": 990.0 + index,
            "split_validation": {
                "status": "complete",
                "training_supported": True,
                "even_absolute_cfo_hz": 1_000.0 + index,
                "even_coherence_margin": 0.5,
            },
        }
        for index in range(2)
    ]
    with gzip.open(input_root / "frame-cfo-rows.jsonl.gz", "wt", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, sort_keys=True) + "\n")
    _seal_inputs(input_root)


def _seal_inputs(input_root: Path) -> None:
    summary_path = input_root / "summary.json"
    rows_path = input_root / "frame-cfo-rows.jsonl.gz"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["artifacts"] = {rows_path.name: report._sha256(rows_path)}
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    manifest = {
        "schema": "org.leo.research.frame-cfo-prototype-artifacts/v1",
        "artifacts": {
            summary_path.name: report._sha256(summary_path),
            rows_path.name: report._sha256(rows_path),
        },
    }
    (input_root / "artifact-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )


def test_run_report_rejects_partly_missing_requested_labels_before_opening_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "inputs"
    _write_minimal_inputs(input_root)
    monkeypatch.setattr(
        report.RecordingStore,
        "open_pinned",
        lambda _root: pytest.fail("store must not open for an incomplete selection"),
    )

    with pytest.raises(ValueError, match="requested dwell label is absent"):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=input_root,
            output_root=tmp_path / "output",
            phase="all",
            labels=("T01", "T99"),
            maximum_regions=1,
        )


def test_subset_run_cannot_overwrite_canonical_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / "canonical"
    monkeypatch.setattr(report, "DEFAULT_OUTPUT_ROOT", canonical)

    with pytest.raises(ValueError, match="subset run requires an explicit noncanonical"):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=tmp_path / "inputs",
            output_root=canonical,
            phase="explore",
            labels=None,
            maximum_regions=1,
        )


def test_output_root_cannot_overwrite_frame_cfo_inputs(tmp_path: Path) -> None:
    shared = tmp_path / "shared"

    with pytest.raises(ValueError, match="output root must differ"):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=shared,
            output_root=shared,
            phase="all",
            labels=None,
            maximum_regions=6,
        )


def test_input_artifact_digest_mismatch_fails_before_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "inputs"
    _write_minimal_inputs(input_root)
    with gzip.open(input_root / "frame-cfo-rows.jsonl.gz", "at", encoding="utf-8") as target:
        target.write("{}\n")
    monkeypatch.setattr(
        report.RecordingStore,
        "open_pinned",
        lambda _root: pytest.fail("store must not open for an unsealed input artifact"),
    )

    with pytest.raises(ValueError, match="rows disagree with their artifact manifest"):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=input_root,
            output_root=tmp_path / "output",
            phase="all",
            labels=None,
            maximum_regions=1,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda row: row.pop("schema"), "unsupported frame-CFO prototype row"),
        (
            lambda row: row.__setitem__("phase", "confirm"),
            "row phase disagrees with its dwell inventory",
        ),
    ),
)
def test_run_report_rejects_unknown_or_misbound_rows_before_opening_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: object,
    message: str,
) -> None:
    input_root = tmp_path / "inputs"
    _write_minimal_inputs(input_root)
    rows_path = input_root / "frame-cfo-rows.jsonl.gz"
    with gzip.open(rows_path, "rt", encoding="utf-8") as source:
        rows = [json.loads(line) for line in source]
    mutation(rows[0])
    with gzip.open(rows_path, "wt", encoding="utf-8") as target:
        for row in rows:
            target.write(json.dumps(row, sort_keys=True) + "\n")
    _seal_inputs(input_root)
    monkeypatch.setattr(
        report.RecordingStore,
        "open_pinned",
        lambda _root: pytest.fail("store must not open for malformed persisted rows"),
    )

    with pytest.raises(ValueError, match=message):
        report.run_report(
            bulk_root=tmp_path / "bulk",
            frame_cfo_root=input_root,
            output_root=tmp_path / "output",
            phase="all",
            labels=None,
            maximum_regions=1,
        )


def test_alias_selection_uses_even_qin_only() -> None:
    dwell = {
        "label": "T01",
        "regions": [{"region_id": "region-1"}],
        "hypotheses": [
            {"trajectory_id": "odd-favored", "alias_index": 0},
            {"trajectory_id": "even-favored", "alias_index": 1},
        ],
    }
    rows = {}
    for trajectory_id, even_supported, odd_favored in (
        ("odd-favored", False, True),
        ("even-favored", True, False),
    ):
        rows[("T01", trajectory_id, "region-1", 100)] = {
            "split_validation": {
                "status": "complete",
                "training_supported": even_supported,
                "even_coherence_margin": 0.4 if even_supported else 0.0,
                "odd_absolute_cfo_hz": 9_999.0 if odd_favored else -9_999.0,
            },
            "primary": {"measurement_supported": odd_favored},
        }

    assert report._even_only_trajectory_id(dwell, rows) == "even-favored"


def test_mocked_report_is_policy_truthful_and_byte_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "inputs"
    bulk_root = tmp_path / "bulk"
    _write_minimal_inputs(input_root)
    bulk_root.mkdir()
    stores: list[object] = []

    class FakeReader:
        sample_rate_hz = 750.0

        def iter_timeline_metadata(self) -> tuple[object, ...]:
            return ()

        def read(
            self,
            sample_start: int,
            sample_count: int,
            *,
            receiver_ids: tuple[int, ...],
        ) -> np.ndarray:
            assert (sample_start, sample_count, receiver_ids) == (99, 6, (7,))
            return np.zeros((sample_count, 1, 2), dtype=np.int16)

    class FakeStore:
        def __init__(self) -> None:
            self.closed = False

        def inspect(self, session_id: str) -> object:
            assert session_id == "session-1"
            return SimpleNamespace(manifest_sha256="recording-sha256")

        def reader(self, _bundle: object, stream_id: str, *, verify: bool) -> FakeReader:
            assert stream_id == "stream-1"
            assert verify is True
            return FakeReader()

        def close(self) -> None:
            self.closed = True

    def open_pinned(_root: object) -> FakeStore:
        store = FakeStore()
        stores.append(store)
        return store

    opportunities = tuple(
        SimpleNamespace(
            frame_index=index,
            frame_start_sample=100 + index,
            local_frame_start=index,
            continuity_segment=0,
            crosses_refill_boundary=False,
        )
        for index in range(2)
    )

    def frame_opportunities(
        _region: object,
        *,
        sample_rate_hz: float,
        refill_boundaries: tuple[int, ...],
    ) -> tuple[object, ...]:
        assert sample_rate_hz == 750.0
        assert refill_boundaries == ()
        return opportunities

    def estimate_complex(
        _samples: np.ndarray,
        _sample_rate_hz: float,
        *,
        frame_start_sample: int,
        acquisition_absolute_cfo_hz: float,
        edge: object,
    ) -> object:
        assert acquisition_absolute_cfo_hz == 990.0
        assert str(edge) == "lower"
        index = frame_start_sample - 100
        even = SimpleNamespace(
            absolute_cfo_hz=1_000.0 + index,
            frequency_uncertainty_hz=5.0,
            exact_coherence=0.8,
            control_coherence=0.02,
            channel_vector=np.ones(8, dtype=np.complex128),
        )
        odd = SimpleNamespace(
            absolute_cfo_hz=1_002.0 + index,
            channel_vector=np.ones(8, dtype=np.complex128),
        )
        return SimpleNamespace(
            reference_sample=frame_start_sample + 0.25,
            training_supported=True,
            even=even,
            odd=odd,
        )

    def fit_phase_rate(
        observations: tuple[FramePhaseRateObservation, ...],
        *,
        sample_rate_hz: float,
        epoch_sample: int,
        edge: object,
        config: object,
    ) -> FramePhaseRateResult:
        assert sample_rate_hz == 750.0
        assert epoch_sample == 100
        assert str(edge) == "lower"
        frames = tuple(
            FramePhaseRateFrame(
                frame_index=item.frame_index,
                frame_start_sample=item.frame_start_sample,
                reference_sample=item.reference_sample,
                rounded_minus_ideal_samples=0.0,
                predicted_frequency_hz=item.even_absolute_cfo_hz,
                even_frequency_innovation_hz=0.0,
                relative_timing_samples=0.0,
                phase_ambiguity_bit=0,
                training_phase_residual_modulo_pi_rad=0.01,
                channel_similarity=0.99,
                odd_frequency_error_hz=2.0,
                phase_candidate_odd_frequency_error_hz=1.0,
                odd_phase_residual_rad=0.01,
            )
            for item in observations
        )
        timing_enabled = bool(config.enable_relative_timing)
        return _result(
            frame_count=len(observations),
            validation_frame_count=len(observations),
            phase_feedback_qualified=timing_enabled,
            relative_timing_rate_samples_s=1.25 if timing_enabled else None,
            frames=frames,
        )

    def plot(path: Path, dwells: list[dict[str, object]]) -> None:
        assert len(dwells) == 1
        path.write_bytes(b"deterministic frame-phase-rate test figure\n")

    monkeypatch.setattr(report.RecordingStore, "open_pinned", open_pinned)
    monkeypatch.setattr(report, "frame_opportunities", frame_opportunities)
    monkeypatch.setattr(report, "estimate_edge_pilot_frame_complex_split", estimate_complex)
    monkeypatch.setattr(report, "fit_iterative_frame_phase_rate", fit_phase_rate)
    monkeypatch.setattr(report, "_plot", plot)

    documents = []
    output_roots = (tmp_path / "first", tmp_path / "second")
    for output_root in output_roots:
        documents.append(
            report.run_report(
                bulk_root=bulk_root,
                frame_cfo_root=input_root,
                output_root=output_root,
                phase="all",
                labels=("T01",),
                maximum_regions=1,
            )
        )

    assert all(store.closed for store in stores)
    assert documents[0] == documents[1]
    document = documents[0]
    assert document["selection"]["full_frozen_run"] is False
    assert document["locklet_count"] == 1
    assert document["complete_locklet_count"] == 1
    assert document["phase_arc_qualified_locklet_count"] == 1
    assert document["phase_arc_qualified_fraction"] == 1.0
    assert document["phase_feedback_candidate_locklet_count"] == 1
    assert document["phase_feedback_candidate_fraction"] == 1.0
    assert document["candidate_only"] is True
    assert document["odd_symbols_influenced_fit"] is False
    assert document["odd_symbols_influenced_alias_selection"] is False
    assert document["selection"]["alias_selected_by_even_qin_only_before_odd_validation"] is True
    assert (
        document["selection"]["all_even_only_alias_selections_agree_with_frame_cfo_evaluation"]
        is True
    )
    dwell = document["dwells"][0]
    assert dwell["glrt_recentered_odd_cfo_rms_hz"] == 2.0
    assert dwell["frequency_only_odd_cfo_rms_hz"] == 5.0
    assert dwell["timing_fixed_fit_withheld_selected_odd_cfo_rms_hz"] == 5.0
    assert dwell["iterative_timing_fit_withheld_selected_odd_cfo_rms_hz"] == 1.0

    artifact_names = {
        "artifact-manifest.json",
        "frame-phase-rate-prototype.png",
        "locklets.json",
        "summary.json",
    }
    assert {path.name for path in output_roots[0].iterdir()} == artifact_names
    for name in artifact_names:
        assert (output_roots[0] / name).read_bytes() == (output_roots[1] / name).read_bytes()

    persisted = json.loads((output_roots[0] / "summary.json").read_text(encoding="utf-8"))
    assert persisted == document
    manifest = json.loads((output_roots[0] / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "org.leo.research.frame-phase-rate-artifacts/v1"
    for name, digest in manifest["artifacts"].items():
        assert digest == report._sha256(output_roots[0] / name)
