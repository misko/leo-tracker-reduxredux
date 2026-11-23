from copy import deepcopy
import hashlib
import json
from math import cos, radians

import pytest
import numpy as np

from leo.storage.short_window import ShortWindowReader, ShortWindowWriter
from tools.pipeline_eval.qualification.holdout_geography import EDGE_PROTOCOL, fresh_layout, fresh_offers
from tools.pipeline_eval.qualification.paired_publication import V3_IDENTITY
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
    failed = deepcopy(data)
    failed_arm = failed["cases"][1]["result"]["runs"]["candidate"]
    failed_arm["receipt"]["decision"] = "solver_failed"
    for estimate in failed_arm["arms"].values():
        estimate["latlon"] = None
    failed_result = score(failed, key)
    assert failed_result["failed_pairs"] == 1
    assert failed_result["missing_region"]["candidate"]["failed"] == 1
    assert failed_result["summed_elapsed_ratio"] == score(data, key)["summed_elapsed_ratio"]
    assert not failed_result["passed"]
    assert not score(data,key)["passed_geographic_holdout"]
    assert not score(data,key)["candidate_correct_on_all_region_decisions"]
    another[0]["result"]["runs"]["candidate"]["elapsed_s"] = 100.
    result = score(data,key)
    assert result["median_elapsed_ratio"] <= .5 and result["summed_elapsed_ratio"] > .5
    by_site = {tuple(row["site"]): row for row in result["runtime_by_site"]}
    assert by_site[10., 30.]["summed_elapsed_ratio"] == pytest.approx(2/7)
    assert by_site[-22., 30.]["summed_elapsed_ratio"] == pytest.approx(101/7)
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
    site, = result["runtime_by_site"]
    assert site["assigned"] == 2 and site["completed"] == 1 and site["median_elapsed_ratio"] is None
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
    pair["candidate_specification_digest"] = "spec"
    (tmp_path/"a/pair.json").write_text(json.dumps(pair))
    with pytest.raises(ValueError, match="ALGO08v3 baseline"):
        lock(path, digest, "spec", tmp_path, require_v3=True)
    pair["baseline_release"] = V3_IDENTITY
    (tmp_path/"a/pair.json").write_text(json.dumps(pair))
    locked = lock(path, digest, "spec", tmp_path, require_v3=True)
    assert locked["required_baseline_release"] == V3_IDENTITY
    assert locked["cases"][1]["result"] == {"failure": "Missing paired run"}
    with pytest.raises(ValueError, match="Changed"):
        pinned(path, "00")


@pytest.mark.parametrize("edges", [("upper", "upper"), ("upper", "lower")])
def test_lock_reads_pilot_edges_from_the_pinned_recording(tmp_path, edges):
    writer = ShortWindowWriter(tmp_path, "wave", configuration={"targets": [{"edge": e} for e in edges]},
                               radio={}, receiver_ids=(0,))
    sealed = writer.finish(stop_reason="fixture")
    digest = ShortWindowReader(sealed).manifest_sha256
    panel = dict(jobs=[dict(offer="offer", recording="wave")], commitment="0"*64,
                 geography_protocol=EDGE_PROTOCOL, inputs=dict(recordings={"wave": digest}))
    path = tmp_path / "panel.json"

    def freeze():
        path.write_text(json.dumps(panel))
        return lock(path, hashlib.sha256(path.read_bytes()).hexdigest(), "spec", tmp_path)

    if edges[0] == edges[1]:
        assert freeze()["recording_pilot_edges"] == {"wave": "upper"}
    else:
        with pytest.raises(ValueError, match="one pilot edge"):
            freeze()
    panel["inputs"]["recordings"]["wave"] = "sha256:" + "0"*64
    with pytest.raises(ValueError, match="manifest changed"):
        freeze()


@pytest.fixture
def fresh_panel():
    rng = np.random.default_rng(45)
    data = dict(cases=[], geography_protocol=EDGE_PROTOCOL, recording_pilot_edges={})
    key = dict(answers={}, seed=(45).to_bytes(32, "big").hex())
    for recording, (site, edge) in zip(("a", "b"), fresh_layout(rng), strict=True):
        data["recording_pilot_edges"][recording] = edge
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
    return data, key


@pytest.mark.parametrize("mutation", ["same", "swapped", "missing"])
def test_geographic_confirmation_requires_the_drawn_pilot_edge_at_each_site(fresh_panel, mutation):
    data, key = fresh_panel
    assert score(data, key)["fresh_pilot_edges_verified"]
    edges = data["recording_pilot_edges"]
    if mutation == "same":
        edges["a"] = edges["b"]
    elif mutation == "swapped":
        edges["a"], edges["b"] = edges["b"], edges["a"]
    else:
        del data["recording_pilot_edges"]
    result = score(data, key)
    assert result["passed"] and result["fresh_site_draw_verified"]
    assert not result["fresh_pilot_edges_verified"] and not result["passed_geographic_holdout"]


@pytest.mark.parametrize("screen", ["offered", "truth", "unrelated"])
def test_fresh_confirmation_uses_only_the_offered_center_for_screening(fresh_panel, screen):
    data, key = fresh_panel
    case = data["cases"][0]
    site = key["answers"][case["job"]["offer"]]["truth"]
    for run_data in case["result"]["runs"].values():
        region = run_data["receipt"]["region"]
        region["screen_center"] = {"offered": region["center"], "truth": list(site),
                                   "unrelated": [13.3, 45.6]}[screen]
    result = score(data, key)
    assert result["geographic_confirmation_coverage"] == (screen == "offered")
    assert result["passed_geographic_holdout"] == (screen == "offered")


@pytest.mark.parametrize("mutation", ["opposite_face", "perpendicular_face", "barely_outside",
                                      "different_width", "duplicate_offer", "different_paired_regions",
                                      "revealed_coordinate"])
def test_fresh_panel_rejects_mismatched_boundary_design(fresh_panel, mutation):
    data, key = fresh_panel
    label = "far" if mutation in {"barely_outside", "different_width", "different_paired_regions"} else "edge-omitted"
    case = next(case for case in data["cases"] if case["job"]["offer"] == "a" + label)
    site = key["answers"][case["job"]["offer"]]["truth"]
    if mutation == "duplicate_offer":
        extra = deepcopy(case)
        extra["job"]["offer"] = "extra"
        key["answers"]["extra"] = dict(key["answers"][case["job"]["offer"]])
        data["cases"].append(extra)
    elif mutation == "different_paired_regions":
        case["result"]["runs"]["candidate"]["receipt"]["region"]["center"] = list(
            case["result"]["runs"]["candidate"]["receipt"]["region"]["center"])
        case["result"]["runs"]["candidate"]["receipt"]["region"]["center"][1] += .001
    else:
        for run in case["result"]["runs"].values():
            region = run["receipt"]["region"]
            lat, lon = region["center"]
            east = (site[1]-lon)*111.32*cos(radians(lat))
            north = (site[0]-lat)*111
            if mutation == "opposite_face":
                east, north = -east, -north
            elif mutation == "perpendicular_face":
                east, north = north, east
            elif mutation == "barely_outside":
                east, north = region["width_km"]/2 + .1, 0.
            elif mutation == "revealed_coordinate":
                east, north = (east, 0.) if abs(east) > abs(north) else (0., north)
            else:
                region["width_km"] += .1
            lat = site[0]-north/111
            region["center"] = [lat, site[1]-east/(111.32*cos(radians(lat)))]
    result = score(data, key)
    assert result["relative_quality_preserved"]
    assert not result["geographic_confirmation_coverage"]
    assert not result["passed_geographic_holdout"]


def test_fresh_edge_protocol_requires_both_sides_at_each_site_and_counts_valid_edge_fixes(fresh_panel):
    data, key = fresh_panel
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
