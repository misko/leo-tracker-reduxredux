import hashlib
import json
from pathlib import Path

import pytest
from report_cohort import (
    aggregate,
    compact_receipt,
    evaluation_callback,
    load_rows,
    publish,
    summarize,
)


def rows():
    result = []
    for i in range(12):
        operation = dict(
            fit=dict(converged=True, stationarity=0.0001, objective=1.0, posterior_rms_hz=2.0)
        )
        phases = dict(search=dict(status="complete"))
        phases.update(
            {
                b: dict(
                    status="complete", operational={a: operation for a in ("fitted-c", "zero-c")}
                )
                for b in ("native", "fixed")
            }
        )
        result.append(dict(label=str(i), dataset=("DS16", "DS17", "DS18")[i // 4], phases=phases))
    return result


def test_gate_requires_all12_and_failure_subset_is_explicit():
    values = rows()
    values[-1]["phases"]["fixed"] = dict(status="missing")
    with pytest.raises(ValueError, match="all twelve"):
        summarize(values, evaluate=lambda *args: pytest.fail("reference accessed"))
    with pytest.raises(ValueError, match="all twelve"):
        evaluation_callback({}, values)
    values[-1]["phases"]["fixed"] = dict(status="failed", operational={})
    result = summarize(
        values, evaluate=lambda label, branch, arm, operation: 1.0 if branch == "native" else 2.0
    )
    assert result["all_terminal"] and not result["full_comparison_complete"]
    metrics = aggregate(result)
    assert metrics["all12"]["fitted-c"]["paired"] == 11
    assert metrics["all12"]["fitted-c"]["missing"] == 1
    assert not metrics["all12"]["fitted-c"]["full_dataset_metrics_available"]
    assert metrics["DS18"]["zero-c"]["regressions_over_0_1km"] == 3


def test_missing_selected_endpoint_not_a_complete_comparison_and_no_unqualified_fallthrough():
    values = rows()
    values[0]["phases"]["native"]["operational"] = {}
    assert not summarize(values)["full_comparison_complete"]
    values = rows()
    values[0]["phases"]["native"]["operational"]["fitted-c"]["fit"]["converged"] = False
    with pytest.raises(ValueError, match="unqualified"):
        summarize(values)


def test_compact_evidence_preserves_failures_runtime_and_qualification_without_raw_arrays():
    receipt = dict(
        status="complete",
        elapsed_s=12.0,
        reasons=["one regional failure"],
        regions={
            "retained-0": dict(
                recovery=dict(result=dict(status="prefit-unqualified", calibration=None)),
                association=dict(result=None),
                finals=[
                    dict(arm="fitted-c", fit=dict(converged=False)),
                    dict(arm="zero-c", fit=dict(converged=True)),
                ],
            )
        },
        attempts={
            "B3": {"fitted-c": dict(converged=True), "zero-c": dict(converged=False)},
            "removed_satellites": [1, 2],
        },
    )
    result = compact_receipt(receipt)
    assert result["reasons"] == ["one regional failure"] and result["elapsed_s"] == 12.0
    assert result["regions"][0]["calibration_status"] == "prefit-unqualified"
    assert result["regions"][0]["finals"]["fitted-c"] == dict(attempts=1, qualified=0)
    assert result["joint_stages"] == {"B3": {"fitted-c": True, "zero-c": False}}


def test_publisher_rejects_incomplete_before_writing(tmp_path):
    with pytest.raises(ValueError, match="seal"):
        publish(dict(all_terminal=False), {}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_receipt_hash_covers_raw_associations_but_compact_report_keeps_only_fit_and_selection(
    tmp_path,
):
    phase = tmp_path / "sample/native"
    phase.mkdir(parents=True)
    raw = dict(
        status="complete",
        protocol_sha256="digest",
        label="sample",
        branch="native",
        fallback_available=False,
        operational={
            "fitted-c": dict(
                fit=dict(converged=True, vector=[1, 2]), basin="region", association=[1, 2, 3]
            )
        },
    )
    path = phase / "result.json"
    path.write_text(json.dumps(raw))
    result, hashes = load_rows(
        dict(members=[dict(label="sample", dataset="DS16")]), tmp_path, "digest"
    )
    operation = result[0]["phases"]["native"]["operational"]["fitted-c"]
    assert operation["fit"]["vector"] == [1, 2] and operation["basin"] == "region"
    assert "association" not in operation
    assert hashes[str(path)] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_invocation_timing_sums_pending_and_terminal_instead_of_only_terminal_elapsed(tmp_path):
    phase = tmp_path / "sample/native"
    slices = phase / "slices"
    slices.mkdir(parents=True)
    base = dict(protocol_sha256="digest", label="sample", branch="native", fallback_available=False)
    (phase / "result.json").write_text(json.dumps(dict(base, status="complete", elapsed_s=5)))
    for slot, status, elapsed in [(1, "pending", 3), (2, "complete", 5)]:
        (slices / f"baseline-{slot:02}.done.json").write_text(
            json.dumps(dict(base, status=status, elapsed_s=elapsed))
        )
    result, _ = load_rows(dict(members=[dict(label="sample", dataset="DS16")]), tmp_path, "digest")
    value = result[0]["phases"]["native"]
    assert value["elapsed_s"] == 5 and value["recorded_invocation_elapsed_s"] == 8
    assert [v["status"] for v in value["invocation_timing"]] == ["pending", "complete"]
    for timing in value["invocation_timing"]:
        assert hashlib.sha256(Path(timing["path"]).read_bytes()).hexdigest() == timing["sha256"]
    path = slices / "baseline-02.done.json"
    foreign = json.loads(path.read_text())
    foreign["protocol_sha256"] = "other"
    path.write_text(json.dumps(foreign))
    with pytest.raises(ValueError, match="foreign"):
        load_rows(dict(members=[dict(label="sample", dataset="DS16")]), tmp_path, "digest")
