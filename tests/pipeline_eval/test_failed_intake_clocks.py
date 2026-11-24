import json

import pytest

from reports.ALGO08.v3.failed_intake_clocks import MEASUREMENTS, estimate, launch_interval


def test_bounds_use_the_preceding_or_following_completed_baseline():
    ns = 10**9
    assert launch_interval(["candidate", "baseline"], ns, 14*ns, 8*ns, 3., 5.) == (ns, 3*ns)
    assert launch_interval(["baseline", "candidate"], ns, 18*ns, 8*ns, 3., 5.) == (11*ns, 13*ns)
    with pytest.raises(ValueError):
        launch_interval(["baseline", "candidate"], ns, 15*ns, 8*ns, 3., 5.)


def test_measured_receipt_contains_each_release_failure_and_crosscheck():
    evidence = json.loads((MEASUREMENTS/"failed-intake-clocks.json").read_bytes())
    intake = json.loads((MEASUREMENTS/"release-intake-rate.json").read_bytes())
    failures = evidence["failures"]
    assert set(failures) == {r["case"] for r in intake["rows"] if r["post_s"] is None}
    assert evidence["controls"]["checked"] == 95
    for row in intake["rows"]:
        if row["case"] in failures:
            sample = failures[row["case"]]
            assert 0 <= sample["pre_s"][1]-sample["pre_s"][0] < .2
            assert sample["post_s"][1] + sample["pre_s"][0] == pytest.approx(row["elapsed_s"])


def test_recovery_charges_saved_worker_and_admission_and_retains_other_failure():
    rows = [dict(case=k, byte_low=1_000_000, byte_high=1_000_000, post_s=None, elapsed_s=10)
            for k in ("recover", "still_fails", "success")]
    rows[-1]["post_s"] = 1.5
    result = estimate(dict(rows=rows), {k: dict(post_s=[1.5, 1.5]) for k in ("recover", "still_fails")},
                      dict(case="recover", clock=dict(elapsed_s=1.), admission=dict(setup_clock=dict(elapsed_s=1.))))
    assert result["same_exits"][0]["required_MB_s"] == pytest.approx(.25)
    # Total target 15 s = 10 s unchanged failure + 2 s recovery + 1 s success + 2 MB / rate.
    assert result["one_recovered_four_fixed"][0]["required_MB_s"] == pytest.approx(1.)
