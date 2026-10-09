"""Synthetic reporting fixtures only; no recording/reference access."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("report106", Path(__file__).with_name("report.py"))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def fixture():
    bindings, rows = [], []
    for i, dataset in enumerate(("DS16", "DS17", "DS18")):
        member = dict(
            inventory_label=str(i), dataset=dataset, exposure="previously_evaluated_consumed"
        )
        bindings.append(dict(member=member, loader_binding=dict(kind="legacy_ds16")))
        fit = dict(
            converged=True,
            posterior_rms_hz=60.0,
            elapsed_s=1.0,
            evaluations=4,
            score_components=dict(frequency_nll=3.0, timing_prior=1.0, nuisance_prior=2.0),
            frequency_diagnostics=dict(
                maximum_assignment_unweighted_rms_hz=70.0,
                clock_l2=1.0,
                clutter_probability=[0.1, 0.2],
                assigned_satellite=[1, 0],
            ),
        )
        rows.append(
            dict(
                member=member,
                status="complete",
                protocol_sha256="digest",
                errors={
                    v: {a: e for a in report.ARMS}
                    for v, e in (("archive", 2.0), ("125", 1.0), ("100", 0.8))
                },
                raw={
                    v: {a: dict(status="complete", fit=fit) for a in report.ARMS}
                    for v in ("125", "100")
                },
                operational={
                    v: {a: dict(fit=fit, fallback=False, source="attempt") for a in report.ARMS}
                    for v in ("125", "100")
                },
            )
        )
    plan = dict(
        members=bindings,
        decision_criteria=dict(
            pooled_mean_minimum_improvement_fraction=0.05,
            pooled_median_minimum_improvement_fraction=0.05,
            maximum_dataset_mean_regression_fraction=0.05,
            maximum_pooled_p95_and_worst_regression_fraction=0.1,
        ),
    )
    return plan, rows


def test_complete_metrics_gates_and_exposure():
    plan, rows = fixture()
    summary = report.summarize(plan, rows, "digest")
    assert summary["complete"] and summary["gates"]["fitted-c"]["passed"]
    assert summary["groups"]["Pooled"]["position"]["zero-c"]["100"]["mean"] == pytest.approx(0.8)
    assert summary["groups"]["DS16-original48"]["membership"] == 1
    assert summary["groups"]["DS18-prior24"]["membership"] == 1
    assert (
        summary["groups"]["Pooled"]["comparisons"]["fitted-c"]["125-archive"]["mean_delta_km"] == -1
    )


def test_missing_and_failed_withhold_full_metrics_and_gates(tmp_path):
    plan, rows = fixture()
    rows[0] = dict(
        member=rows[0]["member"], status="failed", protocol_sha256="digest", error="input"
    )
    summary = report.summarize(plan, rows[:2], "digest")
    assert not summary["complete"] and summary["gates"] == {}
    assert summary["groups"]["Pooled"]["position"] is None
    assert [r["status"] for r in summary["coverage"]] == ["failed", "complete", "pending"]
    assert not report.plot(summary, rows, tmp_path / "not-written.png")


def test_bad_protocol_and_unknown_members_fail():
    plan, rows = fixture()
    with pytest.raises(AssertionError):
        report.summarize(plan, rows, "wrong")
    with pytest.raises(AssertionError):
        report.summarize(plan, rows + rows[:1], "digest")


def test_fallback_and_raw_failure_separate():
    plan, rows = fixture()
    rows[0]["raw"]["100"]["zero-c"] = dict(status="failed", error="timeout")
    rows[0]["operational"]["100"]["zero-c"].update(fallback=True, source="125-control")
    summary = report.summarize(plan, rows, "digest")
    d = summary["groups"]["Pooled"]["available_diagnostics"]["zero-c"]["100"]
    assert d["raw_failed"] == d["fallbacks"] == 1
    assert d["raw_qualified"] == 2


def test_synthetic_plot(tmp_path):
    plan, rows = fixture()
    assert report.plot(report.summarize(plan, rows, "digest"), rows, tmp_path / "synthetic.png")
    assert (tmp_path / "synthetic.png").stat().st_size > 1000


def test_metadata_file_binding_and_custom_reference(tmp_path):
    document = dict(
        session_id="synthetic",
        input_manifest_sha256="input",
        prior_latitude_deg=10.0,
        prior_longitude_deg=20.0,
        prior_radius_km=100.0,
        reference_latitude_deg=10.0,
        reference_longitude_deg=20.0,
    )
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(document))
    binding = dict(
        member=dict(session_id="synthetic"),
        loader_binding=dict(baseline_path="baseline.json", effective_input_digest="input"),
    )
    plan = dict(source_sha256={"baseline.json": hashlib.sha256(path.read_bytes()).hexdigest()})
    actual, authority = report.evaluation_document(binding, plan, root=tmp_path)
    assert actual == document and authority["kind"] == "frozen-file-sha256"
    assert report.position_error([0, 0], actual) == pytest.approx(0, abs=1e-10)
    actual["reference_longitude_deg"] = 20.01
    assert 1 < report.position_error([0, 0], actual) < 1.2
    path.write_text("{}")
    with pytest.raises(AssertionError):
        report.evaluation_document(binding, plan, root=tmp_path)


def test_public_metadata_requires_original_digest(tmp_path):
    from leo.contracts.digests import canonical_digest

    document = dict(session_id="synthetic", input_manifest_sha256="input")
    binding = dict(
        member=dict(session_id="synthetic"),
        loader_binding=dict(
            kind="published",
            baseline_path=None,
            effective_input_digest="input",
            baseline_document_digest=canonical_digest(document),
        ),
    )
    actual, _ = report.evaluation_document(
        binding, dict(source_sha256={}), root=tmp_path, status_reader=lambda _: document
    )
    assert actual == document
    with pytest.raises(AssertionError):
        report.evaluation_document(
            binding,
            dict(source_sha256={}),
            root=tmp_path,
            status_reader=lambda _: dict(document, changed=True),
        )
