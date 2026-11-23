from importlib import import_module
import json
from shutil import copyfile
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(("median", "summed", "fixes", "preserved", "qualifies"), [
    (.5, .5, 97, True, True), (.500001, .45, 97, True, False),
    (.45, .500001, 97, True, False), (.45, .45, 96, True, False),
    (.45, .45, 97, False, False),
])
def test_final_version_requires_both_raw_timing_gates_and_quality(median, summed, fixes, preserved, qualifies):
    finish = import_module("reports.ALGO08.single-core-2x.ds30_hundred_finish")
    result = dict(verified=100, quality=dict(preserved=preserved), solver_failures=dict(candidate=[], baseline=[]),
                  builds=dict(baseline=dict(fixes=97), candidate=dict(fixes=fixes)),
                  timing=dict(all_verified=dict(elapsed_s=dict(median_candidate_over_baseline=median,
                                                               summed_candidate_over_baseline=summed))))
    assert finish.decision(result)["qualifies"] is qualifies
    assert not finish.decision(dict(result, solver_failures=dict(candidate=["case"], baseline=[])))["qualifies"]
    with pytest.raises(ValueError, match="100 verified"):
        finish.decision(dict(result, verified=99))

study = import_module("reports.ALGO08.single-core-2x.ds30_hundred")


def test_path_preflight_rejects_an_attempt_that_already_started_measurement():
    finish = import_module("reports.ALGO08.single-core-2x.ds30_hundred_finish")
    value = dict(runs={}, cache_observation=dict(arms={}),
                 failure="ValueError: Cache observation recording differs from its assigned sealed manifests")
    finish.verify_preflight(value)
    for change in (dict(runs={"baseline": {}}), dict(cache_observation={"arms": {"candidate": {}}}),
                   dict(failure="Unexpected I/O error")):
        with pytest.raises(ValueError, match="before either timed launch"):
            finish.verify_preflight(dict(value, **change))


def test_shared_position_error_counts_only_matched_positions():
    finish = import_module("reports.ALGO08.single-core-2x.ds30_hundred_finish")
    pairs = {"both": {"baseline": 1.0, "candidate": 1.25}, "missing": {"baseline": 1.0, "candidate": None}}
    quality = {"by_site": [{"arms": {"c0": {"error_by_case_km": pairs}}}]}
    assert finish.shared_error(quality, "c0") == (1, .25)
    assert finish.shared_error({"by_site": []}, "c0") == (0, None)


def test_frozen_roster_is_the_first_hundred_distinct_recordings_and_binds_order():
    predictions = study.stage.pinned(study.stage.OUT / "prediction-lock.json", study.stage.LOCK_SHA256)
    names = [r["case"] for r in predictions["predictions"] if r["method"] == "compact_two_scan"][:100]
    inputs = [SimpleNamespace(name=name, order=["baseline", "candidate"], raw_authority="raw",
                              rank=rank, session=name, region={}, snapshots_sha256="archive")
              for rank, name in enumerate(names, 1)]
    assert len(study.panel_manifest(inputs)["cases"]) == 100
    with pytest.raises(ValueError, match="frozen order"):
        study.panel_manifest(list(reversed(inputs)))


def test_histograms_retain_withholding_in_fix_counts_and_runtime(tmp_path):
    row = dict(case="DS30-test", state="verified", expected_order=["baseline", "candidate"],
               elapsed_s=dict(baseline=20., candidate=9.), cpu_s=dict(baseline=18., candidate=8.),
               input_blocks=dict(baseline=0, candidate=0),
               audit=dict(decisions=dict(baseline="complete", candidate="withheld")),
               arms={method: {arm: {"latlon": coords} for arm in study.stage.ARMS}
                     for method, coords in (("baseline", [1.1, 1.]), ("candidate", None))})
    refs = {"DS30-test": [1., 1.]}
    _, summary = study.summarize([row], refs)
    assert summary["verified"] == 1 and summary["assigned"] == 100
    assert summary["builds"]["candidate"]["fitted_c_error_km"]["n"] == 0
    assert summary["builds"]["candidate"]["fixes"] == 0
    assert summary["timing"]["all_verified"]["elapsed_s"]["summed_candidate_over_baseline"] == .45
    study.write_report([row], refs, tmp_path, candidate_label="ALGO08v3")
    assert study.stage.read(tmp_path / "progress.json") == summary
    for name in ("runtime", "position-error"):
        assert (tmp_path / (name + ".png")).read_bytes().startswith(b"\x89PNG")


def test_partial_archive_review_uses_pair_pin_and_keeps_complete_gates_pending(tmp_path):
    reviewer = import_module("reports.ALGO08.single-core-2x.ds30_hundred_review")
    receipts = study.stage.PANEL.parents[1] / "single-core-2x/measurements"
    first = study.stage.read(receipts / "exact-curved-0374-stage.json")["cases"][0]
    lock = study.stage.pinned(study.stage.OUT / "prediction-lock.json", study.stage.LOCK_SHA256)
    names = [r["case"] for r in lock["predictions"] if r["method"] == "compact_two_scan"][:100]
    manifest = dict(candidate=study.stage.EXACT_CURVED_LOOKAHEAD, baseline=str(study.stage.pair.BASELINE),
                    baseline_detector=study.stage.BASELINE_DETECTOR, cases=[{"case": name} for name in names])
    manifest["cases"][0].update(order=first["actual_order"], region=first["region"],
                                raw_authority=first["raw_authority"])
    (tmp_path / "panel.json").write_text(json.dumps(manifest))
    (tmp_path / "audits").mkdir()
    (tmp_path / "audits/DS30-0374.json").write_text(json.dumps(first))
    directory = tmp_path / "publications/DS30-0374"
    directory.mkdir(parents=True)
    copyfile(receipts / "DS30-0374-exact-curved-lookahead.json", directory / "pair.json")
    summary = reviewer.review(tmp_path)
    assert summary["stages"]["100"] == {"assigned": 100, "verified": 1}
    assert summary["verified_subset"]["quality"]["preserved"]
    assert not summary["verified_subset"]["passed_elapsed"]
    assert summary["verified_subset"]["same_pixels_all_returned"] == 1
    assert summary["verified_subset"]["shared_fix_timing"]["all_verified"]["cases"] == names[:1]
    (directory / "pair.json").write_text("{}")
    with pytest.raises(ValueError, match="Invalid archived"):
        reviewer.review(tmp_path)
