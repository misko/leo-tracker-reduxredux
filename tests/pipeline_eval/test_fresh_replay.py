from tools.pipeline_eval.qualification import fresh_replay as trial
from tools.pipeline_eval.qualification import fresh_replay_reference as original
from tools.pipeline_eval.qualification import fresh_replay_results as results
from tools.pipeline_eval.scoring import ARMS, ROLES


def test_shortlist_orders_by_manifest_then_id_and_keeps_rejected_access(monkeypatch):
    archive = []

    def availability(case):
        archive.append(case["id"])
        if case["id"] == "a":
            raise ValueError("index unavailable")
        return {"input_manifest_sha256": "actual"}, 12

    monkeypatch.setattr(trial, "archive_ok", availability)
    rows = [(digest, case, {"id": case}) for digest, case in [("b", "c"), ("a", "b"), ("a", "a")]]
    ledger = {row[1]: {} for row in rows}
    rejected = []
    chosen, capture = trial.shortlist(rows, rejected, ledger, "DS29")
    assert chosen["id"] == "b"
    assert archive == ["a", "b"]
    assert rejected == ["a"]
    assert ledger["a"]["state"] == "archive unavailable"
    assert ledger["b"]["checked_files"] == 12
    assert capture["input_manifest_sha256"] == "actual"


def test_original_reference_lanes_cover_exactly_the_four_scientific_policies():
    assert set(original.LANES) == {2, 3}
    roles = [role for lanes in original.LANES.values() for role in lanes]
    assert sorted(roles) == sorted(ROLES)


def test_missing_reference_and_missing_endpoint_remain_observable():
    query = {
        "id": "test",
        "truth": [10, 10],
        "reference": {role: {arm: {"error_km": None} for arm in ARMS} for role in ROLES},
    }
    rows = []
    for method in results.METHODS.values():
        points = {
            arm: {"latlon": [10.01, 10.01] if method == trial.CONTROL else None} for arm in ARMS
        }
        rows.append(
            dict(
                id="test",
                cohort="fresh",
                method=method,
                result=dict(
                    arms=points, status="ok" if method == trial.CONTROL else "timed_out", metrics={}
                ),
            )
        )
    scores = results.geographic(rows, {"test": query})
    table = results.distribution_rows(scores, {"fresh": ["test"]})["fresh"]
    assert table["c0"]["control"]["published"] == 1
    assert table["c0"]["control"]["v5_available"] == 0
    assert table["c0"]["control"]["within_5pct"] == 0
    assert table["fitted_c"]["candidate"]["attempted"] == 1
    assert table["fitted_c"]["candidate"]["published"] == 0
