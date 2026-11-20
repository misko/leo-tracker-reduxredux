import copy
import json

import pytest

from tools.pipeline_eval import iq_compare as trial
from tools.pipeline_eval import iq_comparison_results as results
from tools.pipeline_eval import whole_iq


def specification():
    return dict(
        id="two-detectors",
        title="Paired detector trial",
        caption="Two recorded visits",
        control=dict(label="Control", sha256="0" * 64),
        candidate=dict(label="Candidate", sha256="f" * 64),
        cases=[dict(id="DS26-1", cpus=[0, 1], first="control", cohort="reserve")],
        additional_panels=[dict(id="reserve", title="Reserve recording", cohort="reserve")],
        limit_s=90,
    )


def test_study_rejects_duplicate_unsafe_or_unmatched_rosters():
    base = specification()
    trial.validate(base)
    for row in (
        dict(base["cases"][0], id="../outside"),
        dict(base["cases"][0], first="unknown"),
        dict(base["cases"][0], cpus=[3, 3]),
    ):
        with pytest.raises(ValueError):
            trial.validate(dict(base, cases=[row]))
    for change in (
        dict(cases=base["cases"] * 2),
        dict(candidate=dict(base["candidate"], sha256="will-change")),
        dict(additional_panels=[dict(id="all", title="Other", cohort="reserve")]),
        dict(additional_panels=[dict(id="empty", title="Empty", cohort="unused")]),
    ):
        with pytest.raises(ValueError):
            trial.validate(dict(base, **change))


def test_failed_attempt_counts_against_target_and_absent_v5_has_no_ratio():
    records = []
    for branch, position, status in (("control", None, "failed"), ("candidate", [40, -113], "ok")):
        result = dict(
            status=status, metrics={}, arms={a: dict(latlon=position) for a in results.ARMS}
        )
        records.append(
            dict(
                id="DS26-1",
                cohort="reserve",
                method=results.method("two-detectors", branch),
                result=result,
            )
        )
    resources = {"DS26-1": {"candidate": {"wall_s": 5.1}, "control": {"wall_to_failure_s": 6.0}}}
    base = dict(c0=dict(error_km=2), fitted_c=dict(error_km=None))
    refs = [dict(id="DS26-1", truth=[40, -113], reference=dict(baseline=base))]
    rows = results.score_rows(records, resources, refs, "two-detectors")
    assert len(rows) == 4
    keyed = {(row["branch"], row["arm"]): row for row in rows}
    assert keyed["control", "c0"]["within_10pct"] is False
    assert keyed["control", "c0"]["wall_s"] is None
    assert keyed["control", "c0"]["wall_to_failure_s"] == 6.0
    assert keyed["candidate", "c0"]["within_5pct"] is True
    assert keyed["candidate", "fitted_c"]["within_10pct"] is None
    assert keyed["candidate", "fitted_c"]["published"] is True


def test_seal_requires_terminal_receipts_and_validates_every_member(tmp_path, monkeypatch):
    work = tmp_path / "attempts"
    work.mkdir()
    spec = specification()
    plan = dict(spec=spec, cases={"DS26-1": spec["cases"][0]}, native_sources={}, limit_s=90)
    source = work / "source-lock.json"
    source.write_text(json.dumps(plan))
    (work / "source-lock.sha256").write_text(results._sha(source))
    out = tmp_path / "report"
    with pytest.raises(ValueError, match="no terminal"):
        results.seal(work, out)
    assert not (out / "prediction-lock.json").exists()
    support = {field: field for field in results.observed.COMMON}

    def paired(root, case, branch, plan, *, method):
        return dict(id=case, method=method), copy.copy(support), None

    monkeypatch.setattr(results.observed, "attempt", paired)
    results.seal(work, out)
    first = (out / "prediction-lock.json").read_bytes()
    results.seal(work, out)
    assert first == (out / "prediction-lock.json").read_bytes()
    with pytest.raises(ValueError, match="factor export"):
        results.seal(work, out, keep_factors=True)
    (out / "resources.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="SHA-256"):
        results.sealed(out)


def test_supplemental_panel_uses_the_frozen_native_parent_for_fresh_iq(tmp_path):
    for name in ("prediction-lock.json", "resources.json", "scores.csv"):
        (tmp_path / name).write_text(name)
    spec = specification()
    rows = [dict(id="DS26-1", method="test"), dict(id="DS29-2", method="test")]
    chart = results.chart(tmp_path, spec, "reserve", "reserve", ["DS26-1"], rows)
    assert len(chart["series"]) == 2
    assert all(s["native_field"] == "paired_capture_sha256" for s in chart["series"])
    assert chart["series"][1]["match"] == [
        "tile",
        "catalog_sha256",
        "original_request_sha256",
        "mode",
    ]
    lock = whole_iq.read(tmp_path / chart["seal"])
    assert lock["cases"] == ["DS26-1"]
    assert whole_iq.checked(tmp_path / "reserve.jsonl.gz", lock["files"]["reserve.jsonl.gz"])


def test_terminal_manager_clock_is_preserved_when_supervisor_ended_first(tmp_path):
    run = tmp_path / "DS26-1" / "candidate"
    run.mkdir(parents=True)
    service = dict(
        exit_code=None,
        supervisor_s=None,
        service_active_s=90.02,
        service_wall_s=112.25,
        systemd=dict(Result="timeout", CPUUsageNSec="48000000000"),
    )
    whole_iq.save_json(run / "service.json", service)
    case = dict(
        tile=[1, 2], catalog_sha256="a", request_sha256="b", cohort="two", capture_native_sha256="c"
    )
    row, evidence, native = results.observed.attempt(
        tmp_path, "DS26-1", "candidate", {"cases": {"DS26-1": case}}, method="test"
    )
    assert row["result"]["status"] == "timed_out" and native is None
    assert all(arm["latlon"] is None for arm in row["result"]["arms"].values())
    assert evidence["wall_to_failure_s"] == 112.25 and evidence["cpu_to_failure_s"] == 48
    assert evidence["failure_clock"] == "systemd service lifetime through terminal state"


def test_live_or_unverified_unit_retains_its_slot_until_reconciled(tmp_path, monkeypatch):
    spec = specification()
    case = spec["cases"][0]
    ident = case["id"]
    folder = tmp_path / ident
    attempt = folder / "control"
    attempt.mkdir(parents=True)
    (attempt / "service.log").write_text("unit handle")
    lock = dict(cases={ident: case}, receiver=str(tmp_path), detectors=spec, limit_s=90)
    calls = []

    def growing(attempt):
        raise trial.iq_service.UnsettledService("live service")

    def collect(*args):
        calls.append(args[4].name)
        args[4].mkdir()
        whole_iq.save_json(args[4] / "service.json", {"exit_code": 0})
        whole_iq.save_json(args[4] / "end.json", {})

    lock["detectors"] = {k: dict(spec[k], path=k) for k in trial.BRANCHES}
    monkeypatch.setattr(trial.whole_iq, "evaluate", collect)
    monkeypatch.setattr(trial.iq_service, "reconcile", growing)
    with pytest.raises(trial.iq_service.UnsettledService):
        trial.run_branches(lock, ident, folder)
    assert calls == [] and not (folder / "control-failure.json").exists()
    monkeypatch.setattr(
        trial.iq_service,
        "reconcile",
        lambda attempt: {"exit_code": None, "systemd": {"Result": "success"}},
    )
    whole_iq.save_json(attempt / "end.json", {})
    trial.run_branches(lock, ident, folder)
    trial.run_branches(lock, ident, folder)
    assert calls == ["candidate"] and not (folder / "control-failure.json").exists()


def test_duplicate_case_driver_leaves_both_arms_with_their_owner(tmp_path, monkeypatch):
    ident = "DS26-1"
    case = dict(request_sha256="a", recording={"count": 1})
    lock = dict(
        cases={ident: case},
        programs={},
        receiver=str(tmp_path),
        receiver_files={},
        native_sources={},
    )
    source = tmp_path / "source-lock.json"
    whole_iq.save_json(source, lock)
    (tmp_path / "source-lock.sha256").write_text(results._sha(source))
    folder = tmp_path / ident
    folder.mkdir()
    monkeypatch.setattr(whole_iq, "receiver_identity", lambda receiver: {})
    monkeypatch.setattr(whole_iq, "native_sources", lambda receiver: {})
    monkeypatch.setattr(
        whole_iq,
        "binding",
        lambda case_id: (dict(request={"sha256": "a"}, recording=case["recording"]), {}),
    )
    with (folder / ".run.lock").open("a") as current:
        trial.fcntl.flock(current, trial.fcntl.LOCK_EX)
        with pytest.raises(trial.iq_service.UnsettledService, match="another supervisor"):
            trial.run(tmp_path, ident)
        assert list(folder.iterdir()) == [folder / ".run.lock"]
