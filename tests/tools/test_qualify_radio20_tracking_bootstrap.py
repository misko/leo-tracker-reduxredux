"""Qualification cannot promote incomplete, stale, or false-positive startup."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "radio20_qualification",
    Path(__file__).resolve().parents[2] / "tools/qualify_radio20_tracking_bootstrap.py",
)
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


def result():
    rows = []
    for index in range(14):
        ready = index in (1, 2, 3)
        rows.append(
            dict(
                case=index,
                acquisition_supported=int(index < 8),
                resolver_us=440000,
                total_us=710000,
                past_jobs=60 if ready else 8,
                status=2 if ready else -1,
                failure=0 if ready else 4,
                available_through=10_000_000,
                handoff=dict(start=10_002_500),
            )
        )
    return dict(scope=q.SCOPE, plan_us=5700, cases=rows, ready_cases=3, control_ready_cases=0)


def test_complete_numerical_replay_is_not_live_tracking_qualification():
    assessment = q.assess(result())
    assert assessment["baseline_reproduced"]
    assert assessment["ready_signal_cases"] == [1, 2, 3]
    assert assessment["unsupported_signal_cases"] == [0, 4, 5, 6, 7]
    assert not assessment["all_accepted_cases_handed_off"]
    assert not assessment["live_tracking_qualified"]


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "counts",
        "nan",
        "negative_time",
        "over_budget",
        "stale",
        "failure",
        "unknown",
        "jobs",
        "scope",
    ],
)
def test_incomplete_or_invalid_evidence_is_rejected(damage):
    data = result()
    if damage == "missing":
        data["cases"].pop()
    if damage == "duplicate":
        data["cases"][2] = deepcopy(data["cases"][1])
    if damage == "counts":
        data["ready_cases"] = 4
    if damage == "nan":
        data["cases"][0]["total_us"] = float("nan")
    if damage == "negative_time":
        data["cases"][0]["resolver_us"] = -1
    if damage == "over_budget":
        data["cases"][0]["total_us"] = 4_000_000
    if damage == "stale":
        data["cases"][1]["handoff"]["start"] -= 1
    if damage == "failure":
        data["cases"][1]["failure"] = 4
    if damage == "unknown":
        data["cases"][0]["status"] = 0
    if damage == "jobs":
        data["cases"][0]["past_jobs"] = 201
    if damage == "scope":
        data["scope"] = "live"
    with pytest.raises(ValueError):
        q.assess(data)


def test_control_handoff_is_visible_and_fails_the_gate():
    data = result()
    data["cases"][8].update(status=2, failure=0)
    data.update(ready_cases=4, control_ready_cases=1)
    assessment = q.assess(data)
    assert assessment["ready_control_cases"] == [8]
    assert not assessment["baseline_reproduced"]


def attestation():
    return dict(
        serial=q.SERIAL,
        firmware=q.FIRMWARE,
        boot_id="a044a122-056f-44b5-b550-73d392576d21",
        fit_partition_sha256="a" * 64,
        buffer_3="0",
        buffer_5="0",
        out_altvoltage1_TX_LO_powerdown="1",
        timeout_command="/usr/bin/timeout",
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("serial", "different"),
        ("firmware", "unknown"),
        ("buffer_5", "1"),
        ("out_altvoltage1_TX_LO_powerdown", "0"),
        ("boot_id", ""),
        ("fit_partition_sha256", ""),
    ],
)
def test_wrong_device_active_rx_or_missing_deadline_refuses_deployment(key, value):
    fields = attestation()
    fields[key] = value
    with pytest.raises(ValueError):
        q.parse_attestation("\n".join(f"{k}={v}" for k, v in fields.items()))


def test_payload_hash_change_and_unexpected_file_are_rejected(tmp_path):
    path = tmp_path / "payload"
    path.write_bytes(b"expected")
    manifest = dict(
        payload={n: dict(path=str(path), sha256=q.digest(b"expected")) for n in q.PAYLOAD_NAMES},
        source_sha256={},
    )
    assert set(q.payload(manifest)) == set(q.PAYLOAD_NAMES)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity"):
        q.payload(manifest)
    path.write_bytes(b"expected")
    manifest["payload"]["unexpected"] = dict(path=str(path), sha256=q.digest(b"expected"))
    with pytest.raises(ValueError, match="unexpected"):
        q.payload(manifest)
