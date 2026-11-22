from importlib import import_module
from types import SimpleNamespace

import pytest

study = import_module("reports.ALGO08.single-core-2x.ds30_hundred")


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
    study.write_report([row], refs, tmp_path)
    assert study.stage.read(tmp_path / "progress.json") == summary
    for name in ("runtime", "position-error"):
        assert (tmp_path / (name + ".png")).read_bytes().startswith(b"\x89PNG")
