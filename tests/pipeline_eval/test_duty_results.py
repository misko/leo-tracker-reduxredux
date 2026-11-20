import csv
import gzip
import json
from itertools import permutations, product

import pytest

from tools.pipeline_eval.qualification import duty_results as duty
from tools.pipeline_eval.variants.channel_schedule import SCHEDULES


def write_records(path, records):
    with gzip.open(path, "wt") as stream:
        for row in records:
            stream.write(json.dumps(row) + "\n")


def _receipt(case, method, cpu, order):
    metrics = {"c0_conditional_rms_hz": 80, "fitted_c_conditional_rms_hz": 74}
    if method == "v5_core":
        metrics.update(initial_arm_fits=3, cavity_offered=True)
    if method in SCHEDULES:
        metrics.update(
            schedule=method,
            channels=list(SCHEDULES[method]),
            valid_visits_by_channel=[1] * 8,
            original_valid_visits=8,
            kept_valid_visits=4,
            original_probes=16,
            kept_probes=8,
        )
    elapsed = {"v5_core": 8, "v5_lean": 12, "orbit_projector": 4}.get(method, 6)
    return dict(
        id=case,
        method=method,
        cpu=cpu,
        execution_order=order,
        worker_wall_s=elapsed,
        call_s=elapsed - 1,
        input_sha256=f"{cpu:064x}",
        implementation_sha256="a" * 64,
        result=dict(
            status="ok",
            boundary="detector output to position",
            metrics=metrics,
            arms={"c0": {"latlon": [37, -122]}, "fitted_c": {"latlon": [37.02, -122]}},
        ),
    )


@pytest.fixture
def trials(tmp_path, monkeypatch):
    data, previous = tmp_path / "receipts", tmp_path / "checkpoints"
    data.mkdir()
    previous.mkdir()
    rows = {
        "channel": [
            _receipt(case, method, cpu, index)
            for cpu, (case, methods) in enumerate(
                zip(duty.TIMING_IDS, permutations(duty.CHANNELS), strict=True)
            )
            for index, method in enumerate(methods)
        ],
        "projector": [
            _receipt(case, method, cpu, index)
            for cpu, case in enumerate(duty.TIMING_IDS)
            for index, method in enumerate(duty.PROJECTOR if cpu % 2 == 0 else duty.PROJECTOR[::-1])
        ],
    }
    cases, old_rows = {}, []
    for cpu, case in enumerate(duty.TIMING_IDS):
        reference = dict(id=case, group=case.split("-")[0], truth=[37.01, -122])
        old_rows.extend(_receipt(case, method, cpu, 0) for method in ("v5_core", "v5_lean"))
        arms = old_rows[-1]["result"]["arms"]
        cases[case] = (reference, "confirmation", {"stages": {"cavity": arms, "final": arms}})
    monkeypatch.setattr(duty, "load_rows", lambda _: cases)
    write_records(previous / "paired.jsonl.gz", old_rows)
    for study in rows:
        write_records(data / f"{study}-pairs.jsonl.gz", rows[study])
    return data, previous, rows


def _iq_payload(case):
    modes = list(product(("original", "accelerated"), ("all", *SCHEDULES)))
    rows = []
    for i, (segment, sequence) in enumerate(product((3, 10), range(8))):
        channel = sequence + 1
        shift = i % 6
        order = modes[shift:] + modes[:shift]
        if i // 6 % 2:
            order.reverse()
        timing, equal = {}, {}
        for engine, schedule in modes:
            called = schedule == "all" or channel in SCHEDULES[schedule]
            name = f"{engine}/{schedule}"
            detector = 4 if engine == "original" else 2
            wall = (detector if i else 0.25) if called else 0.125
            timing[name] = dict(wall_s=wall, cpu_s=wall / 2, called=called)
            equal[name] = True if called else None
        rows.append(
            dict(
                visit=i,
                segment=segment,
                sequence=sequence,
                channel=channel,
                policy_status="processed" if i else "invalid_capture",
                iq_sha256="sha256:" + "d" * 64,
                n_candidates=4 if i else 0,
                order=order,
                timing=timing,
                equal=equal,
            )
        )
    return dict(
        case=case,
        cpus=[20],
        kernel_sha256="a" * 64,
        kernel_source_sha256="b" * 64,
        anchor_grid_sha256="c" * 64,
        rows=rows,
        archive_audit=dict(
            archived_probe_rows=30,
            exact_probe_rows=30,
            different_probe_keys=[],
            archive_exclusions_equal=True,
        ),
    )


def read_table(out, name):
    with (out / f"{name}.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def test_reports_failures_and_worker_version_drift_without_dropping_recordings(trials, tmp_path):
    data, previous, rows = trials
    case = duty.TIMING_IDS[0]
    channel = rows["channel"][1]
    channel["implementation_sha256"] = "b" * 64
    projector = rows["projector"][1]
    projector.pop("call_s")
    projector.pop("implementation_sha256")
    projector["result"] = dict(status="failed", reason="exit 1", boundary="worker", metrics={})
    for study, path_rows in rows.items():
        write_records(data / f"{study}-pairs.jsonl.gz", path_rows)
    for ident in duty.IQ_CASES:
        iq = _iq_payload(ident)
        iq["rows"][1]["equal"]["accelerated/all"] = False
        write_records(data / f"{ident}-iq.json.gz", [iq])
    assert len(duty.measurements(data, previous)) == 30
    out = tmp_path / "report"
    duty.build(data, previous, out)
    errors = read_table(out, "paired-errors")
    assert len(errors) == 60
    assert [r["error_km"] for r in errors if r["status"] == "failed"] == ["", ""]
    full = next(r for r in errors if r["method"] == "v5_lean" and r["arm"] == "fitted_c")
    assert full["fitted_minus_c0_rms_hz"] == "-6"
    assert float(full["fitted_minus_c0_error_km"]) == pytest.approx(0, abs=1e-9)
    distributions = read_table(out, "paired-distributions")
    pooled = [
        r for r in distributions if r["method"] == "orbit_projector" and r["dataset"] == "all"
    ]
    assert len(pooled) == 2
    assert {
        (r["attempts"], r["fixes"], r["lost_v5_fixes"], r["keeps_v5_10pct"]) for r in pooled
    } == {("6", "5", "1", "False")}
    timing = {(r["recording"], r["method"]): r for r in read_table(out, "paired-runtime")}
    assert timing[case, channel["method"]]["implementation_versions"] == "2"
    assert timing[case, "orbit_projector"]["speedup"] == ""
    assert timing[duty.TIMING_IDS[1], "orbit_projector"]["speedup"] == "3.0"
    iq_rows = read_table(out, "iq-timing")
    all_accel = next(r for r in iq_rows if r["engine"] == "accelerated" and r["schedule"] == "all")
    assert all_accel["unequal_reference"] == "1"
    odd_accel = next(
        r for r in iq_rows if r["engine"] == "accelerated" and r["schedule"] == "glrt_odd_channels"
    )
    assert (odd_accel["detector_calls"], odd_accel["processed"], odd_accel["invalid_capture"]) == (
        "8",
        "7",
        "1",
    )
    assert float(odd_accel["speedup_wall_vs_original_all"]) == pytest.approx(60.25 / 15.25)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("id", "wrong-recording", "frozen recording"),
        ("cpu", 99, "paired CPU"),
        ("execution_order", 1, "prescribed execution order"),
        ("worker_wall_s", 0, "invalid worker time"),
        ("input_sha256", "c" * 64, "frozen paired input"),
        ("implementation_sha256", "c" * 64, "changed implementation"),
    ],
)
def test_rejects_malformed_location_pairs(trials, field, value, error):
    data, previous, rows = trials
    rows["channel"][0][field] = value
    write_records(data / "channel-pairs.jsonl.gz", rows["channel"])
    with pytest.raises(ValueError, match=error):
        duty.measurements(data, previous)


def test_rejects_changed_control_but_scores_an_experimental_coordinate(trials):
    data, previous, rows = trials
    full, projector = rows["projector"][:2]
    projector["result"]["arms"]["c0"]["latlon"][0] += 0.01
    write_records(data / "projector-pairs.jsonl.gz", rows["projector"])
    assert duty.measurements(data, previous)[projector["id"], projector["method"]] == projector
    full["result"]["arms"]["c0"]["latlon"][0] += 0.01
    write_records(data / "projector-pairs.jsonl.gz", rows["projector"])
    with pytest.raises(ValueError, match="differs from the archived final"):
        duty.measurements(data, previous)


def test_rejects_iq_asymmetry_in_the_reported_detector_calls(tmp_path):
    for case in duty.IQ_CASES:
        iq = _iq_payload(case)
        iq["rows"][0]["timing"]["original/glrt_odd_channels"]["called"] = False
        write_records(tmp_path / f"{case}-iq.json.gz", [iq])
    with pytest.raises(ValueError, match="detector invocation changed"):
        duty.iq_rows(tmp_path)
