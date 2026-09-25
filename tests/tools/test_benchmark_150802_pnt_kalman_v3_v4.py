from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "benchmark_150802_pnt_kalman_v3_v4.py"
    name = "benchmark_150802_pnt_kalman_v3_v4_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _row(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        row_key=f"sha256:{index + 1:064x}",
        row_input_digest=f"sha256:{index + 101:064x}",
        source={
            "stream": "stream-0",
            "receiver": 0,
            "edge": "lower",
            "source_probe_sample_start": index * 8,
            "epoch_sample": 3,
            "seed_cfo_hz": 250.0,
            "source_branch_id": f"branch-{index}",
            "standard_v1_local_rate_hz_s": 0.0,
        },
    )


def _v3_result() -> dict:
    return {
        "status": "complete",
        "frames": [],
        "supported_frame_count": 4,
        "phase_update_count": 3,
        "frequency_update_count": 4,
        "timing_update_count": 2,
        "phase_lock_qualified": False,
        "phase_lock_reason": "test",
        "reason": "test",
        "initial_alignment": None,
    }


def _v4_result(row_key: str) -> dict:
    return {
        "numerical_status": "complete",
        "acquisition_status": "complete",
        "proposal_count": 1,
        "serialized_proposal_count": 1,
        "local_serialized_proposal_count": 1,
        "global_serialized_proposal_count": 0,
        "local_evaluated_grid_point_count": 1,
        "local_evaluated_block_score_count": 4,
        "local_trajectory_path_evaluated_count": 1,
        "local_trajectory_path_limit_truncated_count": 0,
        "global_fallback_attempted": False,
        "global_proposal_block_index": 0,
        "global_proposal_block_start_sample": None,
        "global_proposal_block_stop_sample": None,
        "global_proposal_sample_count": 0,
        "global_proposal_symbols": [2, 4],
        "global_proposal_symbol_count": 0,
        "global_proposal_frame_offset_count": 0,
        "global_evaluated_grid_point_count": 0,
        "global_peak_count": 0,
        "global_refinement_coordinate_pair_count": 0,
        "global_evaluated_block_score_count": 0,
        "global_trajectory_path_evaluated_count": 0,
        "global_trajectory_path_limit_truncated_count": 0,
        "additional_seed_count": 0,
        "evaluated_seed_count": 1,
        "whole_window_rescore_candidate_count": 1,
        "whole_window_rescore_template_score_count": 6,
        "retained_mode_count": 1,
        "accepted_mode_count": 1,
        "accepted_tracked_mode_count": 1,
        "accepted_phase_lock_count": 0,
        "component_inventory": [],
        "presence_disposition": "uncalibrated_candidate",
        "code_specificity_disposition": "ambiguous",
        "cfo_alias_resolution_disposition": "unresolved",
        "uniqueness_disposition": "unresolved",
        "scientific_qualification_claimed": False,
        "phase_thresholds_unchanged": True,
        "evidence_digest": row_key,
    }


class _Clock:
    def __init__(self, step: int) -> None:
        self.value = 0
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


class _Reader:
    sample_rate_hz = 100.0
    manifest_digest = "sha256:" + "4" * 64
    _maximum_cached_chunks = 2

    def read_complex(self, stream: str, receiver: int, start: int, count: int):
        del stream, receiver
        receipt = {
            "relative_path": f"chunk-{start // 8}.zst",
            "compressed_sha256": "sha256:" + "5" * 64,
            "uncompressed_sha256": "sha256:" + "6" * 64,
            "sample_start": start,
            "sample_count": count,
        }
        return np.arange(count, dtype=np.float64).astype(np.complex128), (receipt,)


def _bindings(tool):
    return tool.BenchmarkBindings(
        v3_api_name="fake-v3",
        v3_source_sha256="sha256:" + "1" * 64,
        v3_config_digest="sha256:" + "2" * 64,
        v3_config={"version": 3},
        v4_api_name="fake-v4",
        v4_source_sha256="sha256:" + "3" * 64,
        v4_config_digest="sha256:" + "7" * 64,
        v4_config={"version": 4},
        source_inventory={"fake.py": "sha256:" + "8" * 64},
        runtime_inventory={"folded_anchor_score_grid_backend": "fake"},
        analyze_v3=lambda samples, rate, row: _v3_result(),
        analyze_v4=lambda samples, rate, row: _v4_result(row.row_key),
        acquisition_module=object(),
    )


def _worker_receipt(
    tool,
    analyzer: str,
    rows: tuple[SimpleNamespace, ...],
    *,
    analyzer_times: tuple[int, ...],
    full_wall_ns: int,
    peak_rss_bytes: int,
    seeded_path: bool | tuple[bool, ...] = True,
    population_row_count: int | None = None,
    full_population: bool = True,
) -> dict:
    bindings = {
        "v3": {
            "api": "fake-v3",
            "source_sha256": "sha256:" + "1" * 64,
            "config_digest": "sha256:" + "2" * 64,
        },
        "v4": {
            "api": "fake-v4",
            "source_sha256": "sha256:" + "3" * 64,
            "config_digest": "sha256:" + "7" * 64,
        },
    }
    identities = [
        {
            "row_index": row.index,
            "row_key": row.row_key,
            "row_input_digest": row.row_input_digest,
        }
        for row in rows
    ]
    seeded_paths = (seeded_path,) * len(rows) if isinstance(seeded_path, bool) else seeded_path
    if len(seeded_paths) != len(rows):
        raise ValueError("seeded-path fixture length mismatch")
    receipt = {
        "schema": tool.ISOLATED_WORKER_SCHEMA,
        "analyzer": analyzer,
        "session_id": tool.CANARY.SESSION_ID,
        "run_id": tool.CANARY.RUN_ID,
        "frozen_input_sha256": "sha256:" + "a" * 64,
        "recording_manifest_sha256": "sha256:" + "4" * 64,
        "harness_source_sha256": tool.CANARY._file_digest(Path(tool.__file__).resolve()),
        "binding": bindings[analyzer],
        "coverage": {
            "population_row_count": (
                len(rows) if population_row_count is None else population_row_count
            ),
            "scheduled_row_count": len(rows),
            "full_population": full_population,
            "rows": identities,
            "row_identity_digest": tool.CANARY._value_digest(identities),
        },
        "measurement_scope": {"isolated_analyzer_process": True},
        "rows": [
            {
                **identity,
                "analyzer_elapsed_ns": elapsed,
                "seeded_path": selected_seeded_path if analyzer == "v4" else None,
                "outcome_evidence_digest": (
                    identity["row_key"]
                    if analyzer == "v4"
                    else tool._v3_summary(_v3_result())["evidence_digest"]
                ),
            }
            for identity, elapsed, selected_seeded_path in zip(
                identities,
                analyzer_times,
                seeded_paths,
                strict=True,
            )
        ],
        "full_replay_wall_elapsed_ns": full_wall_ns,
        "peak_rss": {"maximum_observed": peak_rss_bytes},
    }
    receipt["worker_receipt_digest"] = tool.CANARY._value_digest(receipt)
    return receipt


def _worker_receipts(
    tool,
    rows: tuple[SimpleNamespace, ...],
    *,
    v3_times: tuple[int, ...],
    v4_times: tuple[int, ...],
    v3_wall_ns: int = 100,
    v4_wall_ns: int = 125,
    v3_peak_rss: int = 100,
    v4_peak_rss: int = 125,
    v4_seeded_paths: bool | tuple[bool, ...] = True,
    population_row_count: int | None = None,
    full_population: bool = True,
) -> dict[str, dict]:
    return {
        "v3": _worker_receipt(
            tool,
            "v3",
            rows,
            analyzer_times=v3_times,
            full_wall_ns=v3_wall_ns,
            peak_rss_bytes=v3_peak_rss,
            population_row_count=population_row_count,
            full_population=full_population,
        ),
        "v4": _worker_receipt(
            tool,
            "v4",
            rows,
            analyzer_times=v4_times,
            full_wall_ns=v4_wall_ns,
            peak_rss_bytes=v4_peak_rss,
            seeded_path=v4_seeded_paths,
            population_row_count=population_row_count,
            full_population=full_population,
        ),
    }


def _gate_scientific(tool, rows: tuple[SimpleNamespace, ...], *, parity: bool = True) -> dict:
    return {
        "session_id": tool.CANARY.SESSION_ID,
        "run_id": tool.CANARY.RUN_ID,
        "frozen_input_sha256": "sha256:" + "a" * 64,
        "recording_manifest_sha256": "sha256:" + "4" * 64,
        "harness_source_sha256": tool.CANARY._file_digest(Path(tool.__file__).resolve()),
        "bindings": {
            "v3": {
                "api": "fake-v3",
                "source_sha256": "sha256:" + "1" * 64,
                "config_digest": "sha256:" + "2" * 64,
            },
            "v4": {
                "api": "fake-v4",
                "source_sha256": "sha256:" + "3" * 64,
                "config_digest": "sha256:" + "7" * 64,
            },
        },
        "coverage": {
            "population_row_count": len(rows),
            "scheduled_row_count": len(rows),
            "full_population": True,
        },
        "rows": [
            {
                "row_index": row.index,
                "row_key": row.row_key,
                "row_input_digest": row.row_input_digest,
                "v3": {"evidence_digest": tool._v3_summary(_v3_result())["evidence_digest"]},
                "v4": {"evidence_digest": row.row_key},
            }
            for row in rows
        ],
        "native_numpy_parity": {"all_rows_passed": parity},
    }


def _rehash_worker(tool, receipt: dict) -> None:
    receipt.pop("worker_receipt_digest", None)
    receipt["worker_receipt_digest"] = tool.CANARY._value_digest(receipt)


def _fake_parity(samples, rate, row, module, count, clock):
    del samples, rate, module, count
    started = clock()
    elapsed = clock() - started
    return (
        {
            "row_key": row.row_key,
            "status": "pass",
            "sample_count": 4,
            "sample_sha256": "sha256:" + "9" * 64,
            "maximum_absolute_score_delta": 0.0,
            "argmax_mismatch_count": 0,
            "allclose": True,
        },
        {
            "row_key": row.row_key,
            "native_elapsed_ns": elapsed,
            "numpy_elapsed_ns": elapsed,
        },
    )


def test_representative_rows_are_evenly_spaced_and_include_endpoints() -> None:
    tool = _tool()
    rows = tuple(_row(index) for index in range(9))

    selected = tool.representative_rows(rows, 3)

    assert tuple(row.index for row in selected) == (0, 4, 8)
    assert tool.representative_rows(rows, 1) == (rows[0],)


def test_scientific_receipt_is_deterministic_and_separate_from_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool.CANARY, "WINDOW_SAMPLE_COUNT", 8)
    rows = tuple(_row(index) for index in range(2))
    frozen = SimpleNamespace(
        rows=rows,
        digest="sha256:" + "a" * 64,
    )
    first_workers = _worker_receipts(
        tool,
        rows,
        v3_times=(100, 100),
        v4_times=(100, 100),
    )
    second_workers = _worker_receipts(
        tool,
        rows,
        v3_times=(1_000, 1_000),
        v4_times=(1_000, 1_000),
        v3_wall_ns=1_000,
        v4_wall_ns=1_200,
        v3_peak_rss=1_000,
        v4_peak_rss=1_200,
    )

    first = tool.run_benchmark(
        frozen=frozen,
        reader=_Reader(),
        bindings=_bindings(tool),
        maximum_rows=None,
        parity_row_count=2,
        parity_sample_count=4,
        clock_ns=_Clock(10),
        peak_rss_bytes=iter((100, 200, 250)).__next__,
        parity_function=_fake_parity,
        isolated_worker_receipts=first_workers,
    )
    second = tool.run_benchmark(
        frozen=frozen,
        reader=_Reader(),
        bindings=_bindings(tool),
        maximum_rows=None,
        parity_row_count=2,
        parity_sample_count=4,
        clock_ns=_Clock(100),
        peak_rss_bytes=iter((1_000, 2_000, 2_500)).__next__,
        parity_function=_fake_parity,
        isolated_worker_receipts=second_workers,
    )

    first_scientific, first_performance = first
    second_scientific, second_performance = second
    assert first_scientific == second_scientific
    assert first_performance != second_performance
    assert first_scientific["native_numpy_parity"]["all_rows_passed"] is True
    assert first_scientific["coverage"]["full_population"] is True
    assert first_scientific["bounded_inventory"]["retained_parity_iq_bytes"] == 128
    assert (
        first_scientific["bounded_inventory"]["actual"]["v4_local_evaluated_block_score_count"] == 8
    )
    assert (
        first_scientific["bounded_inventory"]["actual"]["v4_local_trajectory_path_evaluated_count"]
        == 2
    )
    assert (
        first_scientific["bounded_inventory"]["actual"][
            "v4_global_refinement_coordinate_pair_count"
        ]
        == 0
    )
    assert "elapsed_ns" not in json.dumps(first_scientific, sort_keys=True)
    assert first_performance["distributions"]["v3"]["p95_ns"] == 10.0
    assert first_performance["exit_gates"]["status"] == "pass"
    assert first_performance["exit_gates"]["checks"] == {
        "seeded_path_p95": True,
        "full_wall": True,
        "peak_rss": True,
        "native_numpy_parity": True,
    }
    assert [row["execution_order"] for row in first_performance["per_row"]] == [
        "v3_then_v4",
        "v4_then_v3",
    ]

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    tool.write_receipts(first_root, *first, capture_root=None)
    tool.write_receipts(second_root, *second, capture_root=None)
    assert (first_root / tool.SCIENTIFIC_FILENAME).read_bytes() == (
        second_root / tool.SCIENTIFIC_FILENAME
    ).read_bytes()
    assert (first_root / tool.PERFORMANCE_FILENAME).read_bytes() != (
        second_root / tool.PERFORMANCE_FILENAME
    ).read_bytes()
    assert (first_root / tool.ISOLATED_WORKER_FILENAMES["v3"]).exists()
    assert (first_root / tool.ISOLATED_WORKER_FILENAMES["v4"]).exists()


def test_isolated_worker_receipt_binds_source_rows_and_seeded_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool.CANARY, "WINDOW_SAMPLE_COUNT", 8)
    rows = tuple(_row(index) for index in range(2))
    frozen = SimpleNamespace(rows=rows, digest="sha256:" + "a" * 64)
    binding = tool.IsolatedWorkerBinding(
        analyzer="v4",
        api_name="fake-v4",
        source_sha256="sha256:" + "3" * 64,
        config_digest="sha256:" + "7" * 64,
        config={"version": 4},
        source_inventory={"fake.py": "sha256:" + "8" * 64},
        runtime_inventory={"backend": "fake"},
        analyze=lambda samples, rate, row: _v4_result(row.row_key),
        summarize=lambda result: result,
    )

    receipt = tool.run_isolated_worker(
        frozen=frozen,
        reader=_Reader(),
        binding=binding,
        maximum_rows=None,
        clock_ns=_Clock(10),
        peak_rss_bytes=iter((100, 150)).__next__,
    )

    assert receipt["analyzer"] == "v4"
    assert receipt["coverage"]["full_population"] is True
    assert receipt["coverage"]["row_identity_digest"] == tool.CANARY._value_digest(
        receipt["coverage"]["rows"]
    )
    assert [row["seeded_path"] for row in receipt["rows"]] == [True, True]
    assert receipt["distributions"]["analyzer"]["p95_ns"] == 10.0
    digest = receipt.pop("worker_receipt_digest")
    assert digest == tool.CANARY._value_digest(receipt)


def test_exit_gates_pass_at_exact_boundaries() -> None:
    tool = _tool()
    rows = (_row(0),)
    gates = tool.evaluate_performance_exit_gates(
        _gate_scientific(tool, rows),
        _worker_receipts(
            tool,
            rows,
            v3_times=(100,),
            v4_times=(100,),
            v3_wall_ns=100,
            v4_wall_ns=125,
            v3_peak_rss=100,
            v4_peak_rss=125,
        ),
    )

    assert gates["status"] == "pass"
    assert gates["checks"] == {
        "seeded_path_p95": True,
        "full_wall": True,
        "peak_rss": True,
        "native_numpy_parity": True,
    }
    assert gates["observations"]["seeded_path_v4_p95_over_v3"] == 1.0
    assert gates["observations"]["full_wall_v4_over_v3"] == 1.25
    assert gates["observations"]["peak_rss_v4_over_v3"] == 1.25


def test_seeded_path_p95_uses_only_the_same_seeded_v4_rows() -> None:
    tool = _tool()
    rows = (_row(0), _row(1))
    gates = tool.evaluate_performance_exit_gates(
        _gate_scientific(tool, rows),
        _worker_receipts(
            tool,
            rows,
            v3_times=(100, 1),
            v4_times=(100, 1_000_000),
            v4_seeded_paths=(True, False),
        ),
    )

    assert gates["status"] == "pass"
    assert gates["observations"]["seeded_path_row_count"] == 1
    assert gates["observations"]["seeded_path_v3_p95_ns"] == 100.0
    assert gates["observations"]["seeded_path_v4_p95_ns"] == 100.0


@pytest.mark.parametrize(
    ("failed_gate", "v4_time", "v4_wall", "v4_rss", "parity"),
    (
        ("seeded_path_p95", 101, 125, 125, True),
        ("full_wall", 100, 126, 125, True),
        ("peak_rss", 100, 125, 126, True),
        ("native_numpy_parity", 100, 125, 125, False),
    ),
)
def test_exit_gates_fail_immediately_above_each_boundary(
    failed_gate: str,
    v4_time: int,
    v4_wall: int,
    v4_rss: int,
    parity: bool,
) -> None:
    tool = _tool()
    rows = (_row(0),)
    gates = tool.evaluate_performance_exit_gates(
        _gate_scientific(tool, rows, parity=parity),
        _worker_receipts(
            tool,
            rows,
            v3_times=(100,),
            v4_times=(v4_time,),
            v3_wall_ns=100,
            v4_wall_ns=v4_wall,
            v3_peak_rss=100,
            v4_peak_rss=v4_rss,
        ),
    )

    assert gates["status"] == "fail"
    assert gates["checks"][failed_gate] is False
    assert sum(value is False for value in gates["checks"].values()) == 1


def test_bounded_subset_is_explicitly_not_estimable() -> None:
    tool = _tool()
    rows = (_row(0),)
    scientific = _gate_scientific(tool, rows)
    scientific["coverage"].update(
        population_row_count=2,
        scheduled_row_count=1,
        full_population=False,
    )

    gates = tool.evaluate_performance_exit_gates(
        scientific,
        _worker_receipts(
            tool,
            rows,
            v3_times=(100,),
            v4_times=(100,),
            population_row_count=2,
            full_population=False,
        ),
    )

    assert gates["status"] == "not_estimable"
    assert "bounded subsets cannot qualify" in gates["reason"]
    assert all(value is None for value in gates["checks"].values())


def test_missing_isolated_workers_are_not_estimable() -> None:
    tool = _tool()

    gates = tool.evaluate_performance_exit_gates(
        _gate_scientific(tool, (_row(0),)),
        None,
    )

    assert gates["status"] == "not_estimable"
    assert "isolated V3 and V4" in gates["reason"]


@pytest.mark.parametrize("mismatch", ("source", "row", "outcome"))
def test_exit_gates_reject_nonidentical_source_bound_worker_receipts(
    mismatch: str,
) -> None:
    tool = _tool()
    rows = (_row(0),)
    receipts = _worker_receipts(tool, rows, v3_times=(100,), v4_times=(100,))
    receipts = deepcopy(receipts)
    if mismatch == "source":
        receipts["v4"]["binding"]["source_sha256"] = "sha256:" + "f" * 64
    elif mismatch == "row":
        receipts["v4"]["rows"][0]["row_input_digest"] = "sha256:" + "e" * 64
    else:
        receipts["v4"]["rows"][0]["outcome_evidence_digest"] = "sha256:" + "d" * 64
    _rehash_worker(tool, receipts["v4"])

    with pytest.raises(ValueError, match=f"isolated v4 worker .*{mismatch}"):
        tool.evaluate_performance_exit_gates(_gate_scientific(tool, rows), receipts)


def test_isolated_worker_orchestration_uses_two_fresh_interpreters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    commands: list[list[str]] = []

    def run(command, *, check, capture_output, text):
        assert check is False
        assert capture_output is True
        assert text is True
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tool.subprocess, "run", run)
    monkeypatch.setattr(
        tool.CANARY,
        "_json_object",
        lambda path: {"analyzer": "v3" if "v3" in path.name else "v4"},
    )

    receipts = tool.run_isolated_worker_subprocesses(
        input_path=tmp_path / "input.json",
        capture_root=tmp_path / "capture",
        maximum_rows=3,
    )

    assert receipts == {"v3": {"analyzer": "v3"}, "v4": {"analyzer": "v4"}}
    assert len(commands) == 2
    assert all(command[0] == sys.executable for command in commands)
    assert [command[command.index("--isolated-worker") + 1] for command in commands] == [
        "v3",
        "v4",
    ]
    assert all(command[-2:] == ["--maximum-rows", "3"] for command in commands)
    output_roots = [command[command.index("--output-root") + 1] for command in commands]
    assert output_roots[0] != output_roots[1]


def test_native_numpy_parity_matches_on_a_small_deterministic_probe() -> None:
    tool = _tool()
    import leo.analysis.starlink.acquisition as acquisition

    assert acquisition._native_acquisition is not None
    generator = np.random.default_rng(0x150802)
    samples = generator.normal(size=4_000) + 1j * generator.normal(size=4_000)
    row = _row(0)

    scientific, timing = tool.native_numpy_parity(
        samples,
        250_000.0,
        row,
        acquisition,
        4_000,
        _Clock(25),
    )

    assert scientific["status"] == "pass"
    assert scientific["allclose"] is True
    assert scientific["argmax_mismatch_count"] == 0
    assert scientific["maximum_absolute_score_delta"] <= tool.PARITY_ATOL
    assert timing == {
        "row_key": row.row_key,
        "native_elapsed_ns": 25,
        "numpy_elapsed_ns": 25,
    }
    assert acquisition._native_acquisition is not None


def test_direct_v4_summary_records_stable_seed_and_whole_window_contract() -> None:
    tool = _tool()
    from leo.analysis.qam.pilot_pnt_kalman_v4 import (
        PilotPntKalmanConfigV4,
        analyze_contiguous_pilot_pnt_kalman_v4,
    )
    from leo.analysis.starlink.seeded_acquisition import (
        KnownPilotModeSeed,
        SeededPilotAcquisitionConfig,
    )

    config = PilotPntKalmanConfigV4(
        acquisition_config=SeededPilotAcquisitionConfig(global_fallback_enabled=False)
    )
    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.zeros(round(0.075 * 250_000), dtype=np.complex128),
        250_000.0,
        seed=KnownPilotModeSeed(7, 0.0, "branch", "a" * 64),
        additional_seeds=(),
        edge="lower",
        config=config,
    )

    summary = tool._v4_result_summary(result, config)

    assert summary["additional_seed_count"] == 0
    assert summary["evaluated_seed_count"] == 1
    assert summary["whole_window_rescore_template_score_count"] >= 0
    assert summary["local_evaluated_grid_point_count"] == 105
    assert summary["local_evaluated_block_score_count"] > 0
    assert summary["local_trajectory_path_evaluated_count"] > 0
    assert summary["local_trajectory_path_limit_truncated_count"] >= 0
    assert summary["global_proposal_block_index"] == 0
    assert summary["global_proposal_block_start_sample"] is None
    assert summary["global_proposal_block_stop_sample"] is None
    assert summary["global_proposal_sample_count"] == 0
    assert summary["global_proposal_symbol_count"] == 0
    assert summary["global_proposal_frame_offset_count"] == 0
    assert summary["global_refinement_coordinate_pair_count"] == 0
    assert summary["global_trajectory_path_evaluated_count"] == 0
    components = summary["component_inventory"]
    assert components
    assert all(component["source_seed_index"] == 0 for component in components)
    assert all(component["trajectory_path_sha256"] for component in components)
    assert all(
        isinstance(component["trajectory_max_adjacent_epoch_step_samples"], int)
        and isinstance(component["trajectory_admissible"], bool)
        for component in components
    )
    assert all(
        {
            "acquire_frame_support",
            "verify_frame_support",
            "control_frame_support",
            "diagnostic_control_frame_support",
        }
        <= block.keys()
        for component in components
        for block in component["blocks"]
    )


def test_direct_v4_summary_accounts_bounded_global_proposal_and_exact_pairs() -> None:
    tool = _tool()
    from leo.analysis.qam.pilot_pnt_kalman_v4 import (
        PilotPntKalmanConfigV4,
        analyze_contiguous_pilot_pnt_kalman_v4,
    )
    from leo.analysis.starlink.seeded_acquisition import KnownPilotModeSeed

    config = PilotPntKalmanConfigV4()
    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.zeros(round(0.075 * 250_000), dtype=np.complex128),
        250_000.0,
        seed=KnownPilotModeSeed(7, 0.0, "branch", "a" * 64),
        additional_seeds=(),
        edge="lower",
        config=config,
    )

    summary = tool._v4_result_summary(result, config)

    assert summary["global_fallback_attempted"] is True
    assert summary["global_proposal_block_index"] == 0
    assert summary["global_proposal_block_start_sample"] == 0
    assert summary["global_proposal_block_stop_sample"] == 5_000
    assert summary["global_proposal_sample_count"] == 5_000
    assert summary["global_proposal_symbol_count"] == len(summary["global_proposal_symbols"])
    assert summary["global_proposal_frame_offset_count"] == 15
    assert summary["global_evaluated_block_score_count"] == (
        summary["global_refinement_coordinate_pair_count"] * len(result.acquisition.block_starts)
    )


def test_bounds_fail_before_any_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _tool()
    monkeypatch.setattr(tool.CANARY, "WINDOW_SAMPLE_COUNT", 8)
    frozen = SimpleNamespace(rows=(_row(0),), digest="sha256:" + "a" * 64)

    with pytest.raises(ValueError, match="maximum rows"):
        tool.run_benchmark(
            frozen=frozen,
            reader=_Reader(),
            bindings=_bindings(tool),
            maximum_rows=0,
            parity_row_count=1,
            parity_sample_count=4,
        )
    with pytest.raises(ValueError, match="parity row count"):
        tool.run_benchmark(
            frozen=frozen,
            reader=_Reader(),
            bindings=_bindings(tool),
            maximum_rows=1,
            parity_row_count=tool.MAXIMUM_PARITY_ROW_COUNT + 1,
            parity_sample_count=4,
        )


def test_real_binding_records_source_config_backend_and_native_binary() -> None:
    tool = _tool()

    binding = tool.load_bindings()

    assert binding.v3_api_name == "analyze_contiguous_pilot_pnt_kalman_v3"
    assert binding.v4_api_name == "analyze_contiguous_pilot_pnt_kalman_v4"
    assert binding.runtime_inventory["folded_anchor_score_grid_backend"] in {
        "portable",
        "avx2_fma",
    }
    assert binding.v4_config["acquisition_config"]["global_proposal_block_index"] == 0
    assert binding.v4_config["acquisition_config"]["global_proposal_symbols"]
    assert any("_native_acquisition" in path for path in binding.source_inventory)
