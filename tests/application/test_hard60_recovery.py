import copy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.regional_position_association import RegionalAssociation
from leo.analysis.regional_position_calibration import ReceiverCorrection
from leo.analysis.regional_position_fit import PositionFit
from leo.application import hard60_recovery as recovery
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration
from leo.application.regional_position_report import regional_position_document
from leo.application.regional_position_runner import RegionalSliceExpired, json_value
from tests.analysis.test_regional_position_score import synthetic_inputs


def setup_recovery(monkeypatch, *, fallback=False):
    observations, bank, prior = synthetic_inputs()
    calls = []

    def fitted(vector, value, converged=True):
        return PositionFit(
            np.array(vector),
            value,
            100.0,
            10.0,
            0.0 if converged else 1.0,
            converged,
            False,
            "checked",
            1,
            0.001,
        )

    def bounded(objective, start, **options):
        vector = np.array(start, float)
        if options.get("rf_arm") == "zero-c":
            vector[6] = 0
        converged = not (fallback and options["maximum_seconds"] == 20 and vector[7] != 0)
        answer = fitted(vector, 10.0, converged)
        calls.append((vector.copy(), options))
        return answer, {"best_feasible": answer, "terminal": answer, "solver_success": True}

    monkeypatch.setattr(recovery, "fit_bounded_position", bounded)
    monkeypatch.setattr(
        recovery,
        "Hard60Objective",
        lambda o, b, p, s, **kw: SimpleNamespace(
            bank=b,
            design=np.zeros((len(o.window_ids), 5)),
            evaluate=lambda v: (1.0, np.zeros(10), None),
        ),
    )
    monkeypatch.setattr(
        recovery,
        "receiver_correction",
        lambda *a: ReceiverCorrection(
            np.arange(3), np.zeros((2, 3)), np.zeros(len(observations.window_ids)), ()
        ),
    )
    monkeypatch.setattr(
        recovery,
        "associate_calibration",
        lambda o, b, p, c, **kw: RegionalAssociation(
            (0, 1, 2), c.postfit.vector, {"final": {"assigned": 10}}, 3
        ),
    )
    seed = np.r_[-80.0, -80.0, np.zeros(5), 3.0, 0.0, 0.0]
    original = fitted(seed, 200.0, False)
    good = fitted(np.zeros(10), 100.0)
    points = {
        "point:-80:-80": {
            "result": {
                "bootstrap": {"satellite_indices": [0, 1, 2], "vector": seed.tolist()},
                "fits": {"V16": {"fit": json_value(original), "reason": None}},
            },
            "reason": None,
        },
        "point:0:0": {
            "result": {"bootstrap": {}, "fits": {"V16": {"fit": json_value(good), "reason": None}}},
            "reason": None,
        },
        "point:40:40": {"result": None, "reason": "missing observations"},
    }
    finals = [
        {
            "basin": "point:0:0",
            "method": "V16",
            "arm": arm,
            "start": "association",
            "fit": json_value(good),
            "reason": None,
            "calibration_penalty": 0.0,
            "satellites": bank.numbers.tolist(),
            "association": {"final": {"assigned": 10}},
        }
        for arm in ("fitted-c", "zero-c")
    ]
    result = {
        "searches": {
            "V16": {
                "evaluations": [
                    {"east_km": -80.0, "north_km": -80.0, "spacing_km": 40.0, "score": 200.0},
                    {"east_km": 0.0, "north_km": 0.0, "spacing_km": 40.0, "score": 100.0},
                    {"east_km": 40.0, "north_km": 40.0, "spacing_km": 40.0, "score": 1e100},
                ],
                "deferred_cells": 0,
                "stop_reason": "budget",
            }
        },
        "points": points,
        "finals": finals,
        "failures": [],
        "calibrations": {},
        "basins": [],
    }
    return observations, bank, prior, result, calls


def test_recovery_resumes_preserves_original_candidates_and_matches_c_arms(monkeypatch):
    obs, bank, prior, original, calls = setup_recovery(monkeypatch)
    cache = {}
    interrupt = True

    def stage(key, budget, operation):
        if key in cache:
            return cache[key]
        if interrupt and cache:
            raise RegionalSliceExpired(key)
        cache[key] = {"result": json_value(operation()), "reason": None}
        return cache[key]

    def run():
        return recovery.recover_failed_coarse(
            obs,
            bank,
            prior,
            copy.deepcopy(original),
            score=HARD60_SCORE,
            config=Hard60Configuration(),
            stage=stage,
        )

    with pytest.raises(RegionalSliceExpired):
        run()
    interrupt = False
    result = run()
    assert len(calls) == 9
    assert result["finals"][:2] == original["finals"]
    assert result["points"]["point:0:0"] == original["points"]["point:0:0"]
    assert len(result["searches"]["V16"]["evaluations"]) == 3
    assert result["points"]["point:40:40"] == original["points"]["point:40:40"]
    assert result["recovery"]["attempted_points"] == result["recovery"]["converged_points"] == 1
    for arm in ("fitted-c", "zero-c"):
        added = [r for r in result["finals"][2:] if r["arm"] == arm]
        assert len(added) == 3
        assert all(r["fit"]["converged"] for r in added)
        assert all(r["satellites"] == bank.numbers.tolist() for r in added)
    assert all(options["slope_half_width_hz_s"] == 60 for _, options in calls)
    assert calls[0][1]["maximum_iterations"] == 200
    assert all(options["maximum_iterations"] == 600 for _, options in calls[1:])
    assert run() == result
    assert len(calls) == 9
    doc = regional_position_document(
        result,
        session_id="scan-1",
        input_digest="sha256:" + "a" * 64,
        analysis_digest="sha256:" + "a" * 64,
        evidence_digest="sha256:" + "a" * 64,
        configuration={"protocol": "sacramento-hard60-v1"},
        windows=len(obs.window_ids),
        reference=(38, -122),
        reference_evidence="evaluation only",
    )
    assert doc.diagnostics["recovery"]["attempted_points"] == 1
    assert all(a.selected.source_basin.startswith("recovery:") for a in doc.methods[0].arms)
    assert doc.methods[0].points[-1].objective is None


def test_nonstationary_calibration_uses_zero_timing_fallback(monkeypatch):
    obs, bank, prior, original, calls = setup_recovery(monkeypatch, fallback=True)
    result = recovery.recover_failed_coarse(
        obs,
        bank,
        prior,
        original,
        score=HARD60_SCORE,
        config=Hard60Configuration(),
        stage=lambda key, budget, op: {"result": json_value(op()), "reason": None},
    )
    attempts = result["recovery"]["basins"][0]["calibration"]["result"]["attempts"]
    assert [a["start"] for a in attempts] == ["coarse-best", "zero-timing"]
    assert not attempts[0]["prefit"]["fit"]["converged"]
    assert attempts[1]["postfit"]["fit"]["converged"]
    assert len(result["finals"]) == 8
