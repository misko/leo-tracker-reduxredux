from __future__ import annotations

import copy
import json
import subprocess
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import zstandard as zstd

from leo.contracts.digests import canonical_digest, sha256_digest
from tools import run_satellite_tracking_checkpoints as tool


@dataclass(frozen=True)
class _Fixture:
    root: Path
    amendment_path: Path
    specs: tuple[tool._ArcSpec, tool._ArcSpec]


def _write_bytes(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _write_json(root: Path, relative: str, value: object) -> tuple[Path, str]:
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    return _write_bytes(root, relative, payload), sha256_digest(payload)


def _rewrite_amendment(path: Path, document: dict[str, Any]) -> None:
    body = {key: value for key, value in document.items() if key != "amendment_digest"}
    path.write_text(
        json.dumps({**body, "amendment_digest": canonical_digest(body)}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _authority_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Fixture:
    root = tmp_path / "repo"
    root.mkdir()

    base_digest = canonical_digest({"base": "fixture"})
    _, base_sha = _write_json(root, "config/base.json", {"protocol_digest": base_digest})
    roadmap_payload = b"# fixture roadmap\n"
    _write_bytes(root, "plans/roadmap.md", roadmap_payload)
    roadmap_sha = sha256_digest(roadmap_payload)

    calibration_protocol = {
        "input": {"independent_background_pair_count": 3},
        "calibration": {
            "formal_95_percent_rank_minimum_pairs": 19,
            "formal_coverage_claimed": False,
        },
    }
    calibration_result_digest = canonical_digest({"calibration": "fixture"})
    calibration_result = {
        "result": {
            "formal_95_percent_rank_pair_count_sufficient": False,
            "identity_claimed": False,
            "threshold_fitted": False,
            "result_digest": calibration_result_digest,
        }
    }
    _, calibration_protocol_sha = _write_json(root, "config/calibration.json", calibration_protocol)
    _, calibration_result_sha = _write_json(root, "reports/calibration.json", calibration_result)
    floor_payload = b'{"fixture":"detached holdout floor source"}\n'
    _write_bytes(root, "reports/floors.json", floor_payload)
    floor_sha = sha256_digest(floor_payload)

    sealed_a = b"fixture-sealed-9981"
    sealed_b = b"fixture-sealed-150802"
    tle_a = b"fixture-tle-9981"
    tle_b = b"fixture-tle-150802"
    _write_bytes(root, "sealed/9981.json.zst", sealed_a)
    _write_bytes(root, "sealed/150802.json.zst", sealed_b)
    _write_bytes(root, "tle/9981.tle", tle_a)
    _write_bytes(root, "tle/150802.tle", tle_b)
    specs = (
        tool._ArcSpec(
            label="9981",
            arc_id="long-arc-9981-r19f2-s1-rx1-upper-0-30s",
            sealed_result_path="sealed/9981.json.zst",
            sealed_result_sha256=sha256_digest(sealed_a),
            tle_default_path="tle/9981.tle",
            tle_sha256=sha256_digest(tle_a),
            tle_collected_utc_ns=1_700_000_000_000_000_001,
            tle_object_count=2,
            annotation_catalog_numbers=(101,),
        ),
        tool._ArcSpec(
            label="150802",
            arc_id="long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
            sealed_result_path="sealed/150802.json.zst",
            sealed_result_sha256=sha256_digest(sealed_b),
            tle_default_path="tle/150802.tle",
            tle_sha256=sha256_digest(tle_b),
            tle_collected_utc_ns=1_700_000_000_000_000_002,
            tle_object_count=2,
            annotation_catalog_numbers=(201, 202),
        ),
    )

    monkeypatch.setattr(tool, "_BASE_PROTOCOL_PATH", "config/base.json")
    monkeypatch.setattr(tool, "_BASE_PROTOCOL_SHA256", base_sha)
    monkeypatch.setattr(tool, "_BASE_PROTOCOL_DIGEST", base_digest)
    monkeypatch.setattr(tool, "_ROADMAP_PATH", "plans/roadmap.md")
    monkeypatch.setattr(tool, "_ROADMAP_SHA256", roadmap_sha)
    monkeypatch.setattr(tool, "_CALIBRATION_PROTOCOL_PATH", "config/calibration.json")
    monkeypatch.setattr(tool, "_CALIBRATION_PROTOCOL_SHA256", calibration_protocol_sha)
    monkeypatch.setattr(tool, "_CALIBRATION_RESULT_PATH", "reports/calibration.json")
    monkeypatch.setattr(tool, "_CALIBRATION_RESULT_SHA256", calibration_result_sha)
    monkeypatch.setattr(tool, "_CALIBRATION_RESULT_DIGEST", calibration_result_digest)
    monkeypatch.setattr(tool, "_FLOOR_SOURCE_PATH", "reports/floors.json")
    monkeypatch.setattr(tool, "_FLOOR_SOURCE_SHA256", floor_sha)
    monkeypatch.setattr(tool, "_ARC_SPECS", specs)
    monkeypatch.setattr(tool, "DEFAULT_AMENDMENT", Path("config/amendment.json"))
    monkeypatch.setattr(tool, "_EXPECTED_AMENDMENT_ID", "fixture-checkpoint-attempt-1")
    monkeypatch.setattr(
        tool,
        "_EXPECTED_CHRONOLOGY",
        "Frozen fixture authority before synthetic execution.",
    )
    expected_outputs = {
        "artifact_directory": "reports/figures/checkpoint-attempt-1",
        "report_path": "reports/checkpoint-attempt-1.md",
        "attempt_receipt_path": "reports/figures/checkpoint-attempt-1-receipt.json",
    }
    monkeypatch.setattr(tool, "_EXPECTED_OUTPUTS", expected_outputs)

    calibration_authority = {
        "protocol": {
            "path": "config/calibration.json",
            "sha256": calibration_protocol_sha,
        },
        "sealed_result": {
            "path": "reports/calibration.json",
            "sha256": calibration_result_sha,
            "result_digest": calibration_result_digest,
        },
        "independent_background_pair_count": 3,
        "formal_95_percent_rank_minimum_pairs": 19,
        "formal_95_percent_rank_pair_count_sufficient": False,
        "covariance_calibrated": False,
        "c2_complete": False,
    }
    monkeypatch.setattr(tool, "_EXPECTED_CALIBRATION_AUTHORITY", calibration_authority)
    controls = copy.deepcopy(tool._EXPECTED_NUMERICAL_CONTROLS)
    controls["c1"]["measurement_floor_source"] = {
        "path": "reports/floors.json",
        "sha256": floor_sha,
    }
    for overlay in controls["c1"]["measurement_floor_overlays"]:
        overlay["source_digest"] = floor_sha
    monkeypatch.setattr(tool, "_EXPECTED_NUMERICAL_CONTROLS", controls)
    monkeypatch.setattr(tool, "_validate_implementation", lambda _root, _value: None)
    monkeypatch.setattr(tool, "_git", lambda _root, *_args: "a" * 40)

    amendment: dict[str, Any] = {
        "schema": tool._SCHEMA,
        "amendment_id": "fixture-checkpoint-attempt-1",
        "status": tool._STATUS,
        "chronology": "Frozen fixture authority before synthetic execution.",
        "base_protocol": {
            "path": "config/base.json",
            "sha256": base_sha,
            "protocol_digest": base_digest,
        },
        "roadmap": {"path": "plans/roadmap.md", "sha256": roadmap_sha},
        "implementation": {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "file_sha256": {},
        },
        "sealed_results": [
            {
                "arc_id": item.arc_id,
                "path": item.sealed_result_path,
                "sha256": item.sealed_result_sha256,
            }
            for item in specs
        ],
        "raw_tle_inputs": [
            {
                "arc_id": item.arc_id,
                "path": item.tle_default_path,
                "sha256": item.tle_sha256,
                "collected_utc_ns": item.tle_collected_utc_ns,
                "object_count": item.tle_object_count,
            }
            for item in specs
        ],
        "calibration_authority": calibration_authority,
        "numerical_controls": controls,
        "outputs": expected_outputs,
        "execution": tool._EXPECTED_EXECUTION,
        "claim_boundary": tool._EXPECTED_CLAIM_BOUNDARY,
    }
    amendment_path = root / "config/amendment.json"
    amendment_path.parent.mkdir(parents=True, exist_ok=True)
    _rewrite_amendment(amendment_path, amendment)
    return _Fixture(root=root, amendment_path=amendment_path, specs=specs)


def test_authority_validates_exact_inputs_and_denies_claim_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    authority = tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)

    assert tuple(item.label for item in authority.arcs) == ("9981", "150802")
    assert authority.amendment["calibration_authority"]["c2_complete"] is False
    assert authority.amendment["claim_boundary"]["identity_claimed"] is False

    document = json.loads(fixture.amendment_path.read_text())
    document["claim_boundary"]["identity_claimed"] = True
    _rewrite_amendment(fixture.amendment_path, document)
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="claim denials"):
        tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    (
        ("execution", "attempt_number", True, "execution authority"),
        ("claim_boundary", "identity_claimed", 0, "claim denials"),
        (
            "numerical_controls",
            "persistence",
            {"zstandard_level": True, "zstandard_threads": 0},
            "numerical controls",
        ),
    ),
)
def test_authority_comparisons_are_json_type_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
    message: str,
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    document = json.loads(fixture.amendment_path.read_text())
    document[section][key] = value
    _rewrite_amendment(fixture.amendment_path, document)

    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match=message):
        tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)


def test_only_canonical_amendment_and_outputs_are_authorized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    alternate = fixture.root / "config/alternate-amendment.json"
    alternate.write_bytes(fixture.amendment_path.read_bytes())
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="canonical"):
        tool.validate_checkpoint_execution_amendment(fixture.root, alternate)

    document = json.loads(fixture.amendment_path.read_text())
    document["outputs"]["report_path"] = "reports/another.md"
    _rewrite_amendment(fixture.amendment_path, document)
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="output inventory"):
        tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)


def test_tle_override_must_match_and_outputs_are_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    first = fixture.specs[0]
    matching = _write_bytes(
        fixture.root,
        "alternate/9981.tle",
        (fixture.root / first.tle_default_path).read_bytes(),
    )
    authority = tool.validate_checkpoint_execution_amendment(
        fixture.root,
        fixture.amendment_path,
        tle_path_overrides={first.arc_id: matching},
    )
    assert authority.arcs[0].tle_path == matching.resolve()

    wrong = _write_bytes(fixture.root, "alternate/wrong.tle", b"wrong")
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="TLE override"):
        tool.validate_checkpoint_execution_amendment(
            fixture.root,
            fixture.amendment_path,
            tle_path_overrides={first.arc_id: wrong},
        )

    authority.artifact_directory.mkdir(parents=True)
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="already exists"):
        tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)


def test_implementation_binding_checks_working_and_committed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_bytes(root, "uv.lock", b"fixture lock\n")
    payload = b"bound implementation\n"
    path = _write_bytes(root, "impl.py", payload)
    digest = sha256_digest(payload)
    commit = "1" * 40
    tree = "2" * 40
    monkeypatch.setattr(tool, "_IMPLEMENTATION_FILES", ("impl.py",))
    monkeypatch.setattr(tool, "DEFAULT_AMENDMENT", Path("config/amendment.json"))
    repository_state = {
        "diff": "config/amendment.json",
        "status": "",
    }

    def fake_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return "3" * 40
        if args == ("rev-parse", f"{commit}^{{tree}}"):
            return tree
        if args == ("diff", "--name-only", f"{commit}..HEAD"):
            return repository_state["diff"]
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return repository_state["status"]
        raise AssertionError(args)

    monkeypatch.setattr(tool, "_git", fake_git)
    monkeypatch.setattr(tool, "_git_blob_sha256", lambda *_args: digest)
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )
    binding = {
        "commit": commit,
        "tree": tree,
        "file_sha256": {"impl.py": digest},
        "runtime_environment": tool._runtime_environment(root),
    }

    tool._validate_implementation(root, binding)

    repository_state["diff"] = "config/amendment.json\nsrc/unbound.py"
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="outside"):
        tool._validate_implementation(root, binding)
    repository_state["diff"] = "config/amendment.json"
    repository_state["status"] = "?? untracked.py"
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="clean worktree"):
        tool._validate_implementation(root, binding)
    repository_state["status"] = ""

    drifted_runtime = copy.deepcopy(binding)
    drifted_runtime["runtime_environment"]["package_versions"]["numpy"] = "0.0"
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="runtime"):
        tool._validate_implementation(root, drifted_runtime)

    path.write_bytes(b"drift")
    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="working file"):
        tool._validate_implementation(root, binding)


@pytest.mark.parametrize(
    ("injected_error", "expected_error"),
    (
        (OSError("injected publication failure"), tool.SatelliteTrackingCheckpointAuthorityError),
        (KeyboardInterrupt(), KeyboardInterrupt),
    ),
)
def test_publication_is_atomic_no_replace_and_interrupt_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injected_error: BaseException,
    expected_error: type[BaseException],
) -> None:
    stage_artifacts = tmp_path / "stage-artifacts"
    stage_artifacts.mkdir()
    (stage_artifacts / "one.json").write_bytes(b"one")
    (stage_artifacts / "two.png").write_bytes(b"two")
    stage_report = tmp_path / "stage-report.md"
    stage_report.write_text("report\n")
    artifact_directory = tmp_path / "published-artifacts"
    report_path = tmp_path / "published-report.md"

    def fail_report_link(_source: Path, _destination: Path) -> None:
        raise injected_error

    monkeypatch.setattr(tool.os, "link", fail_report_link)
    with pytest.raises(expected_error):
        tool._publish_staged_outputs(
            stage_artifacts=stage_artifacts,
            artifact_directory=artifact_directory,
            stage_report=stage_report,
            report_path=report_path,
        )

    assert not artifact_directory.exists()
    assert not report_path.exists()
    assert stage_artifacts.is_dir()
    assert stage_report.is_file()


def test_atomic_directory_publication_never_replaces_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "source.txt").write_text("source\n")
    (destination / "owned.txt").write_text("owned\n")

    with pytest.raises(OSError):
        tool._rename_directory_no_replace(source, destination)

    assert (source / "source.txt").read_text() == "source\n"
    assert (destination / "owned.txt").read_text() == "owned\n"


def test_publication_rolls_back_interrupt_after_atomic_directory_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_artifacts = tmp_path / "stage-artifacts"
    stage_artifacts.mkdir()
    (stage_artifacts / "result.json").write_text("result\n")
    stage_report = tmp_path / "stage-report.md"
    stage_report.write_text("report\n")
    artifact_directory = tmp_path / "published-artifacts"
    report_path = tmp_path / "published-report.md"
    real_rename = tool._rename_directory_no_replace
    rename_calls = 0

    def move_then_interrupt(source: Path, destination: Path) -> None:
        nonlocal rename_calls
        rename_calls += 1
        real_rename(source, destination)
        if rename_calls == 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(tool, "_rename_directory_no_replace", move_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        tool._publish_staged_outputs(
            stage_artifacts=stage_artifacts,
            artifact_directory=artifact_directory,
            stage_report=stage_report,
            report_path=report_path,
        )

    assert stage_artifacts.is_dir()
    assert (stage_artifacts / "result.json").is_file()
    assert not artifact_directory.exists()
    assert not report_path.exists()


def test_atomic_receipt_update_preserves_previous_document_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "receipt.json"
    tool._write_json_exclusive(receipt, {"status": "running"})
    monkeypatch.setattr(
        tool.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("injected replace failure")),
    )

    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="atomic JSON"):
        tool._write_json_atomic(receipt, {"status": "complete"})

    assert json.loads(receipt.read_text()) == {"status": "running"}
    assert tuple(tmp_path.glob(".receipt.json.*.tmp")) == ()


def test_temporary_cleanup_failure_is_not_silently_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_tree = tmp_path / "temporary-tree"
    temporary_tree.mkdir()
    monkeypatch.setattr(
        tool.shutil,
        "rmtree",
        lambda _path: (_ for _ in ()).throw(OSError("injected cleanup failure")),
    )

    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="removed"):
        tool._remove_temporary_tree(temporary_tree)

    assert temporary_tree.is_dir()


def _summary(label: str) -> dict[str, Any]:
    number = 101 if label == "9981" else 201
    return {
        "observation_count": 6,
        "true_candidate_count": 3,
        "tau_state_count": 3,
        "c1_profiled_tau_pair_distance_matrix_count": 6,
        "c1_profiled_tau_pair_observation_evaluations": 576,
        "c1_125ms_profiled_tau_final_component_count": 2,
        "c1_125ms_profiled_tau_final_largest_component_size": 2,
        "c1_125ms_profiled_tau_final_singleton_component_count": 1,
        "c1_125ms_profiled_tau_final_edge_count": 1,
        "c1_125ms_profiled_tau_final_median_local_candidate_count": 2.0,
        "c1_125ms_tau_zero_drift_final_median_local_candidate_count": 2.0,
        "c1_125ms_tau_zero_drift_final_median_soft_effective_candidate_count": 1.5,
        "highlighted_candidate_components": {str(number): (number, number + 1)},
        "wrong_epoch_observe_only": {
            "-500": {
                "final_minimum_nearest_any_rms_hz": 12.0,
                "final_median_nearest_any_rms_hz": 20.0,
                "observe_only": True,
                "identity_gate_applied": False,
                "true_field_tau_s": 0.0,
                "comparison_field_tau_s": 0.0,
                "tau_profiled": False,
            },
            "500": {
                "final_minimum_nearest_any_rms_hz": 13.0,
                "final_median_nearest_any_rms_hz": 21.0,
                "observe_only": True,
                "identity_gate_applied": False,
                "true_field_tau_s": 0.0,
                "comparison_field_tau_s": 0.0,
                "tau_profiled": False,
            },
        },
        "c2_covariance_calibrated": False,
        "c2_receiver_nuisance_parameters_calibrated": False,
        "c2_opportunity_inventory_complete": False,
        "c2_missing_opportunities_retained": False,
        "c2_coverage_conditioned_on_observed_rows": True,
        "c2_complete": False,
        "c2_abstention_recommended": True,
        "c2_abstention_diagnostics": ("incomplete-opportunity-inventory",),
        "c2_final_family_mass": {
            "null": 0.2,
            "catalogue-orbit": 0.5,
            "radio-polynomial": 0.3,
        },
        "c3_outcome": "ambiguity",
        "c3_outcome_reason": "multiple-connected-neighborhoods-required",
        "c3_candidate_posterior_probability": 0.8,
        "c3_h0_radio_or_unassigned_posterior_probability": 0.2,
        "c3_effective_candidate_connected_neighborhood_count": 2.0,
        "c3_top_candidate_states": (
            {
                "catalog_numbers": (number,),
                "tau_s": (0.0,),
                "posterior_probability": 0.4,
                "connected_neighborhood_label": canonical_digest({"class": label}),
            },
        ),
        "c3_top_candidate_connected_neighborhoods": (
            {
                "catalog_numbers": (number, number + 1),
                "posterior_probability": 0.6,
                "within_candidate_probability": 0.75,
                "connected_neighborhood_label": canonical_digest({"class": label}),
            },
        ),
        "c3_optional_family_availability": (),
        "posterior_probability_calibrated": False,
        "identity_claimed": False,
    }


def test_execution_is_sequential_exclusive_and_publishes_full_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "load_satellite_pnt_long_arc_protocol", lambda *_a, **_k: object())
    order: list[str] = []

    def fake_process_arc(**kwargs: Any) -> tool._ArcPublishedReceipt:
        arc = kwargs["arc"]
        stage = kwargs["stage_artifacts"]
        order.append(arc.label)
        result = stage / f"{arc.label}-checkpoint-result.json.zst"
        result.write_bytes(f"result-{arc.label}".encode())
        figures: list[dict[str, Any]] = []
        for index, kind in enumerate(
            (
                "candidate-count",
                "closest-pairs",
                "tau-envelope",
                "wrong-epoch-alternatives",
                "c3-family-class-mass",
            )
        ):
            name = f"{arc.label}-{kind}.png"
            payload = f"png-{arc.label}-{index}".encode()
            (stage / name).write_bytes(payload)
            figures.append(
                {
                    "figure_kind": kind,
                    "file_name": name,
                    "sha256": sha256_digest(payload),
                }
            )
        digest = canonical_digest({"arc": arc.label})
        return tool._ArcPublishedReceipt(
            label=arc.label,
            arc_id=arc.arc_id,
            result_file=result.name,
            result_sha256=tool._sha256_file(result),
            result_byte_size=result.stat().st_size,
            c1_result_digest=digest,
            c2_result_digest=digest,
            c1_connected_neighborhood_binding_digest=digest,
            c3_result_digest=digest,
            figures=tuple(figures),
            summary=_summary(arc.label),
        )

    monkeypatch.setattr(tool, "_process_arc", fake_process_arc)
    artifact, report, receipt = tool.execute_authorized_checkpoints(
        fixture.root, fixture.amendment_path
    )

    assert order == ["9981", "150802"]
    assert (artifact / "manifest.json").is_file()
    report_text = report.read_text()
    assert report_text.count("![Arc ") == 10
    assert "figures/checkpoint-attempt-1/9981-candidate-count.png" in report_text
    assert "C2 — common evidence scale | **Incomplete (3/19).**" in report_text
    assert "detached holdout forecast-RMS sensitivity scales" in report_text
    assert "C1 -500 s nearest-curve" in report_text
    assert "Highlighted NORAD 101" in report_text
    assert "Top provisional C3 candidate states" in report_text
    assert "Top provisional C3 connected neighborhoods" in report_text
    assert "does not execute distinct rolling-origin refits" in report_text
    receipt_payload = json.loads(receipt.read_text())
    assert receipt_payload["status"] == "complete"
    assert receipt_payload["c2_complete"] is False
    output = capsys.readouterr().out
    assert "phase=preflight" in output
    assert "phase=publish-complete" in output

    with pytest.raises(tool.SatelliteTrackingCheckpointAuthorityError, match="already exists"):
        tool.execute_authorized_checkpoints(fixture.root, fixture.amendment_path)


def test_one_arc_scientific_orchestration_uses_all_checkpoint_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _authority_fixture(tmp_path, monkeypatch)
    authority = tool.validate_checkpoint_execution_amendment(fixture.root, fixture.amendment_path)
    spec = fixture.specs[0]
    arc = authority.arcs[0]
    stage = tmp_path / "stage"
    stage.mkdir()
    calls: list[str] = []
    compact_storage_paths: list[Path] = []
    observation = SimpleNamespace(
        arc_id=arc.arc_id,
        tle_snapshot=SimpleNamespace(
            provider="space-track",
            collected_utc_ns=spec.tle_collected_utc_ns,
            raw_sha256=spec.tle_sha256,
            object_count=spec.tle_object_count,
        ),
    )
    protocol = SimpleNamespace(
        observations=(observation,),
        observer=SimpleNamespace(
            latitude_deg=1.0,
            longitude_deg=2.0,
            altitude_m=3.0,
            name="fixture-site",
        ),
        models=SimpleNamespace(nominal_rf_hz=11_440_312_498.0),
        protocol_digest=canonical_digest({"protocol": "fixture"}),
    )
    support = SimpleNamespace(content_digest=canonical_digest({"support": 1}))
    bundle = SimpleNamespace(prediction_support=support, graph=object())
    bank_snapshot = SimpleNamespace(digest=spec.tle_sha256)
    banks = tuple(
        SimpleNamespace(
            field_delta_s=delta,
            content_digest=canonical_digest({"bank": delta}),
            support=support,
            tle_snapshot=bank_snapshot,
        )
        for delta in (-500, 0, 500)
    )
    views = tuple(
        SimpleNamespace(field_delta_s=delta, pure_array_view=True) for delta in (-500, 0, 500)
    )
    c1 = SimpleNamespace(content_digest=canonical_digest({"c1": 1}))
    c2 = SimpleNamespace(
        content_digest=canonical_digest({"c2": 1}),
        prediction_bank_content_digest=banks[1].content_digest,
    )
    binding = SimpleNamespace(content_digest=canonical_digest({"binding": 1}))
    c3 = SimpleNamespace(result_digest=canonical_digest({"c3": 1}))

    monkeypatch.setattr(tool, "load_registered_long_arc_graph", lambda *_a, **_k: bundle)
    monkeypatch.setattr(
        tool,
        "load_sealed_response_free_bank_inventory",
        lambda *_a, **_k: SimpleNamespace(),
    )

    def fake_rebuild(*_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]:
        calls.append("rebuild")
        compact_storage = _kwargs["storage_directory"]
        assert compact_storage.is_dir()
        compact_storage_paths.append(compact_storage)
        policy = _kwargs["compact_policy"]
        assert policy.maximum_array_storage_bytes_total == 6_000_000_000
        return banks

    def fake_c1(**_kwargs: Any) -> Any:
        calls.append("c1")
        assert _kwargs["true_field_bank"] is views[1]
        assert _kwargs["wrong_field_banks"] == (views[0], views[2])
        return c1

    def fake_c2(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("c2")
        assert _args[1] is views[1]
        return c2

    def fake_binding(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("binding")
        return binding

    def fake_c3(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("c3")
        return c3

    def fake_write(path: Path, **_kwargs: Any) -> None:
        calls.append("serialize")
        path.write_bytes(b"zstd-result")

    def fake_figures(*_args: Any, **kwargs: Any) -> tuple[dict[str, Any], ...]:
        calls.append("render-c1")
        result = []
        for kind in (
            "candidate-count",
            "closest-pairs",
            "tau-envelope",
            "wrong-epoch-alternatives",
        ):
            name = f"9981-{kind}.png"
            (kwargs["output_directory"] / name).write_bytes(b"png")
            result.append({"figure_kind": kind, "file_name": name})
        return tuple(result)

    def fake_c3_figure(_result: Any, *, path: Path, arc_label: str) -> dict[str, Any]:
        calls.append("render-c3")
        path.write_bytes(b"png")
        return {"figure_kind": "c3-family-class-mass", "file_name": path.name}

    monkeypatch.setattr(
        tool,
        "iter_rebuilt_digest_identical_compact_field_banks",
        fake_rebuild,
    )
    monkeypatch.setattr(
        tool,
        "open_compact_catalogue_prediction_array_bank_view",
        lambda bank: nullcontext(views[bank.field_delta_s // 500 + 1]),
    )
    monkeypatch.setattr(tool, "analyze_candidate_observability", fake_c1)
    monkeypatch.setattr(tool, "score_registered_long_arc_model_families", fake_c2)
    monkeypatch.setattr(tool, "_c1_connected_neighborhood_binding", fake_binding)
    monkeypatch.setattr(tool, "close_long_arc_block_evidence_run", fake_c3)
    monkeypatch.setattr(tool, "verify_long_arc_hypothesis_closure_result", lambda _x: None)
    monkeypatch.setattr(tool, "_write_arc_result_zst", fake_write)
    monkeypatch.setattr(tool, "render_catalogue_observability_figures", fake_figures)
    monkeypatch.setattr(tool, "_figure_receipt_payload", lambda value: value)
    monkeypatch.setattr(tool, "_render_c3_figure", fake_c3_figure)
    monkeypatch.setattr(tool, "_compact_arc_summary", lambda *_a: _summary("9981"))

    receipt = tool._process_arc(
        authority=authority,
        protocol=protocol,
        protocol_path=fixture.root / "config/base.json",
        spec=spec,
        arc=arc,
        stage_artifacts=stage,
    )

    assert calls == [
        "rebuild",
        "c1",
        "c2",
        "binding",
        "c3",
        "serialize",
        "render-c1",
        "render-c3",
    ]
    assert receipt.result_sha256 == tool._sha256_file(stage / receipt.result_file)
    assert len(receipt.figures) == 5
    assert compact_storage_paths and not compact_storage_paths[0].exists()


def test_c3_neighborhood_binding_uses_complete_profiled_tau_atlas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bank_digest = canonical_digest({"bank": "true"})
    atlas_digest = canonical_digest({"atlas": "profiled-tau"})
    floor = SimpleNamespace(
        history_ms=125.0,
        floor_hz=57.75380979657822,
        source_digest=canonical_digest({"floor": 125}),
        calibrated=False,
        identity_gate_applied=False,
        final_components=(
            SimpleNamespace(component_index=0, catalog_numbers=(101,)),
            SimpleNamespace(component_index=1, catalog_numbers=(202,)),
        ),
    )
    atlas = SimpleNamespace(
        true_field_prediction_bank_digest=bank_digest,
        candidate_numbers=(101, 202),
        tau_values_s=(0.0,),
        observation_count=6,
        nuisance_model="offset-plus-ridge-drift-v1",
        drift_prior_sigma_hz_per_s=20.0,
        reference_measurement_sigma_hz=50.0,
        tau_pair_distance_matrix_count=1,
        pair_observation_evaluations=24,
        complete_tau_cross_product_evaluated=True,
        floor_neighborhoods=(floor,),
        content_digest=atlas_digest,
        tau_pairing_semantics="independent-complete-cross-product-minimum-v1",
        candidate_node_semantics=("one-node-per-catalogue-identity-all-tau-states-unified-v1"),
        threshold_graph_semantics=("edge-if-any-profiled-state-pair-within-floor-v1"),
        measured_response_accessed=False,
        candidate_universe_selected_from_response=False,
        identity_claimed=False,
    )
    c1 = SimpleNamespace(
        profiled_tau_candidate_identity_atlas=atlas,
        true_field_prediction_bank_digest=bank_digest,
        work_receipt=SimpleNamespace(
            profiled_tau_pair_distance_matrix_count=1,
            profiled_tau_pair_observation_evaluations=24,
        ),
        content_digest=canonical_digest({"c1": "profiled-tau"}),
        candidate_numbers=(101, 202),
    )
    c2 = SimpleNamespace(
        prediction_bank_content_digest=bank_digest,
        receiver_nuisance_basis_digest=canonical_digest({"c2": "receiver-basis"}),
        state_receipts=(
            SimpleNamespace(
                state_kind="catalogue",
                state_id=canonical_digest({"state": 101}),
                catalog_number=101,
                tau_s=0.0,
            ),
            SimpleNamespace(
                state_kind="catalogue",
                state_id=canonical_digest({"state": 202}),
                catalog_number=202,
                tau_s=0.0,
            ),
        ),
    )
    captured: dict[str, Any] = {}

    def fake_seal(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(content_digest=canonical_digest({"binding": "fixture"}))

    monkeypatch.setattr(
        tool,
        "seal_long_arc_catalogue_connected_neighborhood_binding",
        fake_seal,
    )
    tool._c1_connected_neighborhood_binding(c1, c2)

    receipts = captured["receipts"]
    assert captured["source_profiled_tau_atlas_digest"] == atlas_digest
    assert captured["c2_receiver_nuisance_basis_digest"] == c2.receiver_nuisance_basis_digest
    assert captured["tau_values_s"] == (0.0,)
    assert captured["complete_tau_cross_product_evaluated"] is True
    assert receipts[0].connected_neighborhood_label != (receipts[1].connected_neighborhood_label)


@dataclass(frozen=True)
class _Binding:
    content_digest: str


@dataclass(frozen=True)
class _Closure:
    result_digest: str


def test_arc_result_is_streamed_as_valid_zstandard_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = canonical_digest({"fixture": 1})
    c1 = SimpleNamespace(content_digest=digest)
    c2 = SimpleNamespace(content_digest=digest)
    binding = _Binding(content_digest=digest)
    closure = _Closure(result_digest=digest)
    monkeypatch.setattr(tool, "verify_long_arc_hypothesis_closure_result", lambda _x: None)
    monkeypatch.setattr(
        tool,
        "candidate_observability_result_payload",
        lambda _x: {"content_digest": digest},
    )
    monkeypatch.setattr(
        tool,
        "long_arc_block_evidence_run_payload",
        lambda _x: {"content_digest": digest},
    )
    arc = tool.AuthorizedCheckpointArc(
        label="9981",
        arc_id="fixture-arc",
        sealed_result_path=tmp_path / "sealed",
        sealed_result_sha256=digest,
        tle_path=tmp_path / "tle",
        tle_sha256=digest,
    )
    path = tmp_path / "result.json.zst"
    tool._write_arc_result_zst(
        path,
        arc=arc,
        c1_result=c1,
        c2_result=c2,
        connected_neighborhood_binding=binding,
        c3_result=closure,
        compression_controls={"zstandard_level": 1, "zstandard_threads": 0},
    )

    with path.open("rb") as raw, zstd.ZstdDecompressor().stream_reader(raw) as reader:
        document = json.load(reader)
    assert document["schema"] == tool._RESULT_SCHEMA
    assert document["arc_id"] == "fixture-arc"
    assert document["c2_complete"] is False
    assert document["identity_claimed"] is False
    assert document["wrong_epoch_is_gate"] is False


def test_c3_figure_is_deterministic_and_uses_only_final_neighborhood_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family_names = (
        "h0-radio-null",
        "h1-single-candidate",
        "h1-switch",
        "k2-two-candidate",
    )

    def summary(duration: float, candidate_mass: float, *, final: bool) -> Any:
        families = tuple(
            SimpleNamespace(family=family, posterior_probability=probability)
            for family, probability in zip(
                family_names,
                (1.0 - candidate_mass, candidate_mass, 0.0, 0.0),
                strict=True,
            )
        )
        neighborhoods = (
            SimpleNamespace(
                family="h1-single-candidate",
                connected_neighborhood_label=canonical_digest({"neighborhood": 1}),
                posterior_probability=candidate_mass * 0.75,
            ),
            SimpleNamespace(
                family="h1-single-candidate",
                connected_neighborhood_label=canonical_digest({"neighborhood": 2}),
                posterior_probability=candidate_mass * 0.25,
            ),
        )
        return SimpleNamespace(
            cumulative_duration_s=duration,
            family_posterior=families,
            connected_neighborhood_summary_status=(
                "available-final-prefix" if final else "suppressed-final-prefix-map"
            ),
            connected_neighborhood_posterior=neighborhoods if final else (),
        )

    rolling = (summary(1.0, 0.4, final=False), summary(2.0, 0.7, final=True))
    result = SimpleNamespace(
        rolling_summaries=rolling,
        final_summary=rolling[-1],
        result_digest=canonical_digest({"closure": "fixture"}),
    )
    monkeypatch.setattr(tool, "verify_long_arc_hypothesis_closure_result", lambda _x: None)
    first = tool._render_c3_figure(
        result,
        path=tmp_path / "first.png",
        arc_label="fixture",
    )
    second = tool._render_c3_figure(
        result,
        path=tmp_path / "second.png",
        arc_label="fixture",
    )

    assert first["sha256"] == second["sha256"]
    assert first["plotted_candidate_connected_neighborhood_count"] == 2
    assert first["posterior_probability_calibrated"] is False
    assert first["identity_claimed"] is False
