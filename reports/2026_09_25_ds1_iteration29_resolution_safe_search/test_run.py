from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

RUNNER = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("i29_test_runner", RUNNER)
assert SPEC is not None and SPEC.loader is not None
run = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run
SPEC.loader.exec_module(run)


def test_plan_and_frozen_inputs_are_valid() -> None:
    run.validate_plan(run.verified_json(run.PLAN))
    found = run.validate_inputs()
    assert found["cache_record_count"] == 250


def test_enu_origin_and_float_keys() -> None:
    latitude, longitude = run.enu_to_geodetic(0.0, 0.0)
    assert abs(latitude - run.ANCHOR[0]) < 1e-10
    assert abs(longitude - run.ANCHOR[1]) < 1e-10
    assert run.float_key(0.0, 0.0) != run.float_key(-0.0, 0.0)


def test_quadratic_surface_recovers_known_stationary_point() -> None:
    rows = []
    for east in (-1.0, 0.0, 1.0):
        for north in (-1.0, 0.0, 1.0):
            rows.append(
                {
                    "east_m": east,
                    "north_m": north,
                    "score": (east - 0.2) ** 2 + 2.0 * (north + 0.3) ** 2,
                }
            )
    fit = run.quadratic_surface(rows, "score")
    assert fit["positive_definite"]
    assert np.allclose([fit["stationary_east_m"], fit["stationary_north_m"]], [0.2, -0.3])


def test_sealed_direction_gate() -> None:
    record = run.direction_checkpoint()
    assert record["gate"]["passed"]
    direction = np.asarray(record["descent_direction_east_north"])
    orthogonal = np.asarray(record["orthogonal_direction_east_north"])
    assert np.isclose(np.linalg.norm(direction), 1.0)
    assert np.isclose(direction @ orthogonal, 0.0)


def test_refinement_rejects_near_duplicate_parabola() -> None:
    optimum = -1185.0783371757898

    class FakeScorer:
        @staticmethod
        def score(coordinates: list[tuple[float, float]]) -> list[dict[str, object]]:
            rows = []
            for east, north in coordinates:
                score = (east - optimum) ** 2
                rows.append(
                    {
                        "coordinate_key": run.float_key(east, north),
                        "east_m": east,
                        "north_m": north,
                        "surrogate_score": score,
                        "actual_material_score": score,
                        "atlas_direct_pooled_score_discrepancy": 0.0,
                        "maximum_atlas_direct_doppler_error_hz": 0.0,
                        "maximum_tail_mass": 0.0,
                    }
                )
            return rows

    scorer = FakeScorer()
    origin = np.zeros(2)
    direction = np.asarray([1.0, 0.0])
    offsets = [-1562.5, -1184.9528937466555, -781.25]
    rows = scorer.score([(offset, 0.0) for offset in offsets])
    scalar_rows = dict(zip(offsets, rows, strict=True))
    result = run.refine_bracket(scorer, origin, direction, scalar_rows, maximum_new=1)
    first = result["history"][0]
    assert first["proposal_method"] != "safeguarded-parabola"
    assert first["proposal_minimum_separation_m"] >= first["proposal_resolution_m"]
