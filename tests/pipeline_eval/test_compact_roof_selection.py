from tools.pipeline_eval.qualification import compact_roof_selection as study
from tools.pipeline_eval.qualification import compact_roof_selection_results as results


def test_actual_roster_is_32_frozen_rows_in_a_fixed_unlabelled_order():
    all_ids, order, _ = study.roster()
    assert len(all_ids) == len(order) == 32
    assert all_ids == sorted(order)
    assert order[:3] == ["DS26-0116", "DS26-0269", "DS26-0217"]


def test_dispatches_full_budget_only_and_skips_unavailable_or_already_claimed(
    monkeypatch, tmp_path
):
    plan = dict(
        order=["missing", "first", "second"],
        bindings={key: {"eligible": key != "missing"} for key in ("missing", "first", "second")},
    )
    (tmp_path / "claims").mkdir()
    now = 5
    monkeypatch.setattr(study, "monotonic", lambda: now)
    deadline = now + study.CAP + study.RESERVE
    assert study.claim(tmp_path, plan, 15, deadline - 0.1) is None
    assert study.claim(tmp_path, plan, 15, deadline) == "first"
    assert study.claim(tmp_path, plan, 12, deadline) == "second"
    assert study.claim(tmp_path, plan, 16, deadline) is None


def test_unlaunched_and_unavailable_are_neither_withheld_nor_returned():
    identity = {
        key: None
        for key in (
            "id",
            "input_sha256",
            "native_sha256",
            "catalog_sha256",
            "frozen_request_sha256",
            "tile",
        )
    }
    binding = dict(identity, eligible=True, frozen_unavailable=None, input_issues={})
    missing = results.unmeasured(binding, False)
    unconfirmed = results.unmeasured(binding, True)
    absent = results.unmeasured(
        dict(binding, eligible=False, frozen_unavailable="no_native_run"), False
    )
    assert missing["result"]["status"] == "missing" and missing["attempted"] is False
    assert unconfirmed["result"]["status"] == "missing" and unconfirmed["attempted"] is None
    assert (
        absent["result"]["status"] == "unavailable"
        and absent["result"]["reason"] == "no_native_run"
    )
    assert all(r["worker_returned"] is False for r in (missing, unconfirmed, absent))


def test_legacy_launcher_computation_errors_remain_fresh_attempts():
    for reason in ("AssertionError", "ValueError: orbit phase interpolation never extrapolates"):
        row = dict(
            worker_returned=True, attempted=True, result=dict(status="unavailable", reason=reason)
        )
        result = results.normalize_attempt(row)
        assert result["attempted"] and result["launcher_returned"]
        assert not result["worker_returned"] and result["result"]["status"] == "failed"
        assert result["reported_worker_status"] == "unavailable"
