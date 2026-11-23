import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


def test_orbit_retry_only_for_original_interpolation_exception(monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    trial = importlib.import_module("full_short_orbit_transfer")
    msg = "Traceback\nValueError: orbit phase interpolation never extrapolates\n"
    assert trial.is_interpolation_failure(dict(exit_code=1, stderr=msg))
    assert not trial.is_interpolation_failure(dict(exit_code=0, stderr=msg))
    assert not trial.is_interpolation_failure(dict(exit_code=1, stderr="FileNotFoundError"))


def test_native_geography_is_scoped_and_counted(monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    runner = importlib.import_module("full_short_run")
    module = importlib.import_module("dense_geographic_projection")
    initial = object()
    scorer = SimpleNamespace(phase_linear_frequency=initial)
    native = SimpleNamespace(counts={"calls": 2})
    def bind(path, digest, ordinary):
        assert path == "pinned" and digest == runner.GEOGRAPHIC_SHA and ordinary is initial
        return native
    monkeypatch.setattr(module, "Projector", bind)
    monkeypatch.setattr(module, "checked_runtime", lambda: (scorer, initial))
    with pytest.raises(RuntimeError):
        with runner.geographic_projection("pinned") as counts:
            assert scorer.phase_linear_frequency is native and counts == native.counts
            raise RuntimeError("solver exited")
    assert scorer.phase_linear_frequency is initial


def test_projected_recovery_keeps_the_original_denominators(monkeypatch):
    monkeypatch.syspath_prepend(str(HERE))
    budget = importlib.import_module("short_graph_budget")
    rows = [dict(case="DS30-0022", stages=[0,0,100], compressed_MB=100),
            dict(case="other", stages=[10,20,2], compressed_MB=100)]
    out = budget.prices(rows, 10, .5, 1, 20)
    assert out["median_and_sum"][1] == pytest.approx((100+23)/132)
    assert out["with_projected_recovery"][1] == pytest.approx((30+23)/132)


def test_saved_orbit_failure_recovery_retains_full_artifact_bindings():
    data = json.loads((HERE / "measurements/full-short-orbit-transfer.json").read_bytes())
    assert data["archived_failure"] == "solver_failed" and data["mode"] == "current"
    assert data["guard_entries"] == [] and data["binding"]["identical_probe_rows"]
    assert data["terminal"]["native_sha256"] == data["binding"]["source_digest"]
    assert data["decision"] == "complete" and len(data["evidence"]["images"]) == 8
    assert data["solve"]["grid_complete"] and data["solve"]["objective_replay"] == {"c0": 0, "fitted_c": 0}
