from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import zstandard as zstd


def _tool():
    path = Path(__file__).parents[2] / "tools" / "replay_150802_pnt_kalman_v4_canary.py"
    spec = importlib.util.spec_from_file_location("replay_150802_v4_canary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _source_row(*, probe: int, v2: str = "complete", v3: str = "complete") -> dict:
    return {
        "scope": "sha256:" + "1" * 64,
        "source_trajectory_id": "sha256:" + f"{probe + 1:064x}",
        "source_branch_id": "sha256:" + f"{probe + 2:064x}",
        "source_probe_sample_start": probe,
        "segment_index": probe,
        "candidate_rank": 1,
        "stream": "stream-0",
        "receiver": 0,
        "edge": "lower",
        "start_time_s": probe / 100.0,
        "epoch_sample": 7,
        "seed_cfo_hz": 1_250.0 + probe,
        "standard_v1_qualified": False,
        "standard_v1_local_rate_hz_s": None,
        "v2_status": v2,
        "v2_frequency_update_count": 0 if v2 == "no_result" else 12,
        "v2_phase_lock_qualified": False,
        "v3_status": v3,
        "v3_phase_lock_qualified": False,
    }


def _mode_evidence(
    source_seed_index: int = 0,
    *,
    epoch_sample: int = 7,
    absolute_cfo_hz: float = 1_250.0,
    doppler_rate_hz_s: float = 0.0,
    epoch_residuals: tuple[int, ...] = (0, 0, 0, 0),
    cfo_residuals_hz: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0),
    path_sha256: str = "e" * 64,
) -> dict:
    block_epochs = [epoch_sample + value for value in epoch_residuals]
    block_cfos_hz = [absolute_cfo_hz + value for value in cfo_residuals_hz]
    blocks = [
        {
            "block_index": index,
            "start_sample": index,
            "stop_sample": index + 1,
            "first_frame_start_sample": index,
            "projected_epoch_sample": epoch_sample,
            "trajectory_epoch_sample": block_epochs[index],
            "trajectory_epoch_residual_samples": epoch_residuals[index],
            "absolute_cfo_hz": block_cfos_hz[index],
            "trajectory_cfo_residual_hz": cfo_residuals_hz[index],
            "acquire_score": 0.6,
            "verify_score": 0.5,
            "control_scores": [0.1],
            "diagnostic_control_scores": [0.2],
            "exact_minus_control_margin": 0.4,
            "acquire_frame_support": 4,
            "verify_frame_support": 4,
            "control_frame_support": [4],
            "diagnostic_control_frame_support": [4],
            "frame_support": 4,
            "passed_research_gate": True,
        }
        for index in range(4)
    ]
    return {
        "rank": 1,
        "proposal_origin": "protected_seed",
        "source_seed_index": source_seed_index,
        "source_branch_id": "branch-a",
        "source_provenance_sha256": "d" * 64,
        "source_nominal_epoch_sample": epoch_sample,
        "source_nominal_absolute_cfo_hz": absolute_cfo_hz,
        "proposal_epoch_sample": epoch_sample,
        "proposal_absolute_cfo_hz": absolute_cfo_hz,
        "epoch_sample": epoch_sample,
        "absolute_cfo_hz": absolute_cfo_hz,
        "doppler_rate_hz_s": doppler_rate_hz_s,
        "canonical_cfo_hz": absolute_cfo_hz,
        "cfo_alias_lift": 0,
        "blocks": blocks,
        "trajectory_block_epoch_samples": block_epochs,
        "trajectory_block_epoch_residual_samples": list(epoch_residuals),
        "trajectory_block_absolute_cfo_hz": block_cfos_hz,
        "trajectory_block_cfo_residual_hz": list(cfo_residuals_hz),
        "trajectory_epoch_span_samples": max(epoch_residuals) - min(epoch_residuals),
        "trajectory_max_adjacent_epoch_step_samples": max(
            (
                abs(right - left)
                for left, right in zip(block_epochs, block_epochs[1:], strict=False)
            ),
            default=0,
        ),
        "trajectory_epoch_dispersion_samples": 0.0,
        "trajectory_epoch_fit_rms_samples": 0.0,
        "trajectory_timing_rate_samples_s": 0.0,
        "trajectory_cfo_span_hz": max(cfo_residuals_hz) - min(cfo_residuals_hz),
        "trajectory_cfo_dispersion_hz": 0.0,
        "trajectory_cfo_fit_rms_hz": 0.0,
        "trajectory_cfo_rate_residual_hz_s": 0.0,
        "trajectory_path_sha256": path_sha256,
        "trajectory_admissible": True,
        "whole_window_verify_score": 0.5,
        "whole_window_control_scores": [0.1],
        "whole_window_diagnostic_control_scores": [0.2],
        "whole_window_exact_minus_control_margin": 0.4,
        "whole_window_frame_support": 40,
        "whole_window_consistent_with_blocks": True,
    }


def _evidence(candidate: str) -> dict:
    return {
        "acquisition_status": "complete",
        "proposals": [
            {
                "candidate_id": candidate,
                "origin": "protected_seed",
                "decision": "candidate",
                "alias_class": "canonical",
                "mode": _mode_evidence(),
            }
        ],
        "sample_rate_hz": 1.0,
        "sample_count": 4,
        "frame_period_samples": 1.0,
        "block_starts": [0, 1, 2, 3],
        "searched_epoch_count": 1,
        "searched_cfo_count": 1,
        "evaluated_grid_point_count": 1,
        "evaluated_block_score_count": 4,
        "trajectory_path_evaluated_count": 1,
        "trajectory_path_limit_truncated_count": 0,
        "separation_suppressed_count": 0,
        "candidate_limit_truncated_count": 0,
        "additional_seeds": [],
        "evaluated_seed_count": 1,
        "whole_window_rescore_candidate_count": 1,
        "whole_window_rescore_template_score_count": 3,
        "acquisition_config_digest": "sha256:" + "9" * 64,
        "alias_class_tolerances": {
            "cfo_hz": 1e-3,
            "doppler_rate_hz_s": 1.0,
            "timing_samples": 0.25,
        },
        "exact_template_identity": {
            "label": "expected",
            "template_sha256": "a" * 64,
            "role": "expected",
            "gates_research_decision": True,
            "independently_reacquired": True,
        },
        "conditional_control_template_identities": [
            {
                "label": "conditional",
                "template_sha256": "b" * 64,
                "role": "conditional_gate",
                "gates_research_decision": True,
                "independently_reacquired": False,
            }
        ],
        "diagnostic_control_template_identities": [
            {
                "label": "diagnostic",
                "template_sha256": "c" * 64,
                "role": "orbit_breaking_diagnostic",
                "gates_research_decision": False,
                "independently_reacquired": False,
            }
        ],
        "presence_disposition": "uncalibrated_candidate",
        "code_specificity_disposition": "ambiguous",
        "cfo_alias_resolution_disposition": "unresolved",
        "uniqueness_disposition": "unresolved",
        "acquisition_thresholds_calibrated": False,
        "specificity_claimed": False,
        "acquisition_candidate_only": True,
        "global_fallback_attempted": False,
        "global_proposal_block_index": 0,
        "global_proposal_block_start_sample": None,
        "global_proposal_block_stop_sample": None,
        "global_proposal_sample_count": 0,
        "global_proposal_symbols": [2, 4],
        "global_proposal_symbol_count": 0,
        "global_proposal_frame_offset_count": 0,
        "global_searched_epoch_count": 0,
        "global_searched_cfo_count": 0,
        "global_evaluated_grid_point_count": 0,
        "global_peak_count": 0,
        "global_evaluated_block_score_count": 0,
        "global_trajectory_path_evaluated_count": 0,
        "global_trajectory_path_limit_truncated_count": 0,
        "global_separation_suppressed_count": 0,
        "global_candidate_limit_truncated_count": 0,
        "retained_mode_ids": [candidate],
        "accepted_mode_ids": [candidate],
        "tracks": [
            {
                "candidate_id": candidate,
                "status": "complete",
                "phase_lock_qualified": False,
                "published_independent": True,
                "mode_doppler_rate_hz_s": 0.0,
                "applied_initial_doppler_rate_hz_s": 0.0,
            }
        ],
        "phase_thresholds_unchanged": True,
    }


def test_frozen_population_binding_and_published_cohorts_are_exact() -> None:
    tool = _tool()

    frozen = tool.load_frozen_input(Path(__file__).parents[2] / tool.DEFAULT_INPUT)
    cohorts = tool.published_cohorts(frozen.rows)

    assert frozen.digest == tool.FROZEN_INPUT_SHA256
    assert len(frozen.rows) == 537
    assert len({row.row_key for row in frozen.rows}) == 537
    assert {name: len(rows) for name, rows in cohorts.items()} == {
        "standard_qualified_controls": 53,
        "v2_phase_qualified_controls": 55,
        "robust_v3_losses": 50,
        "one_update_aliases": 7,
        "matched_alias_null_peers": 57,
    }


def test_candidate_accounting_requires_every_serialized_or_truncated_proposal() -> None:
    tool = _tool()
    value = _evidence("candidate-a")
    value["evaluated_grid_point_count"] = 2
    value["searched_cfo_count"] = 2
    value["evaluated_block_score_count"] = 8
    value["trajectory_path_evaluated_count"] = 2
    value["candidate_limit_truncated_count"] = 1

    evidence = tool.canonical_v4_evidence(value)

    assert evidence["candidate_accounting_complete"] is True
    assert evidence["serialized_proposal_count"] == 1
    assert evidence["tracked_mode_count"] == 1
    assert evidence["accepted_tracked_mode_count"] == 1
    assert evidence["published_independent_track_count"] == 1
    assert evidence["source_seed_accounting_complete"] is True
    assert evidence["whole_window_accounting_complete"] is True
    assert evidence["trajectory_accounting_complete"] is True
    assert evidence["tracker_initial_rate_accounting_complete"] is True
    assert evidence["evaluated_seed_count"] == 1

    value["evaluated_grid_point_count"] = 3
    value["searched_cfo_count"] = 3
    value["evaluated_block_score_count"] = 12
    value["trajectory_path_evaluated_count"] = 3
    with pytest.raises(ValueError, match="retained plus separation-suppressed"):
        tool.canonical_v4_evidence(value)


def test_candidate_accounting_keeps_global_full_grid_separate_from_peak_inventory() -> None:
    tool = _tool()
    value = _evidence("candidate-local")
    value["proposals"].append(
        {
            "candidate_id": "candidate-global",
            "origin": "global_fallback",
            "decision": "rejected",
            "alias_class": "global-component",
            "mode": _mode_evidence(epoch_sample=8, path_sha256="f" * 64),
        }
    )
    value["retained_mode_ids"].append("candidate-global")
    value.update(
        {
            "global_fallback_attempted": True,
            "global_proposal_block_start_sample": 0,
            "global_proposal_block_stop_sample": 1,
            "global_proposal_sample_count": 1,
            "global_proposal_symbol_count": 2,
            "global_proposal_frame_offset_count": 1,
            "global_searched_epoch_count": 10,
            "global_searched_cfo_count": 3,
            "global_evaluated_grid_point_count": 30,
            "global_peak_count": 5,
            "global_evaluated_block_score_count": 4,
            "global_trajectory_path_evaluated_count": 1,
            "global_trajectory_path_limit_truncated_count": 7,
            "global_separation_suppressed_count": 2,
            "global_candidate_limit_truncated_count": 2,
        }
    )

    evidence = tool.canonical_v4_evidence(value)

    assert evidence["proposal_count"] == 6
    assert evidence["serialized_proposal_count"] == 2
    assert evidence["local_serialized_proposal_count"] == 1
    assert evidence["global_serialized_proposal_count"] == 1
    assert evidence["global_proposal_accounting_complete"] is True
    assert evidence["global_refinement_coordinate_pair_count"] == 1
    assert evidence["work_counters"]["global"]["evaluated_grid_point_count"] == 30
    assert evidence["work_counters"]["global"]["proposal_block_start_sample"] == 0
    assert evidence["work_counters"]["global"]["proposal_block_stop_sample"] == 1
    assert evidence["work_counters"]["global"]["proposal_symbols"] == [2, 4]
    assert evidence["work_counters"]["global"]["refinement_coordinate_pair_count"] == 1
    assert evidence["work_counters"]["global"]["trajectory_path_universe_count"] == 8
    assert evidence["proposal_origin_counts"] == {
        "global_fallback": 1,
        "protected_seed": 1,
    }
    assert evidence["component_inventory"][1]["accepted"] is False

    value["proposals"][1]["alias_class"] = "canonical"
    with pytest.raises(ValueError, match="full-trajectory equivalence"):
        tool.canonical_v4_evidence(value)

    value["proposals"][1]["alias_class"] = "global-component"
    value["global_proposal_frame_offset_count"] = 2
    with pytest.raises(ValueError, match="frame-offset count"):
        tool.canonical_v4_evidence(value)


def test_alias_classes_require_compatible_timing_rate_and_one_cfo_quotient() -> None:
    tool = _tool()
    spacing = tool.OFDM_CFO_ALIAS_HZ

    def mode(
        *,
        epoch: int = 19,
        cfos: tuple[float, ...] = (1_250.0, 1_250.0, 1_250.0, 1_250.0),
        residuals: tuple[int, ...] = (0, 0, 0, 0),
        rate: float = 10.0,
        lift: int = 0,
        branch: str = "branch-a",
        provenance: str = "a" * 64,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            epoch_sample=epoch,
            absolute_cfo_hz=cfos[0],
            canonical_cfo_hz=1_250.0,
            cfo_alias_lift=lift,
            doppler_rate_hz_s=rate,
            trajectory_block_epoch_residual_samples=residuals,
            trajectory_block_absolute_cfo_hz=cfos,
            source_branch_id=branch,
            source_provenance_sha256=provenance,
        )

    modes = (
        mode(),
        mode(
            cfos=tuple(1_250.0 + spacing for _ in range(4)),
            rate=10.5,
            lift=1,
            branch="branch-b",
            provenance="b" * 64,
        ),
        mode(
            cfos=(
                1_250.0 + spacing,
                1_250.0 + spacing,
                1_250.0 + 2 * spacing,
                1_250.0 + 2 * spacing,
            )
        ),
        mode(epoch=20),
        mode(residuals=(0, 0, 1, 1)),
        mode(rate=12.0),
    )

    classes = tool._alias_class_ids(
        modes,
        cfo_tolerance_hz=1e-3,
        rate_tolerance_hz_s=1.0,
        timing_tolerance_samples=0.25,
    )

    assert classes[id(modes[0])] == classes[id(modes[1])]
    assert classes[id(modes[2])] != classes[id(modes[0])]
    assert classes[id(modes[3])] != classes[id(modes[0])]
    assert classes[id(modes[4])] != classes[id(modes[0])]
    assert classes[id(modes[5])] != classes[id(modes[0])]


def test_candidate_identity_binds_selected_trajectory_path() -> None:
    tool = _tool()
    first = _mode_evidence(path_sha256="1" * 64)
    second = {**first, "trajectory_path_sha256": "2" * 64}

    assert tool._candidate_id(first) != tool._candidate_id(second)


def test_trajectory_and_tracker_rate_audits_reject_inconsistent_evidence() -> None:
    tool = _tool()
    value = _evidence("candidate-a")
    value["tracks"][0]["applied_initial_doppler_rate_hz_s"] = 1.0

    with pytest.raises(ValueError, match="initial Doppler rate"):
        tool.canonical_v4_evidence(value)

    value = _evidence("candidate-a")
    value["proposals"][0]["mode"]["blocks"][2]["trajectory_epoch_sample"] = 8
    with pytest.raises(ValueError, match="differs from its selected trajectory"):
        tool.canonical_v4_evidence(value)


def _write_chunk(root: Path, relative: str, values: np.ndarray, index: int, start: int) -> dict:
    raw = values.astype("<i2", copy=False).tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(raw)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed)
    return {
        "chunk_index": index,
        "relative_path": relative,
        "sample_start": start,
        "sample_count": values.shape[0],
        "sample_format": "ci16_le",
        "sample_layout": "sample_receiver_iq",
        "compressed_sha256": _sha256(compressed),
        "uncompressed_sha256": _sha256(raw),
        "uncompressed_bytes": len(raw),
    }


def test_manifest_v2_reader_verifies_and_reads_a_cross_chunk_receiver_slice(
    tmp_path: Path,
) -> None:
    tool = _tool()
    first = np.zeros((3, 2, 2), dtype=np.int16)
    second = np.zeros((3, 2, 2), dtype=np.int16)
    first[:, 1, 0] = [10, 11, 12]
    first[:, 1, 1] = [-10, -11, -12]
    second[:, 1, 0] = [13, 14, 15]
    second[:, 1, 1] = [-13, -14, -15]
    chunks = [
        _write_chunk(tmp_path, "radio-a/iq-000000.ci16.zst", first, 0, 0),
        _write_chunk(tmp_path, "radio-a/iq-000001.ci16.zst", second, 1, 3),
    ]
    manifest = {
        "schema_version": 2,
        "session_id": "capture-test",
        "streams": [
            {
                "stream_id": "stream-0",
                "applied_settings": {
                    "sample_rate_hz": 100,
                    "receiver_ids": [0, 1],
                },
                "chunks": chunks,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    reader = tool.FrozenCi16Reader(
        tmp_path,
        expected_manifest_digest=tool._file_digest(manifest_path),
        expected_session_id="capture-test",
        maximum_cached_chunks=1,
    )

    samples, receipts = reader.read_complex("stream-0", 1, 2, 3)

    np.testing.assert_array_equal(samples, [12 - 12j, 13 - 13j, 14 - 14j])
    assert len(receipts) == 2
    assert len(reader.verified_chunks) == 2


def test_output_policy_rejects_qnap_and_capture_tree_writes(tmp_path: Path) -> None:
    tool = _tool()
    capture = tmp_path / "capture"

    with pytest.raises(ValueError, match="read-only by policy"):
        tool._validate_output_root(tool.QNAP_ROOT / "canary", capture)
    with pytest.raises(ValueError, match="read-only by policy"):
        tool._validate_output_root(capture / "analysis", capture)

    tool._validate_output_root(tmp_path / "output", capture)


def test_resume_reuses_only_identity_bound_complete_rows_deterministically(
    tmp_path: Path,
) -> None:
    tool = _tool()
    sources = [_source_row(probe=0), _source_row(probe=1)]
    document = {
        "schema_version": 1,
        "session_id": tool.SESSION_ID,
        "run_id": tool.RUN_ID,
        "aggregate": {"source_window_count": 2},
        "windows": sources,
    }
    frozen = tool.FrozenInput(
        path=tmp_path / "input.json",
        digest=tool._value_digest(document),
        document=document,
        rows=tool.frozen_rows(document),
    )
    calls: list[str] = []

    def analyze(samples, sample_rate_hz, row):
        del samples, sample_rate_hz
        calls.append(row.row_key)
        return _evidence(row.row_key)

    binding = tool.AnalyzerBinding(
        api_name="fake-v4",
        source_sha256="sha256:" + "2" * 64,
        config_digest="sha256:" + "3" * 64,
        config={"test": True},
        analyze=analyze,
    )

    class Reader:
        sample_rate_hz = 100.0
        manifest_digest = "sha256:" + "4" * 64
        verified_chunks = {}

        def read_complex(self, stream, receiver, start, count):
            del stream, receiver, start
            return np.zeros(count, dtype=np.complex128), ()

    reader = Reader()
    output = tmp_path / "output"
    tool.run_canary(
        frozen=frozen,
        reader=reader,
        binding=binding,
        output_root=output,
        resume=False,
        maximum_rows=1,
        continue_on_error=False,
    )
    first_path = tool.checkpoint_path(output, frozen.rows[0])
    first_bytes = first_path.read_bytes()

    tool.run_canary(
        frozen=frozen,
        reader=reader,
        binding=binding,
        output_root=output,
        resume=True,
        maximum_rows=None,
        continue_on_error=False,
    )
    complete_bytes = (output / "canary.json").read_bytes()
    tool.run_canary(
        frozen=frozen,
        reader=reader,
        binding=binding,
        output_root=output,
        resume=True,
        maximum_rows=None,
        continue_on_error=False,
    )

    assert calls == [frozen.rows[0].row_key, frozen.rows[1].row_key]
    assert first_path.read_bytes() == first_bytes
    assert (output / "canary.json").read_bytes() == complete_bytes
    index = json.loads((output / "index.json").read_text(encoding="utf-8"))
    assert set(index["checkpoint_document_sha256"]) == {
        frozen.rows[0].row_key,
        frozen.rows[1].row_key,
    }


def test_published_gates_remain_not_estimable_for_a_partial_replay() -> None:
    tool = _tool()
    sources = [_source_row(probe=0), _source_row(probe=1)]
    document = {
        "schema_version": 1,
        "session_id": tool.SESSION_ID,
        "run_id": tool.RUN_ID,
        "aggregate": {"source_window_count": 2},
        "windows": sources,
    }
    frozen = tool.FrozenInput(
        path=Path("input.json"),
        digest=tool._value_digest(document),
        document=document,
        rows=tool.frozen_rows(document),
    )

    result = tool.evaluate_published_gates(
        frozen=frozen,
        cohorts=tool.published_cohorts(frozen.rows),
        checkpoints=(),
    )

    assert result == {
        "status": "not_estimable",
        "reason": "complete frozen-population row checkpoints are required",
        "expected_row_count": 2,
        "completed_row_count": 0,
    }


def test_published_gate_evaluator_uses_named_cohorts_and_separate_phase_policy() -> None:
    tool = _tool()
    frozen = tool.load_frozen_input(Path(__file__).parents[2] / tool.DEFAULT_INPUT)
    cohorts = tool.published_cohorts(frozen.rows)
    tracked = set(cohorts["standard_qualified_controls"])
    tracked.update(cohorts["v2_phase_qualified_controls"])
    tracked.update(cohorts["robust_v3_losses"])
    selected = set(tracked)
    checkpoints = []
    for row in frozen.rows:
        candidate = row.row_key
        evidence = _evidence(candidate)
        if candidate not in selected:
            evidence["proposals"][0]["decision"] = "rejected"
            evidence["accepted_mode_ids"] = []
            evidence["tracks"] = []
            evidence["presence_disposition"] = "no_research_candidate"
            evidence["code_specificity_disposition"] = "unassessed"
            evidence["cfo_alias_resolution_disposition"] = "unassessed"
            evidence["uniqueness_disposition"] = "unassessed"
        canonical = tool.canonical_v4_evidence(evidence)
        checkpoints.append(
            {
                "schema": tool.ROW_SCHEMA,
                "identity": {"row_key": row.row_key},
                "execution_status": "complete",
                "v4": canonical,
            }
        )

    result = tool.evaluate_published_gates(
        frozen=frozen,
        cohorts=cohorts,
        checkpoints=checkpoints,
    )

    assert result["status"] == "pass"
    assert all(result["checks"].values())
    assert result["automatic_phase_promotion"] is False

    robust_key = cohorts["robust_v3_losses"][0]
    checkpoint = next(row for row in checkpoints if row["identity"]["row_key"] == robust_key)
    checkpoint["v4"]["accepted_tracked_mode_count"] = 0
    failed = tool.evaluate_published_gates(
        frozen=frozen,
        cohorts=cohorts,
        checkpoints=checkpoints,
    )
    assert failed["status"] == "fail"
    assert failed["checks"]["robust_v3_losses_tracked"] is False


def test_v4_loader_binds_composed_api_and_all_scientific_sources() -> None:
    tool = _tool()

    binding = tool.load_v4_binding()

    assert binding.api_name == "analyze_contiguous_pilot_pnt_kalman_v4"
    assert {
        "src/leo/analysis/qam/pilot_pnt_kalman.py",
        "src/leo/analysis/qam/pilot_pnt_kalman_v4.py",
        "src/leo/analysis/starlink/acquisition.py",
        "src/leo/analysis/starlink/seeded_acquisition.py",
        "src/leo/analysis/starlink/templates.py",
    } <= set(binding.source_inventory)
    assert binding.runtime_inventory["folded_anchor_score_grid_backend"] in {
        "python",
        "portable",
        "avx2_fma",
    }
    if binding.runtime_inventory["native_acquisition_loaded"]:
        assert any("_native_acquisition" in path for path in binding.source_inventory)
    acquisition_config = binding.config["acquisition_config"]
    assert acquisition_config["global_proposal_block_index"] == 0
    assert acquisition_config["global_proposal_symbols"]
    assert acquisition_config["cfo_alias_rate_tolerance_hz_s"] == 1.0
    assert acquisition_config["cfo_alias_timing_tolerance_samples"] == 0.25
    assert acquisition_config["maximum_adjacent_trajectory_epoch_step_samples"] == 1
    assert acquisition_config["maximum_trajectory_epoch_fit_rms_samples"] == 0.75
    assert acquisition_config["maximum_trajectory_cfo_span_hz"] == 100.0


def test_real_v4_adapter_emits_the_strict_accounted_canary_surface() -> None:
    tool = _tool()
    binding = tool.load_v4_binding()
    source = _source_row(probe=0)
    row = tool.FrozenRow(
        index=0,
        row_key=tool._value_digest(tool._row_identity(source)),
        row_input_digest=tool._value_digest(source),
        source=source,
    )

    raw = binding.analyze(
        np.zeros(tool.WINDOW_SAMPLE_COUNT, dtype=np.complex128),
        tool.SAMPLE_RATE_HZ,
        row,
    )
    evidence = tool.canonical_v4_evidence(raw)

    assert evidence["proposal_count"] == (
        evidence["serialized_proposal_count"]
        + evidence["separation_suppressed_count"]
        + evidence["candidate_limit_truncated_count"]
        + evidence["global_separation_suppressed_count"]
        + evidence["global_candidate_limit_truncated_count"]
    )
    assert evidence["global_fallback_attempted"] is True
    assert evidence["global_proposal_block_index"] == 0
    assert evidence["global_proposal_block_start_sample"] == 0
    assert evidence["global_proposal_block_stop_sample"] == 50_000
    assert evidence["global_proposal_sample_count"] == 50_000
    assert evidence["global_proposal_symbol_count"] == len(evidence["global_proposal_symbols"])
    assert evidence["global_proposal_frame_offset_count"] == 15
    assert evidence["global_evaluated_grid_point_count"] == (
        evidence["global_searched_epoch_count"] * evidence["global_searched_cfo_count"]
    )
    assert evidence["phase_thresholds_unchanged"] is True
    assert evidence["work_counters"]["local"]["evaluated_block_score_count"] == 420
    assert evidence["work_counters"]["local"]["unique_even_lattice_score_count"] == 420
    assert evidence["global_evaluated_block_score_count"] == (
        evidence["global_refinement_coordinate_pair_count"] * len(evidence["block_starts"])
    )
    assert evidence["trajectory_path_evaluated_count"] >= evidence["evaluated_grid_point_count"]
    assert evidence["trajectory_path_limit_truncated_count"] >= 0
    assert (
        evidence["global_trajectory_path_evaluated_count"]
        >= (evidence["global_serialized_proposal_count"])
    )
    assert evidence["additional_seeds"] == []
    assert evidence["evaluated_seed_count"] == 1
    assert evidence["whole_window_rescore_template_score_count"] == (
        evidence["whole_window_rescore_candidate_count"]
        * (
            1
            + len(evidence["conditional_control_template_identities"])
            + len(evidence["diagnostic_control_template_identities"])
        )
    )
    assert all(
        component["source_branch_id"] == source["source_branch_id"]
        for component in evidence["component_inventory"]
    )
    assert all(
        len(component["trajectory_path_sha256"]) == 64
        and len(component["trajectory_block_epoch_samples"]) == 4
        and len(component["trajectory_block_absolute_cfo_hz"]) == 4
        for component in evidence["component_inventory"]
    )
    assert all(
        track["applied_initial_doppler_rate_hz_s"] == track["mode_doppler_rate_hz_s"]
        for track in evidence["tracks"]
    )
