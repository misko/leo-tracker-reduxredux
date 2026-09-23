import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

DIRECTORY = Path(__file__).parents[2] / "tools/research"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location(
    "coverage_benchmark_test", DIRECTORY / "run_fast_coverage_benchmark.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sys.path.pop(0)
SEARCH = sys.modules["search_multiresolution_tle_coverage"]


def test_source_snapshot_survives_later_source_edits(tmp_path, monkeypatch):
    source = tmp_path / "engine.py"
    source.write_text("original version\n")
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(MODULE, "SOURCE_PATHS", [source])
    monkeypatch.setattr(
        MODULE.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="commit\n")
    )
    receipt = MODULE.snapshot_sources(output)
    source.write_text("later version\n")
    frozen = output / "source" / "engine.py"
    assert frozen.read_text() == "original version\n"
    assert receipt["files"]["engine.py"] == MODULE.digest(frozen)
    assert receipt["files"]["engine.py"] != MODULE.digest(source)


@pytest.mark.parametrize("policy,expected_instances", [("cold-per-search", 3), ("shared", 1)])
def test_benchmark_cold_searches_do_not_inherit_scored_cells(
    tmp_path, monkeypatch, policy, expected_instances
):
    instances = []

    class Evaluator:
        def __init__(self, *args, **kwargs):
            self.cache = {}
            instances.append(self)

        def evaluate_points(self, sites):
            rows = []
            for i in range(len(sites)):
                coverage = (SEARCH.ThresholdCoverage(200.0, 10, 1.0, 1, 10.0, 10.0),)
                row = SEARCH.CellScore(float(sites.east_km[i]), float(sites.north_km[i]), coverage)
                self.cache[(float(sites.latitude_deg[i]), float(sites.longitude_deg[i]))] = row
                rows.append(row)
            return rows

        def evaluate_finalists(self, sites):
            return []

        def metrics(self):
            return {
                "cached_cell_count": len(self.cache),
                "cache_hits": 0,
                "fully_scored_cell_count": len(self.cache),
                "early_abandoned_cell_count": 0,
                "evaluation_elapsed_s": 0.0,
            }

    def adaptive(evaluate, **kwargs):
        rows = evaluate(np.asarray([[0.0, 0.0]]))
        return rows, [{"new_cell_count": 1, "spacing_km": 200.0}]

    monkeypatch.setattr(MODULE, "CITIES", {"unit": (0.0, 0.0)})
    monkeypatch.setattr(MODULE, "snapshot_sources", lambda _: {"files": {}})
    monkeypatch.setattr(
        MODULE.fast_coverage_inputs,
        "load",
        lambda *a, **k: {"trajectory_digest": "fixture", "provenance": {"truth_accessed": False}},
    )
    monkeypatch.setattr(MODULE, "build_prediction_banks", lambda _: ((), {}))
    monkeypatch.setattr(MODULE, "CoverageEvaluator", Evaluator)
    monkeypatch.setattr(MODULE, "multiresolution_search", adaptive)
    args = SimpleNamespace(
        output=tmp_path / "results",
        session="fixture",
        evidence=tmp_path,
        bulk_root=tmp_path,
        tle_root=tmp_path,
        thresholds_hz=(200.0,),
        primary_threshold_hz=200.0,
        partition_mode="fixed",
        candidate_block=16,
        cache_policy=policy,
        cities=("unit",),
        mode="both",
        spacings_km=(200.0, 100.0),
        single_point=None,
        uniform_policy="full",
        top_k=1,
        levels_km=(200.0, 100.0),
        basins=(8,),
        workers=1,
        radius_km=100.0,
    )
    summary = MODULE.run(args)
    assert len(instances) == expected_instances
    assert len(summary["runs"]) == 3
    adaptive_result = json.loads((args.output / "unit-adaptive" / "result.json").read_text())
    assert adaptive_result["cache_policy"] == policy
    assert adaptive_result["newly_scored_points"] == (1 if policy == "cold-per-search" else 0)


def test_default_policy_bounds_grid_to_500_km_radius():
    assert MODULE.MAXIMUM_RADIUS_KM == 500.0
    assert MODULE.SEARCH_BOX_KM == 1000.0
    points = MODULE.regional_circle_offsets(MODULE.SEARCH_BOX_KM, 500.0, 50.0)
    assert len(points) == 316
    assert np.all(np.linalg.norm(points, axis=1) <= 500.0)
