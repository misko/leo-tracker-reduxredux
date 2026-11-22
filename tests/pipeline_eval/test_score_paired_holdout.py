from copy import deepcopy
import hashlib
import json

import pytest
import numpy as np

from tools.pipeline_eval.qualification.holdout_geography import EDGE_PROTOCOL, fresh_layout, fresh_offers
from tools.pipeline_eval.qualification.score_paired_holdout import lock, pinned, score


def run(latitude=10., elapsed=1., withheld=False, near=True):
    center = [10., 30.] if near else [20., 30.]
    arms = {c: dict(latlon=None if withheld else [latitude, 30.], rf_rms_hz=1.1)
            for c in ("c0", "fitted_c")}
    return dict(receipt=dict(region=dict(center=center, width_km=20),
                             decision="withheld" if withheld else "complete"),
                arms=arms, elapsed_s=elapsed, cpu_s=elapsed)


def cases():
    def make(offer, baseline, candidate):
        return dict(job=dict(offer=offer, recording="r"), result=dict(runs=dict(baseline=baseline, candidate=candidate)))
    key = {"answers": {k: dict(recording="r", truth=[10., 30.], condition=k) for k in ("containing", "far")}}
    data = dict(cases=[make("containing", run(elapsed=4.), run()), make("far", run(20., 3., near=False),
                                                                      run(20., 1., near=False))])
    return data, key


def test_inherited_false_fixes_count_even_when_relative_gates_pass():
    data, key = cases()
    result = score(data, key)
    assert result["relative_quality_preserved"] and result["summed_elapsed_ratio"] == pytest.approx(2/7)
    assert not result["passed"]  # One geographic site cannot qualify a two-site confirmation.
    assert {s["false_fixes"] for s in result["by_site"] if s["condition"]=="far"} == {1}
    assert result["missing_region"]["candidate"] == dict(assigned=1, false_fixes=1, withheld=0, failed=0)
    assert all(s["within_km_count"]["1"] == 0 for s in result["by_site"] if s["condition"]=="far")
    data["cases"][1]["result"]["runs"]["baseline"] = run(withheld=True, near=False)
    assert not score(data, key)["relative_quality_preserved"]


def test_two_site_confirmation_requires_both_median_and_total_ratios():
    data, key = cases()
    another = deepcopy(data["cases"])
    for c in another:
        condition = c["job"]["offer"]
        c["job"].update(offer="second-"+condition, recording="s")
        key["answers"][c["job"]["offer"]] = dict(recording="s", condition=condition, truth=[-22., 30.])
        for r in c["result"]["runs"].values():
            r["receipt"]["region"]["center"][0] -= 32
            for arm in r["arms"].values():
                arm["latlon"][0] -= 32
    data["cases"].extend(another)
    assert score(data,key)["passed"]
    assert not score(data,key)["passed_geographic_holdout"]
    assert not score(data,key)["candidate_correct_on_all_region_decisions"]
    another[0]["result"]["runs"]["candidate"]["elapsed_s"] = 100.
    result = score(data,key)
    assert result["median_elapsed_ratio"] <= .5 and result["summed_elapsed_ratio"] > .5
    assert not result["passed"]


def test_relabeling_one_recording_cannot_create_a_second_location():
    data, key = cases()
    key["answers"]["far"]["truth"][0] = -22.
    with pytest.raises(ValueError, match="multiple receiver locations"):
        score(data, key)


def test_revealed_height_must_agree_across_offers_for_the_same_site():
    data, key = cases()
    key["answers"]["containing"]["height_m"] = 85.0
    key["answers"]["far"]["height_m"] = 1800.0
    with pytest.raises(ValueError, match="multiple heights"):
        score(data, key)


def test_lost_fix_missing_pair_worse_error_and_summed_latency_cannot_pass():
    initial, key = cases()
    for bad in (run(withheld=True), run(latitude=10.05)):
        data = deepcopy(initial)
        data["cases"][0]["result"]["runs"]["candidate"] = bad
        assert not score(data,key)["passed"]
    data = deepcopy(initial)
    data["cases"][0]["result"] = dict(failure="missing")
    result = score(data,key)
    assert not result["passed"] and result["assigned"] == 2 and result["summed_elapsed_ratio"] is None
    assert len(result["rows"]) == 8
    data = deepcopy(initial)
    data["cases"][1]["result"]["runs"]["candidate"]["elapsed_s"] = 2.8
    assert not score(data,key)["passed"]


def test_lock_binds_every_assignment_and_rejects_a_substituted_candidate(tmp_path):
    jobs = [dict(offer="a",recording="r"),dict(offer="b",recording="r")]
    path = tmp_path/"panel.json"
    path.write_text(json.dumps(dict(jobs=jobs,commitment="c"*64)))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    locked = lock(path,digest,"spec",tmp_path)
    assert [r["result"]["failure"] for r in locked["cases"]] == ["Missing paired run"]*2
    (tmp_path/"a").mkdir()
    pair = dict(candidate_specification_digest="different",
                blind_assignment=dict(job=jobs[0], panel_sha256=digest, truth_commitment="c"*64))
    (tmp_path/"a/pair.json").write_text(json.dumps(pair))
    with pytest.raises(ValueError, match="frozen assignment"):
        lock(path,digest,"spec",tmp_path)
    with pytest.raises(ValueError, match="Changed"):
        pinned(path, "00")


def test_fresh_edge_protocol_requires_both_sides_at_each_site_and_counts_valid_edge_fixes():
    rng = np.random.default_rng(991)
    data = dict(cases=[], geography_protocol=EDGE_PROTOCOL)
    key = dict(answers={}, seed=(991).to_bytes(32, "big").hex())
    for recording, (site, _edge) in zip(("a", "b"), fresh_layout(rng), strict=True):
        width, offers = fresh_offers(rng, site)
        for condition, center in offers.items():
            job = dict(recording=recording, offer=recording + condition)
            key["answers"][job["offer"]] = dict(recording=recording, condition=condition, truth=site)
            contained = condition in {"containing", "edge-containing"}
            runs = {label: run(elapsed=seconds, withheld=not contained)
                    for label, seconds in [("baseline", 4.), ("candidate", 1.)]}
            for result in runs.values():
                result["receipt"]["region"] = dict(center=center, width_km=width)
                for arm in result["arms"].values():
                    arm["latlon"] = list(site) if contained else None
            data["cases"].append(dict(job=job, result=dict(runs=runs)))
    result = score(data, key)
    assert result["passed"] and result["assigned"] == 8
    assert result["passed_geographic_holdout"]
    assert result["fresh_site_draw_verified"]
    substituted = score(data, dict(key, seed="55" * 32))
    assert substituted["candidate_correct_on_all_region_decisions"]
    assert not substituted["fresh_site_draw_verified"] and not substituted["passed_geographic_holdout"]
    assert result["candidate_correct_on_all_region_decisions"]
    assert result["geography_protocol"] == EDGE_PROTOCOL
    assert result["missing_region"]["candidate"] == dict(assigned=4, false_fixes=0, withheld=4, failed=0)
    assert all(s["false_fixes"] == 0 for s in result["by_site"])
    for row in result["rows"]:
        assert row["offered_center_error_km"] > 0
        if row["decision"] == "complete":
            assert row["improvement_over_center_km"] == row["offered_center_error_km"]
            assert row["prediction_face_clearance_km"] == row["truth_face_clearance_km"] > 0
        else:
            assert row["improvement_over_center_km"] is None
            assert row["truth_face_clearance_km"] < 0 and row["prediction_face_clearance_km"] is None
    inherited = deepcopy(data)
    omitted = next(c for c in inherited["cases"] if c["job"]["offer"] == "aedge-omitted")
    for arm in omitted["result"]["runs"].values():
        arm["receipt"]["decision"] = "complete"
        for prediction in arm["arms"].values():
            prediction["latlon"] = arm["receipt"]["region"]["center"]
    inherited_result = score(inherited, key)
    assert inherited_result["passed"] and not inherited_result["passed_geographic_holdout"]
    assert not score(dict(data, geography_protocol=None), key)["passed_geographic_holdout"]
    moved = deepcopy(data)
    moved_key = deepcopy(key)
    moved["cases"][0]["job"]["recording"] = "third-waveform"
    moved_key["answers"][moved["cases"][0]["job"]["offer"]]["recording"] = "third-waveform"
    assert not score(moved, moved_key)["geographic_confirmation_coverage"]
    case = next(c for c in data["cases"] if c["job"]["offer"] == "bedge-containing")
    lost = case["result"]["runs"]["candidate"]
    lost["receipt"]["decision"] = "withheld"
    for arm in lost["arms"].values():
        arm["latlon"] = None
    assert not score(data, key)["relative_quality_preserved"]
    data["cases"].remove(case)
    del key["answers"]["bedge-containing"]
    assert not score(data, key)["geographic_confirmation_coverage"]
