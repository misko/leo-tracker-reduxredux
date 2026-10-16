import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ds21_model_a_timing_runtime_v2 as runtime
import model_a_verified_manifest as manifest
import numpy as np
import pytest

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.sequential_group_calibration import SequentialShift


def test_native_serialization_preserves_actual_numpy_receiver_tuple(tmp_path):
    path = tmp_path / "receipt.json"
    value = dict(receivers=(np.int64(0), np.int64(1)), array=np.array([1.25, -3.5]))
    runtime.immutable(path, value)
    assert runtime.read(path) == dict(receivers=[0, 1], array=[1.25, -3.5])


@pytest.mark.parametrize("kind", ["edit", "remove", "add-orphan"])
def test_manifest_detects_changed_bytes_and_added_authority(tmp_path, kind):
    source = tmp_path / "ancestor" / "launches" / "first.json"
    source.parent.mkdir(parents=True)
    source.write_text("original")
    pinned = manifest.pin_qualified_files([source.parent.parent], source_files=[])
    if kind == "edit":
        source.write_text("modified")
    elif kind == "remove":
        source.unlink()
    else:
        (source.parent / "unpaired.json").write_text("orphan")
    with pytest.raises((ValueError, FileNotFoundError)):
        manifest.verify_pinned_files(pinned)


def test_manifest_ignores_explicit_derived_report_and_unrelated_sibling_case(tmp_path):
    case = tmp_path / "case-009"
    case.mkdir()
    (case / "protocol.json").write_text("original")
    pinned = manifest.pin_qualified_files([case], source_files=[])
    (case / "development-errors.json").write_text("derived post-seal error")
    (tmp_path / "case-013").mkdir()
    (tmp_path / "case-013" / "launch.json").write_text("unrelated active case")
    manifest.verify_pinned_files(pinned)


@pytest.fixture
def actual_case(monkeypatch, tmp_path):
    """Real original objectives/fits/core, with only synthetic orbit/input ports."""
    helper_path = Path(__file__).parents[1] / "analysis/test_sequential_group_calibration.py"
    spec = importlib.util.spec_from_file_location("model_a_actual_synthetic_fixture", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    bases = {
        view: helper.model(
            monkeypatch,
            np.tile(
                np.arange(1, 5)
                if view == "low"
                else np.arange(5, 9)
                if view == "high"
                else np.arange(1, 9),
                16,
            ),
        )
        for view in ("low", "high", "all")
    }
    nodes = np.arange(0.0, 151.0, 50.0)
    prepared = {
        view: SimpleNamespace(observations=base.observations) for view, base in bases.items()
    }
    bank, prior = bases["low"].bank, bases["low"].prior
    low_model = runtime.original.objective(prepared["low"], bank, prior, nodes)
    vector = np.zeros(low_model.size)
    vector[2:7] = [-80000, 2, -54000, 1.5, -600]
    calibration = freeze_group_calibration(
        low_model, dict(vector=vector, nuisance=np.zeros(low_model.clock_count))
    )
    shift = SequentialShift((np.int64(0), np.int64(1)), np.array([-24000.0, 38000.0]))
    for view, base in bases.items():
        obs = base.observations
        args = (obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)
        measurements = calibration.predict(*args) + shift.predict(obs.receiver, obs.channel >= 5)
        prepared[view].observations = replace(obs, measured_hz=measurements)
    low_model = runtime.original.objective(prepared["low"], bank, prior, nodes)
    nuisance = np.zeros(low_model.clock_count)
    fit = fit_group_calibration(
        low_model,
        vector,
        nuisance,
        seconds=2,
        iterations=100,
        local_center=[0, 0],
        local_radius_km=25,
    )
    assert fit["converged"]
    low = dict(
        seed=dict(vector=vector, nuisance=nuisance),
        options=dict(
            arm="fitted-c", seconds=20, iterations=600, local_center=[0, 0], local_radius_km=25
        ),
        local_center=[0, 0],
        parameter_count=low_model.size,
        nuisance_count=len(nuisance),
        fit=fit,
        stationary=True,
    )
    low_path = tmp_path / "parent" / "low.json"
    runtime.immutable(low_path, low)
    unused = np.zeros(low_model.size)
    initial = dict(
        starts={
            "A": {
                view: [
                    dict(
                        seed=dict(
                            vector=vector if view == "low" else unused,
                            nuisance=nuisance if view == "low" else [],
                        ),
                        proposal={},
                    )
                    for _ in range(6)
                ]
                for view in ("low", "high", "all")
            }
        }
    )
    initial_path = tmp_path / "parent" / "initialization.json"
    runtime.immutable(initial_path, initial)
    frozen = dict(
        label="SYNTHETIC",
        original=dict(
            initialization=runtime.binding(initial_path),
            inherited_low={str(i): runtime.binding(low_path) for i in range(6)},
        ),
    )
    directory = tmp_path / "runtime"
    runtime.immutable(directory / "protocol.json", dict(synthetic=True))
    case = dict(prepared=prepared, bank=bank, prior=prior, nodes=nodes)
    monkeypatch.setattr(runtime, "read_control", lambda directory: frozen)
    monkeypatch.setattr(runtime, "prepare_case", lambda frozen: case)
    donor = SimpleNamespace(
        predict=lambda times, rf, rx, high: (
            calibration.predict(times, rf, rx, high) + shift.predict(rx, high)
        )
    )
    monkeypatch.setattr(runtime.original, "decode_physical_correction", lambda source: donor)
    return directory, frozen


@pytest.mark.parametrize("condition", runtime.CONDITIONS)
def test_public_runtime_real_core_writes_complete_scientific_terminal(actual_case, condition):
    directory, frozen = actual_case
    unit = f"{condition}-1"
    # No optimizer, sequential-core, serializer, or file writer is mocked.
    result = runtime.run(directory, unit)
    assert result["state"] == "complete"
    assert result["path"]["status"] == "complete"
    assert result["optimizer_calls"] == 2
    assert result["selection"]["stationary"]
    terminal = runtime.read(directory / "units" / unit / "terminal.json")
    assert terminal["path"]["fixed_shift_receivers"] == [0, 1]
    assert runtime.validate_unit(directory, unit, frozen) == terminal


def test_runtime_preserves_known_nonstationary_failure_and_refuses_refit(actual_case):
    directory, _ = actual_case
    unit = f"{runtime.CONDITIONS[1]}-1"
    folder = directory / "units" / unit
    runtime.immutable(folder / "launch.json", dict(orphan=True))
    with pytest.raises(ValueError, match="no retry"):
        runtime.run(directory, unit)
    assert not (folder / "calls").exists()


@pytest.mark.parametrize("outer_failure", ["TypeError", "SliceHardStop"])
def test_recovery_preserves_actual_saved_fits_without_numeric_calls(
    actual_case, monkeypatch, outer_failure
):
    directory, frozen = actual_case
    condition = runtime.CONDITIONS[1]
    original_result = runtime.run(directory, f"{condition}-1")
    old = directory.parent / "failed-v1"
    runtime.immutable(old / "protocol.json", dict(synthetic_failed_v1=True))
    frozen.update(failed_directory=str(old), failed_protocol=runtime.binding(old / "protocol.json"))
    unit = f"{condition}-0"
    folder = old / "units" / unit
    identity = dict(protocol_sha256=frozen["failed_protocol"]["sha256"], unit=unit)
    runtime.immutable(folder / "launch.json", identity)
    runtime.immutable(
        folder / "termination.json", dict(**identity, state="failed", error_type=outer_failure)
    )
    for stage, original_row in original_result["calls"].items():
        row = dict(original_row, **identity, start=0)
        path = folder / "calls" / f"{stage}.json"
        claim = dict(**identity, call=stage)
        runtime.immutable(path, row)
        runtime.immutable(folder / "launches" / path.name, claim)
        runtime.immutable(
            folder / "terminations" / path.name, dict(**claim, call_receipt=runtime.binding(path))
        )
    original_bytes = {str(p): p.read_bytes() for p in folder.rglob("*.json")}
    monkeypatch.setattr(
        runtime.original, "fit_group_calibration", lambda *a, **k: pytest.fail("recovery refitted")
    )
    monkeypatch.setattr(
        runtime.original,
        "fit_sequential_path",
        lambda *a, **k: pytest.fail("recovery reconstructed scientific model"),
    )
    result = runtime.recover(directory, unit)
    assert result["state"] == "recovered-metadata-only"
    assert (
        result["optimizer_calls"]
        == result["recovery_objective_calls"]
        == result["recovery_predictor_calls"]
        == 0
    )
    assert result["reused_v1_optimizer_calls"] == 2
    assert result["selection"]["fit"] == original_result["selection"]["fit"]
    assert {str(p): p.read_bytes() for p in folder.rglob("*.json")} == original_bytes
    assert runtime.validate_unit(directory, unit, frozen)["state"] == "recovered-metadata-only"


def test_rehashed_terminal_wrong_inherited_low_is_rejected(actual_case):
    directory, frozen = actual_case
    unit = f"{runtime.CONDITIONS[1]}-1"
    runtime.run(directory, unit)
    folder = directory / "units" / unit
    terminal_path = folder / "terminal.json"
    value = runtime.read(terminal_path)
    duplicate = directory.parent / "other-low.json"
    duplicate.write_bytes(Path(value["inherited_low"]["path"]).read_bytes())
    value["inherited_low"] = runtime.binding(duplicate)
    terminal_path.write_text(json.dumps(value))
    termination_path = folder / "termination.json"
    status = runtime.read(termination_path)
    status["terminal"] = runtime.binding(terminal_path)
    termination_path.write_text(json.dumps(status))
    with pytest.raises(ValueError, match="own low/unit"):
        runtime.validate_unit(directory, unit, frozen)


@pytest.mark.parametrize(
    "low_stationary, high_stationary, rows",
    [
        (False, True, {"high", "final"}),
        (True, False, {"high", "final"}),
        (True, True, {"high"}),
    ],
)
def test_exact_prerequisite_inventory(low_stationary, high_stationary, rows):
    low = dict(stationary=low_stationary, fit={})
    values = {
        key: dict(stationary=high_stationary if key == "high" else True, fit={}) for key in rows
    }
    with pytest.raises(ValueError, match="prerequisite"):
        runtime.receipt_path(low, values)
