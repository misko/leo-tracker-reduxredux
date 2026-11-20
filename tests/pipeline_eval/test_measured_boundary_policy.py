import json

import pytest

from tools.pipeline_eval.qualification import measured_boundary_policy as trial
from tools.pipeline_eval.qualification import measured_boundary_policy_results as results
from tools.pipeline_eval.variants.compact_tile_decision import decide

TILE = {"id": "frozen", "center": [0, 0], "width_km": 25}


def payload(clearance_m):
    edge = (12.5 - clearance_m / 1000) / 111
    return (
        json.dumps(
            dict(
                status="ok",
                boundary="installed",
                metrics={"tracks": 12},
                arms={
                    "c0": {"latlon": [edge, 0], "rf_rms_hz": 55},
                    "fitted_c": {"latlon": [0, 0], "rf_rms_hz": 57},
                },
            ),
            indent=2,
        )
        + "\n"
    ).encode()


@pytest.mark.parametrize(("clearance", "status"), [(19, "withheld"), (21, "ok")])
def test_fixed_threshold_changes_only_paired_publication(clearance, status):
    raw = payload(clearance)
    off = decide(raw)
    on = decide(off, enabled=True, tile=TILE)
    original, candidate = trial.check_pair(raw, off, on, TILE)
    assert candidate["status"] == status
    for arm, old in original["arms"].items():
        new = candidate["arms"][arm]
        assert new["rf_rms_hz"] == old["rf_rms_hz"]
        if status == "withheld":
            assert new["latlon"] is None and new["forced_latlon"] == old["latlon"]
        else:
            assert new["latlon"] == old["latlon"]


def test_off_requires_byte_identity_and_on_checks_exact_rule():
    raw = payload(19)
    on = decide(raw, enabled=True, tile=TILE)
    with pytest.raises(ValueError):
        trial.check_pair(raw, raw + b"\n", on, TILE)
    with pytest.raises(ValueError):
        trial.check_pair(raw, raw, raw, TILE)


def test_omitted_offer_is_scored_as_false_publication_or_withheld():
    raw = payload(19)
    off, on = trial.check_pair(raw, raw, decide(raw, enabled=True, tile=TILE), TILE)
    rows = [
        dict(id="offer", tile=TILE, method=name, result=result)
        for name, result in ((results.OFF, off), (results.ON, on))
    ]
    queries = {"offer": dict(recording="DS26", condition="near-outside", truth=[0.13, 0])}
    usage = {
        "offer": dict.fromkeys(
            (
                "solver_wall_s",
                "solver_cpu_s",
                "cgroup_wall_s",
                "peak_bytes",
                "guard_on_wall_s",
                "guard_off_wall_s",
            ),
            1.0,
        )
    }
    scored = results.score_rows(rows, queries, usage)
    assert len(scored) == 4
    assert sum(r["false_publication"] for r in scored) == 2
    as_guarded = [r for r in scored if r["method"] == results.ON]
    assert all(r["error_km"] is None and r["forced_error_km"] > 0 for r in as_guarded)
