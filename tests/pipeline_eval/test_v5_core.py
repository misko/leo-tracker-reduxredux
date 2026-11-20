import gzip
import io
import json
import os
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.qualification import prefix_figures, trace_prefix, v5_prefix_audit
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import v5_core


def install(monkeypatch, name, **symbols):
    monkeypatch.setitem(
        sys.modules, "leo.analysis.localization_v3." + name, SimpleNamespace(**symbols)
    )


def test_initial_branch_uses_only_the_winning_zero_calibration_mask(monkeypatch):
    def node(i):
        return {
            "seed": {"rows": [{"candidate_index": i}], "state": "warm"},
            "aliases": i,
            "center_score": i,
        }

    seeds = [node(i) for i in (2, 1, 3, 4)]

    class Model:
        def __init__(self, scan, cold, sigma, fitted, reference):
            assert cold["seed"]["state"] == "zero" and fitted is False and list(reference) == [0]
            self.alias = cold["aliases"]
            self.rows = cold["seed"]["rows"]

        def residual(self, xy):
            return np.array([float(self.alias)])

        def state(self, xy):
            return self.alias

    visited = []

    def refresh(scan, sigma, cold, arm, *, rounds, iterations):
        i = cold["aliases"]
        visited.append((i, arm, rounds, iterations))
        scores = {1: 5, 2: 2, 3: 2}
        return Model(scan, cold, sigma, False, [0]), {"parameters": [0, 0], "score": scores[i]}, []

    def metrics(model, legacy, arm, xy):
        assert legacy["state"] == 2 and arm == "c0"
        return {"tracks": [{"component": model.alias, "compatible": True}]}

    install(
        monkeypatch,
        "discovery",
        fresh_discovery=lambda scan, sigma, budget: seeds,
        explore=lambda *a, **kw: (seeds[-1]["seed"], None),
        signature=lambda n: n["aliases"],
        zero_state=lambda s: "zero",
    )
    install(monkeypatch, "families", AnchoredFamilies=lambda *args: SimpleNamespace(alias=4))
    install(monkeypatch, "acceptance", actual_metrics=metrics)
    install(monkeypatch, "position", NormalPosition=Model, refreshed=refresh)
    scan = SimpleNamespace(radio_sigma_hz=2, search_region=SimpleNamespace(half_width_km=12.5))
    result, count = v5_core.initial_selection(scan)
    assert count == 3 and visited == [(i, "c0", 5, 48) for i in (1, 2, 3)]
    choice = next(c for c in result["choices"] if c["hypothesis"] == result["selected_hypothesis"])
    assert choice["node"]["aliases"] == 2
    assert choice["arms"] == {"c0": {"metrics": {"tracks": [{"component": 2, "compatible": True}]}}}


@pytest.mark.parametrize("offered", [False, True])
def test_cavity_requires_a_positive_proposal_and_publishes_both_arms(monkeypatch, offered):
    def arms(n):
        return {a: {"endpoint_latlon": [n, i], "RMS_hz": float(n + i)} for i, a in enumerate(ARMS)}

    contexts = []

    def scan(*args):
        contexts.append(args[-1])
        return args[-1]

    monkeypatch.setattr(v5_core, "scan_context", scan)
    monkeypatch.setattr(v5_core, "initial_selection", lambda context: ({"chosen": 1}, 3))

    def recover(context, initial, obs):
        assert context == "genuine_previous" and initial == {"chosen": 1} and obs == [1]
        return {"status": "complete"}

    install(monkeypatch, "conservative_recovery", conservative_recovery=recover)
    install(monkeypatch, "history_policy", history_policy=lambda *a, **k: {"status": "accepted"})
    install(monkeypatch, "signed_context", signed_context=lambda *a, **k: {"arms": arms(1)})

    def fit(context, nominations):
        assert offered
        return {"status": "complete", "policy_arms": arms(2)}

    install(
        monkeypatch,
        "family_cavity",
        cavity_policy=fit,
        nominate_families=lambda c: {
            "status": "complete",
            "families": [
                {"best": {"key": "test"}, "predictive_gain": 1 if offered else 0},
                {"best": None, "predictive_gain": 100},
            ],
        },
    )
    prepared = {
        "status": "inputs_prepared",
        "noise": {},
        "tracks": {"observations": [1], "tracks": [2]},
        "phase_history": {},
        "phase_forecast": {},
        "sky": {"metadata": {"cutoff_utc_ns": 1}},
    }
    got = v5_core.infer(prepared, None, None, {})
    assert contexts == ["previous", "genuine_previous"]
    assert got["status"] == "ok" and got["metrics"]["cavity_offered"] is offered
    assert got["arms"] == {
        a: {"latlon": [int(offered) + 1, i], "rf_rms_hz": float(int(offered) + 1 + i)}
        for i, a in enumerate(ARMS)
    }
    prepared["phase_forecast"] = {"history_sha256": "different"}
    with pytest.raises(ValueError, match="phase history"):
        v5_core.infer(prepared, None, None, {})
    install(
        monkeypatch,
        "conservative_recovery",
        conservative_recovery=lambda *args: {"status": "no_passing_calibration"},
    )
    withheld = v5_core.infer(prepared, None, None, {})
    assert withheld["status"] == "withheld" and all(
        v["latlon"] is None for v in withheld["arms"].values()
    )


def test_archived_stopping_points_cover_the_frozen_cohorts_and_reference():
    cases = prefix_figures.load_rows(prefix_figures.REPORT)
    dev = {k for k, (_, split, _) in cases.items() if split == "development"}
    check = {k for k, (_, split, _) in cases.items() if split == "confirmation"}
    assert len(dev) == 16 and len(check) == 119 and not dev & check
    assert {c for c in check if c.startswith("DS26")} == {
        r["id"] for r in v5_prefix_audit.cohorts()["confirmation"] if r["group"] == "DS26"
    }
    rows = prefix_figures.archived_rows(cases)
    assert len(rows) == 135 * 6 * 2
    assert cases["DS26-0066"][2]["stages"]["final"]["fitted_c"][
        "conditional_rms_hz"
    ] == pytest.approx(69.9421304)
    assert cases["DS26-0046"][2]["stages"]["final"]["fitted_c"]["conditional_rms_hz"] is None
    for arm in ARMS:
        assert any(r["moved_km"] > 1 for r in rows if r["arm"] == arm and r["stage"] == "cavity")
        assert all(r["moved_km"] == 0 for r in rows if r["arm"] == arm and r["stage"] == "final")


def test_checkpoint_extractor_rejects_a_replaced_array():
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("a" * 64, b"changed data")
    with ZipFile(stream) as archive, pytest.raises(ValueError, match="array digest"):
        v5_prefix_audit.value(["array", "sha256:" + "a" * 64], archive)


def test_fresh_diagnostic_exercises_a_position_changed_by_late_recovery():
    case = "DS26-0066"
    _, _, data = prefix_figures.load_rows(prefix_figures.REPORT)[case]
    measured = read_predictions(prefix_figures.REPORT / case / "predictions.jsonl")[case]
    assert case not in prefix_figures.TIMING_IDS and measured["result"]["status"] == "ok"
    for arm in ARMS:
        point = measured["result"]["arms"][arm]["latlon"]
        assert point == data["stages"]["cavity"][arm]["latlon"]
        assert point != data["stages"]["final"][arm]["latlon"]


def test_pair_validation_refuses_different_inputs_and_wrong_checkpoint(tmp_path):
    cases = prefix_figures.load_rows(prefix_figures.REPORT)
    data = []
    for case in prefix_figures.TIMING_IDS:
        for method, stage in zip(prefix_figures.METHODS, ("final", "cavity"), strict=True):
            arms = {a: {"latlon": cases[case][2]["stages"][stage][a]["latlon"]} for a in ARMS}
            data.append(
                dict(
                    id=case,
                    method=method,
                    input_sha256="common",
                    implementation_sha256=method,
                    worker_wall_s=2,
                    result=dict(
                        status="ok",
                        boundary="test",
                        arms=arms,
                        metrics=dict(initial_arm_fits=3, cavity_offered=False),
                    ),
                )
            )
    file = tmp_path / "timing.jsonl.gz"

    def save():
        file.write_bytes(gzip.compress(b"".join(json.dumps(r).encode() + b"\n" for r in data)))

    save()
    fresh, times = prefix_figures.fresh_pairs(file, cases)
    assert len(fresh) == len(times) == 6 and all(t["speedup"] == 1 for t in times)
    data[1]["input_sha256"] = "different"
    save()
    with pytest.raises(ValueError, match="different inputs"):
        prefix_figures.fresh_pairs(file, cases)
    data[1]["input_sha256"] = "common"
    data[1]["implementation_sha256"] = "another worker"
    save()
    with pytest.raises(ValueError, match="different worker versions"):
        prefix_figures.fresh_pairs(file, cases)
    data[1]["implementation_sha256"] = data[1]["method"]
    data[1]["result"]["arms"]["fitted_c"]["latlon"] = [0, 0]
    save()
    with pytest.raises(ValueError, match="disagrees"):
        prefix_figures.fresh_pairs(file, cases)


def test_function_trace_includes_forked_calls(tmp_path, monkeypatch):
    request = tmp_path / "request.json"
    request.write_text("{}")
    monkeypatch.setenv("LEO_PREFIX_TRACE_METHOD", "v5_core")

    def exercise(source, result):
        trace_prefix.v5_lean._read(source)
        pid = os.fork()
        if pid == 0:
            trace_prefix.v5_lean._no_fix("test child")
            os._exit(0)
        assert os.waitpid(pid, 0) == (pid, 0)

    monkeypatch.setattr(v5_core, "worker", exercise)
    trace_prefix.trace_worker(request, tmp_path / "result.json")
    entries = [json.loads(s) for s in (tmp_path / "functions.jsonl").read_text().splitlines()]
    assert {r[1] for r in entries if r[0] == "variants/v5_lean.py"} == {"_read", "_no_fix"}
