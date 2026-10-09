"""Synthetic full pilot coverage and frozen progression criteria."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("report110", Path(__file__).with_name("report.py"))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def fixture():
    members, rows = [], []
    for dataset in ("DS16", "DS17", "DS18"):
        for index in range(4):
            member = dict(dataset=dataset, inventory_label=f"{dataset}-{index}")
            members.append(dict(member=member))
            fit = dict(
                converged=True,
                independently_feasible=True,
                independent_stationarity=0.0001,
                posterior_rms_hz=60.0,
                elapsed_s=10.0,
                evaluations=50,
                optimizer_iterations_reported=None,
            )
            rows.append(
                dict(
                    member=member,
                    protocol_sha256="digest",
                    status="complete",
                    errors={
                        v: {a: e for a in report.ARMS}
                        for v, e in (("archive", 1.2), ("0.0", 1.0), ("0.5", 0.8))
                    },
                    raw={
                        rho: {
                            a: dict(status="complete", fit=copy.deepcopy(fit)) for a in report.ARMS
                        }
                        for rho in ("0.0", "0.5")
                    },
                    operational={
                        rho: {a: dict(fallback=False) for a in report.ARMS}
                        for rho in ("0.0", "0.5")
                    },
                )
            )
    plan = dict(
        members=members,
        progression_gates=dict(
            fitted_mean_improvement_fraction_minimum=0.05,
            both_arms_maximum_paired_regression_km=1,
            zero_c_mean_maximum_worsening_fraction=0.05,
            absolute_fit_budget_seconds=90,
        ),
    )
    return plan, rows


def test_full_pilot_passes_and_archive_is_separate():
    plan, rows = fixture()
    summary = report.summarize(plan, rows, "digest")
    assert summary["complete"] and summary["gates"]["passed"]
    pooled = summary["groups"]["Pooled"]
    assert pooled["position"]["fitted-c"]["archive"]["mean"] == pytest.approx(1.2)
    assert pooled["comparisons"]["zero-c"]["0.0-archive"]["mean_delta_km"] == pytest.approx(-0.2)
    assert pooled["raw"]["fitted-c"]["0.5"]["optimizer_iterations_reported"] is None
    assert pooled["recording_peak_memory_bytes"] is None


def test_incomplete_withholds_every_aggregate_and_gates(tmp_path):
    plan, rows = fixture()
    summary = report.summarize(plan, rows[:-1], "digest")
    assert summary["gates"] is None
    assert all(g["position"] is None for g in summary["groups"].values())
    assert summary["coverage"][-1]["status"] == "pending"
    assert not report.plot(summary, rows[:-1], tmp_path / "absent.png")


def test_failed_input_not_replaced():
    plan, rows = fixture()
    rows[0] = dict(
        member=rows[0]["member"], protocol_sha256="digest", status="failed", error="input"
    )
    summary = report.summarize(plan, rows, "digest")
    assert not summary["complete"] and len(summary["coverage"]) == 12
    assert summary["groups"]["Pooled"]["raw"]["fitted-c"]["0.5"]["qualified"] == 11


def test_fallback_never_passes_qualification_gate():
    plan, rows = fixture()
    rows[0]["raw"]["0.5"]["fitted-c"] = dict(status="failed", error="timeout")
    rows[0]["operational"]["0.5"]["fitted-c"]["fallback"] = True
    summary = report.summarize(plan, rows, "digest")
    assert summary["complete"] and not summary["gates"]["checks"]["all48_raw_qualified"]


def test_actual_elapsed_over_budget_fails_even_when_qualified():
    plan, rows = fixture()
    rows[0]["raw"]["0.5"]["zero-c"]["fit"]["elapsed_s"] = 90.01
    summary = report.summarize(plan, rows, "digest")
    assert summary["gates"]["checks"]["all48_raw_qualified"]
    assert not summary["gates"]["checks"]["actual_elapsed"]


def test_regression_and_wrong_protocol_rejected():
    plan, rows = fixture()
    rows[0]["errors"]["0.5"]["zero-c"] = 2.1
    summary = report.summarize(plan, rows, "digest")
    assert not summary["gates"]["checks"]["paired_regressions"]
    assert not summary["gates"]["checks"]["worst"]
    with pytest.raises(AssertionError):
        report.summarize(plan, rows, "stale")


def test_synthetic_plot(tmp_path):
    plan, rows = fixture()
    assert report.plot(report.summarize(plan, rows, "digest"), rows, tmp_path / "synthetic.png")
    assert (tmp_path / "synthetic.png").stat().st_size > 1000


def test_controller_crash_unlaunched_and_stale_claim(tmp_path):
    member = dict(inventory_label="synthetic", dataset="DS16")
    unlaunched = report.controller_state(tmp_path, member, "digest", "pending")
    assert unlaunched["controller_status"] == "unlaunched"
    folder = tmp_path / "controller-claims"
    folder.mkdir()
    claim = folder / "synthetic.json"
    claim.write_text(json.dumps(dict(member=member, protocol_sha256="digest")))
    (folder / "synthetic.exit.json").write_text(
        json.dumps(
            dict(
                member=member,
                protocol_sha256="digest",
                status="exited",
                returncode=7,
                error="synthetic crash",
            )
        )
    )
    crashed = report.controller_state(tmp_path, member, "digest", "pending")
    assert crashed["controller_status"] == "claimed-without-terminal"
    assert crashed["returncode"] == 7 and crashed["error"] == "synthetic crash"
    assert crashed["claim"] == "controller-claims/synthetic.json"
    assert (
        report.controller_state(tmp_path, member, "digest", "failed")["controller_status"]
        == "terminal"
    )
    with pytest.raises(AssertionError):
        report.controller_state(tmp_path, member, "stale", "pending")
