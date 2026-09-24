from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("iteration18_run_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def fit(loss: float, *, converged: bool = True) -> dict:
    return {
        "selection_objective": loss,
        "exact_full_observation_capped_loss": loss,
        "converged": converged,
        "rate_boundary_count": 0,
    }


def test_tau_grid_has_nine_nodes_and_exact_overlap_after_edge_translation() -> None:
    m = module()
    first = m.tau_grid(-0.75)
    second = m.tau_grid(first[-1])
    assert first == pytest.approx([-0.95, -0.90, -0.85, -0.80, -0.75, -0.70, -0.65, -0.60, -0.55])
    assert len(second) == 9
    assert set(first) & set(second) == {-0.75, -0.70, -0.65, -0.60, -0.55}
    assert len(set(second) - set(first)) == 4


def test_timing_winner_requires_convergence_and_reports_grid_edge() -> None:
    m = module()
    rows = [
        {"tau_s": tau, "rate_only": fit(abs(tau + 0.65))}
        for tau in m.tau_grid(-0.75)
    ]
    winner, edge = m.timing_winner(rows, -0.75)
    assert winner["tau_s"] == pytest.approx(-0.65)
    assert edge is False

    rows[0]["rate_only"] = fit(-1.0)
    winner, edge = m.timing_winner(rows, -0.75)
    assert winner["tau_s"] == pytest.approx(-0.95)
    assert edge is True

    for row in rows:
        row["rate_only"]["converged"] = False
    with pytest.raises(ValueError, match="no converged timing node"):
        m.timing_winner(rows, -0.75)


def test_lattice_and_weighted_combination_use_parent_relative_coordinates() -> None:
    m = module()

    class Driver:
        @staticmethod
        def local_coordinate(origin, east, north):
            return {
                "latitude_deg": origin["latitude_deg"] + north,
                "longitude_deg": origin["longitude_deg"] + east,
            }

    points = m.lattice(Driver, {"latitude_deg": 1.0, "longitude_deg": 2.0}, (0, 0), 0.5)
    assert len(points) == 9
    assert m.is_edge(points[0], (0, 0), 0.5)
    assert not m.is_edge(points[4], (0, 0), 0.5)
    point = points[4]
    audits = [
        {**point, "group_id": "20260921_00", "rate_only": fit(0.02)},
        {**point, "group_id": "20260921_16", "rate_only": fit(0.10)},
    ]
    row = m.combine(audits, [point])[0]
    expected = 0.2742 * 0.02 + 0.7258 * 0.10
    assert row["weighted_selection_objective"] == pytest.approx(expected)
    audits[0]["rate_only"]["converged"] = False
    with pytest.raises(ValueError, match="no converged coordinate"):
        m.combine(audits, [point])


def test_checkpoint_validation_rejects_stale_context(tmp_path: Path) -> None:
    m = module()
    checkpoint = tmp_path / "timing.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema": m.CHECKPOINT_SCHEMA,
                "kind": "timing",
                "context": {"plan_sha256": "sha256:old"},
                "group_id": "20260921_00",
                "translation_index": 0,
            }
        )
    )
    with pytest.raises(ValueError, match="stale or malformed"):
        m.validate_checkpoint(
            checkpoint,
            context={"plan_sha256": "sha256:new"},
            kind="timing",
            group_id="20260921_00",
            translation_index=0,
        )


def test_timing_seal_validation_never_accepts_reference_use(tmp_path: Path) -> None:
    m = module()
    seal = tmp_path / "timing-refresh.json"
    seal.write_text(
        json.dumps(
            {
                "schema": m.TIMING_SCHEMA,
                "context": {"parent": "x"},
                "reference_used_for_fit": True,
            }
        )
    )
    seal.with_suffix(".json.sha256").write_text(
        __import__("hashlib").sha256(seal.read_bytes()).hexdigest() + "\n"
    )
    with pytest.raises(ValueError, match="not reference-free"):
        m.load_timing_seal(seal, context={"parent": "x"})


def test_timing_seal_requires_matching_sidecar(tmp_path: Path) -> None:
    m = module()
    seal = tmp_path / "timing-refresh.json"
    seal.write_text(
        json.dumps(
            {
                "schema": m.TIMING_SCHEMA,
                "context": {"parent": "x"},
                "reference_used_for_fit": False,
            }
        )
    )
    with pytest.raises(ValueError, match="sidecar is missing"):
        m.load_timing_seal(seal, context={"parent": "x"})
    seal.with_suffix(".json.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(ValueError, match="does not match"):
        m.load_timing_seal(seal, context={"parent": "x"})


def test_geographic_checkpoint_is_bound_to_timing_digest_and_taus(tmp_path: Path) -> None:
    m = module()
    seal = tmp_path / "timing-refresh.json"
    seal.write_text("sealed timing bytes\n")
    timing = {"selected_taus_s": {"20260921_00": -0.7, "20260921_16": -0.45}}
    context = m.geographic_checkpoint_context({"plan": "p"}, seal, timing)
    assert context["timing_sha256"] == m.digest(seal)
    assert context["selected_taus_s"] == timing["selected_taus_s"]

    checkpoint = tmp_path / "stage.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema": m.CHECKPOINT_SCHEMA,
                "kind": "geographic",
                "context": context,
                "stage_index": 0,
                "translation_index": 0,
            }
        )
    )
    changed = {**context, "selected_taus_s": {**timing["selected_taus_s"], "20260921_16": -0.4}}
    with pytest.raises(ValueError, match="stale or malformed"):
        m.validate_checkpoint(
            checkpoint,
            context=changed,
            kind="geographic",
            stage_index=0,
            translation_index=0,
        )


def test_qualification_requires_interior_timing_and_geographic_winners() -> None:
    path = Path(__file__).with_name("qualify.py")
    spec = importlib.util.spec_from_file_location("iteration18_qualify_test", path)
    assert spec and spec.loader
    qualifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualifier)
    timing = {
        "qualified": True,
        "selected_taus_s": {"20260921_00": -0.7, "20260921_16": -0.45},
        "groups": {
            group: {"qualified": True, "steps": [{"winner_on_edge": False}]}
            for group in qualifier.GROUPS
        },
    }
    inference = {"geographic": {"qualified": True, "steps": [{"winner_on_edge": False}]}}
    assert qualifier.timing_interior(timing)
    assert qualifier.geographic_interior(inference)
    timing["groups"]["20260921_00"]["steps"][-1]["winner_on_edge"] = True
    assert not qualifier.timing_interior(timing)
    inference["geographic"]["steps"][-1]["winner_on_edge"] = True
    assert not qualifier.geographic_interior(inference)


def test_evaluator_distance_is_zero_at_reference() -> None:
    path = Path(__file__).with_name("evaluate_postseal.py")
    spec = importlib.util.spec_from_file_location("iteration18_evaluate_test", path)
    assert spec and spec.loader
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    assert evaluator.distance_km(*evaluator.REFERENCE) == 0.0
