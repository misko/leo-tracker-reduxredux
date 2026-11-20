import json
from collections import Counter, defaultdict

import pytest

from tools.pipeline_eval import corpus
from tools.pipeline_eval.__main__ import references
from tools.pipeline_eval.scoring import ARMS, baseline_rows, distance_km, score


@pytest.mark.parametrize(
    ("panel", "expected"),
    [
        ("roof16", {"DS26": (8, 8, 6), "DS29": (8, 8, 8)}),
        ("ds26-common127", {"DS26": (127, 127, 125)}),
        ("ds26-all159", {"DS26": (159, 143, 141)}),
    ],
)
def test_roof_rosters_keep_every_attempt_in_both_arms(panel, expected):
    rows = list(corpus.references(panel))
    assert len({row["id"] for row in rows}) == sum(item[0] for item in expected.values())
    baselines = baseline_rows(rows)
    assert {
        (row["group"], row["arm"]): (row["attempts"], row["error_km"]["n"], row["within_km"]["5"])
        for row in baselines
        if row["method"] == "baseline"
    } == {(group, arm): counts for group, counts in expected.items() for arm in ARMS}


@pytest.mark.parametrize("panel", ["ds26-all159", "roof16", "transfer124"])
def test_frozen_positions_reproduce_archived_errors(panel):
    for row in corpus.references(panel):
        for method in row["reference"].values():
            for arm in method.values():
                error = distance_km(row["truth"], arm["latlon"])
                if arm["error_km"] is None:
                    assert error is None
                else:
                    assert error == pytest.approx(arm["error_km"], abs=1e-8)


@pytest.mark.parametrize(
    ("panel", "counts"),
    [
        ("transfer16", {"Altrincham": 2, "DS29": 2, "StarLoc": 2, "Synthetic": 2}),
        ("transfer124", {"Altrincham": 3, "DS29": 8, "StarLoc": 11, "Synthetic": 40}),
    ],
)
def test_transfer_present_and_missing_pairs_share_the_same_signal(panel, counts):
    public = {
        row["id"]: row
        for row in map(json.loads, (corpus.FROZEN / "inputs.jsonl").read_text().splitlines())
    }
    _, rows = references(panel, None)
    pairs = defaultdict(dict)
    for row in rows:
        identity = (row["group"], row["recording"])
        assert row["condition"] not in pairs[identity]
        pairs[identity][row["condition"]] = row
    assert Counter(group for group, _ in pairs) == counts
    for members in pairs.values():
        assert set(members) == {"present", "missing"}
        present, missing = members["present"], members["missing"]
        assert present["truth"] == missing["truth"]
        a, b = public[present["id"]], public[missing["id"]]
        for key in ("observation", "catalog", "catalog_timestamp_ns"):
            assert a[key] == b[key]
        assert len(a["regions"]) == len(b["regions"]) == 4
        assert {r["id"] for r in a["regions"]} != {r["id"] for r in b["regions"]}


def test_public_inputs_cannot_fill_a_missing_raw_recording(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "absent-bulk"))
    monkeypatch.setenv("PIPELINE_EVAL_BLIND_ROOT", str(tmp_path / "absent-observations"))
    for panel, expected_rows in [("roof16", 16), ("transfer124", 124)]:
        cases = list(corpus.cases(panel, tmp_path / "cache"))
        assert len(cases) == expected_rows
        for case, _ in cases:
            assert case.get("recording_path") is None
            assert not case.get("recording_segments")
            assert case["input_issues"]["recording"]


def test_missing_region_scores_asymmetric_calibration_decisions():
    case = next(r for r in corpus.references("transfer124") if r["condition"] == "missing")
    result = dict(
        status="ok",
        boundary="regional search",
        metrics={},
        arms=dict(
            c0=dict(latlon=case["truth"]), fitted_c=dict(latlon=None, forced_latlon=case["truth"])
        ),
    )
    summary, _ = score([case], {case["id"]: dict(result=result)})
    c0, fitted_c = summary["groups"]
    assert c0["attempts"] == fitted_c["attempts"] == 1
    assert c0["false_publications"] == 1
    assert c0["decision_counts"] == dict(published=1)
    assert fitted_c["false_publications"] == 0
    assert fitted_c["decision_counts"] == dict(withheld=1)
    assert fitted_c["forced_error_km"]["n"] == 1


def test_null_position_payload_cannot_count_as_withholding():
    sample = next(r for r in corpus.references("transfer124") if r["condition"] == "missing")
    result = dict(status="ok", boundary="detector", metrics={}, arms=None)
    with pytest.raises(ValueError, match="both calibration arms"):
        score([sample], {sample["id"]: dict(result=result)})


@pytest.mark.parametrize(
    ("coordinate", "keeps_v5"), [([0, 0.001005], True), ([0.001005, 0], False)]
)
def test_v5_gate_reserves_the_one_meter_tolerance_for_reproduction(coordinate, keeps_v5):
    truth = [0, 0]
    baseline = [0, 0.001]
    original = dict(latlon=baseline, error_km=distance_km(truth, baseline))
    case = dict(
        id="replay",
        recording="replay",
        group="DS26",
        condition="present",
        truth=truth,
        reference={"baseline": dict.fromkeys(ARMS, original)},
    )
    result = dict(
        status="ok",
        boundary="regional search",
        metrics={},
        arms={arm: dict(latlon=coordinate) for arm in ARMS},
    )
    summary, _ = score([case], {case["id"]: dict(result=result)})
    assert all(group["keeps_v5_panel"] is keeps_v5 for group in summary["groups"])
