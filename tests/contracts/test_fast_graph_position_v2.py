"""The ALGO03 envelope cannot mutate v1 or publish unreviewed support."""

import copy

import pytest

from leo.contracts.fast_graph_position import CENTER, KIND
from leo.contracts.fast_graph_position import MODEL_VERSION as BASELINE_VERSION
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION, RF_CHECKS, validate_terminal


def terminal():
    arm = dict(
        endpoint_latlon=list(CENTER),
        endpoint_east_north_km=[0.0, 0.0],
        gates=dict(
            tracks=[
                dict(component="track", points=1, compatible=True, observation_ids=["old"], norad=1)
            ]
        ),
        linear_gates=[],
        final_phase_change_s=0.0,
        RMS_hz=100.0,
        negative_twice_elbo=1000.0,
    )
    baseline = dict(
        schema_version=1,
        kind=KIND,
        model_version=BASELINE_VERSION,
        input_sha256="sha256:input",
        state="complete",
        session_id="recording",
        qualification="paired_residual_phase_regional_gates",
        matched_c_inputs=True,
        arms={a: copy.deepcopy(arm) for a in ("c0", "fitted_c")},
        reference_usage="none",
        future_TLE_used=False,
        selected_arm="fitted_c",
        read_audit=dict(
            receipts=4,
            denied_paths=[],
            historical_result_or_GPS_reads=False,
            all_launched_processes_accounted=True,
        ),
        position=dict(latitude_deg=CENTER[0], longitude_deg=CENTER[1]),
    )
    selected_arm = dict(
        endpoint_latlon=list(CENTER),
        endpoint_east_north_km=[0.0, 0.0],
        negative_twice_elbo=900.0,
        associated_ids=["old", "new"],
        owners={"old": 1, "new": 2},
        added_points=1,
    )
    return dict(
        schema_version=2,
        kind=KIND,
        model_version=MODEL_VERSION,
        input_sha256="sha256:input",
        session_id="recording",
        state="complete",
        baseline=baseline,
        decision="ALGO03_single",
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
        baseline_seconds=100.0,
        recovery_seconds=20.0,
        total_seconds=120.0,
        read_audit=dict(verified=True, denied_paths=[], all_launched_processes_accounted=True),
        rf_checks=dict.fromkeys(RF_CHECKS, True),
        source_support={a: dict(owners={"old": 1}) for a in ("c0", "fitted_c")},
        selected=dict(
            kind="new_family",
            targets=[dict(norad=2, observation_ids=["new"])],
            arms={a: copy.deepcopy(selected_arm) for a in ("c0", "fitted_c")},
        ),
        position=copy.deepcopy(baseline["position"]),
    )


def test_separate_major_and_model_preserve_paired_support():
    doc = terminal()
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    assert doc["baseline"]["model_version"] == "algo02-causal-family-v1"
    assert MODEL_VERSION != BASELINE_VERSION


@pytest.mark.parametrize(
    "failure",
    [
        "identity",
        "source",
        "arm",
        "unscored",
        "duplicate",
        "audit",
        "gps",
        "future",
        "runtime",
        "coordinates",
        "objective",
        "rf",
    ],
)
def test_invalid_candidate_never_publishes(failure):
    doc = terminal()
    saved = doc["selected"]["arms"]["fitted_c"]
    if failure == "identity":
        doc["model_version"] = BASELINE_VERSION
    if failure == "source":
        doc["baseline"]["input_sha256"] = "changed"
    if failure == "arm":
        saved["owners"]["old"] = 9
    if failure == "unscored":
        saved["associated_ids"].append("incidental")
    if failure == "duplicate":
        saved["associated_ids"].append("new")
    if failure == "audit":
        doc["read_audit"]["verified"] = False
    if failure == "gps":
        doc["reference_usage"] = "GPS"
    if failure == "future":
        doc["future_TLE_used"] = True
    if failure == "runtime":
        doc["total_seconds"] = 20.0
    if failure == "coordinates":
        saved["endpoint_latlon"][0] += 0.1
    if failure == "objective":
        saved["negative_twice_elbo"] = float("nan")
    if failure == "rf":
        doc["rf_checks"][RF_CHECKS[0]] = False
    with pytest.raises(ValueError):
        validate_terminal(doc, input_sha256="sha256:input")


def test_fallback_may_preserve_baseline_after_failed_recovery_audit():
    doc = terminal()
    doc.update(decision="ALGO02_fallback", selected=None)
    doc["read_audit"]["verified"] = False
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    doc["position"]["latitude_deg"] += 0.01
    with pytest.raises(ValueError, match="exact ALGO02"):
        validate_terminal(doc, input_sha256="sha256:input")


def test_failure_and_malformed_result_do_not_publish():
    doc = terminal()
    doc["state"] = "failed"
    with pytest.raises(ValueError):
        validate_terminal(doc, input_sha256="sha256:input")


def test_baseline_missing_norad_uses_audited_owner_but_never_extra_support():
    doc = terminal()
    for arm in ("c0", "fitted_c"):
        del doc["baseline"]["arms"][arm]["gates"]["tracks"][0]["norad"]
    assert validate_terminal(doc, input_sha256="sha256:input") is doc
    for arm in ("c0", "fitted_c"):
        doc["source_support"][arm]["owners"]["incidental"] = 3
        doc["selected"]["arms"][arm]["owners"]["incidental"] = 3
        doc["selected"]["arms"][arm]["associated_ids"].append("incidental")
    with pytest.raises(ValueError, match="Source support"):
        validate_terminal(doc, input_sha256="sha256:input")
    doc = terminal()
    del doc["source_support"]
    with pytest.raises(ValueError):
        validate_terminal(doc, input_sha256="sha256:input")
