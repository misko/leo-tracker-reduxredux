from copy import deepcopy
from importlib import import_module
from pathlib import Path


def test_combined_pair_tolerates_only_subthreshold_probe_score_drift(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    replay = import_module("dense_quadratic_fused")
    compare = replay.compare
    base = dict.fromkeys((
        "identity", "status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "associated",
        "science", "grid", "grid_points", "objective_replay", "source_sha256", "experiment_source_sha256",
    ))
    base.update(graph={"graph_sha256": "fixed", "clocks": {}}, attempts=[{"decision": "complete"}],
                regional=[{"result": {"would_withhold": False}}],
                visited_probes=[{"score": 1., "owners": {"track": 8300}}],
                fused_geography={"counts": {"calls": 1}})
    candidate = deepcopy(base)
    candidate["visited_probes"][0]["score"] += replay.SCORE_TOLERANCE / 2
    candidate["graph"]["clocks"]["cpu_s"] = 2.
    checks, error = compare(base, candidate)
    assert all(checks.values()) and 0 < error < replay.SCORE_TOLERANCE
    candidate["visited_probes"][0]["owners"]["track"] = 8301
    candidate["graph"]["graph_sha256"] = "different"
    checks, error = compare(base, candidate)
    assert not checks["probe_scores_and_owners"] and not checks["graph"] and error is None
