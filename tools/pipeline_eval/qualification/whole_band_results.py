"""Seal every full-recording attempt before scoring the two GLRT search spans."""

import argparse
import gzip
import json
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import fractional_runtime_whole as parity
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_band_trial import REPORT

METHOD = {"narrow": "ordinary_narrow_full_iq", "wide": "regional_wide_full_iq"}
COMMON = ("raw_authority", "clock_sha256", "excluded_sha256", "probes_sha256")


def attempt(root, case, arm, lock, *, method=None):
    run = root / case / arm
    terminal = run / "service.json"
    failure = root / case / f"{arm}-failure.json"
    if not terminal.is_file() and not failure.is_file():
        raise ValueError(f"{case}/{arm} has no terminal attempt receipt")
    service = whole_iq.read(terminal) if terminal.is_file() else {"exit_code": None}
    inputs = lock["cases"][case]
    row = dict(
        id=case,
        method=METHOD[arm] if method is None else method,
        tile=inputs["tile"],
        mode="matched-tile",
        catalog_sha256=inputs["catalog_sha256"],
        original_request_sha256=inputs["request_sha256"],
        cohort=inputs["cohort"],
    )
    if "ordinary_sha256" in inputs:
        row["paired_ordinary_sha256"] = inputs["ordinary_sha256"]
    else:
        row["paired_capture_sha256"] = inputs["capture_native_sha256"]
    plan_path = run / "plan.json"
    if plan_path.exists():
        plan = whole_iq.read(plan_path)
        if (
            plan["case"] != case
            or plan["detector_sha256"] != lock["detectors"][arm]["sha256"]
            or plan["cpus"] != inputs["cpus"]
            or plan["receiver_files"] != lock["receiver_files"]
            or plan["capture_era_request"] != inputs["request_sha256"]
            or plan["recording"] != inputs["recording"]
        ):
            raise ValueError("attempt does not match frozen detector, receiver or recording")
    failed = failure.exists() or not iq_service.succeeded(service)
    data = {"service": service}
    if failed:
        unit_result = service.get("systemd", {}).get("Result")
        error = whole_iq.read(failure)["error"] if failure.exists() else str(service)
        reason = f"{unit_result}: {error}" if unit_result else error
        timed = service.get("exit_code") == 124 or unit_result == "timeout"
        row["result"] = dict(
            status="timed_out" if timed else "failed",
            reason=reason,
            boundary="Full saved IQ through position",
            metrics={},
            arms={name: {"latlon": None} for name in ARMS},
        )
        data["failure"] = reason
        data["wall_to_failure_s"] = service.get("supervisor_s")
        if data["wall_to_failure_s"] is None and service.get("service_wall_s") is not None:
            data["wall_to_failure_s"] = service["service_wall_s"]
            data["failure_clock"] = "systemd service lifetime through terminal state"
        accounting = service.get("systemd", {})
        for name, key, scale in (
            ("cpu_to_failure_s", "CPUUsageNSec", 1e9),
            ("charged_peak_to_failure_bytes", "MemoryPeak", 1),
        ):
            if str(accounting.get(key, "")).isdigit():
                data[name] = int(accounting[key]) / scale
        if not (run / "raw.json").is_file():
            return row, data, None
    if not plan_path.is_file():
        raise ValueError("a completed stage must bind its inputs")
    raw = whole_iq.read(run / "raw.json")
    start = whole_iq.read(run / "start.json")
    stages = [start, raw["raw_end"], raw["position_start"]]
    if not failed:
        stages.append(whole_iq.read(run / "end.json"))
    for stage in stages:
        if (
            stage["cgroup"] != start["cgroup"]
            or stage["memory.max"] != lock["memory_max"]
            or stage["memory.swap.max"] != 0
            or stage["memory.swap.current"] != 0
            or stage["memory.events.oom_kill"]
        ):
            raise ValueError("full recording left its measured cgroup or resource limit")
    if not (
        start["cpus"] == inputs["cpus"]
        and all(s["cpus"] == inputs["cpus"][:1] for s in stages[1:])
        and all(
            a["monotonic_s"] <= b["monotonic_s"]
            for a, b in zip(stages[:-1], stages[1:], strict=True)
        )
        and raw["counts"]["recording_windows"] == inputs["recording"]["window_count"]
        and raw["input_manifest_sha256"] == inputs["clock_authority"]
    ):
        raise ValueError("recorded CPU, timing, window or input provenance changed")
    native = whole_iq.checked(run / "recording/native.json", raw["native_sha256"])
    if arm == "narrow":
        parity.verify_native(
            whole_iq.read(native), inputs["ordinary_sha256"], plan["detector_sha256"]
        )
    request = whole_iq.checked(run / "recording/request.json", raw["request_sha256"])
    times = [t for lane in raw["lanes"] for t in lane["native_timings_s"]]
    data.update(
        counts=raw["counts"],
        **{k: raw[k] for k in COMMON},
        detector_sha256=plan["detector_sha256"],
        raw_s=stages[1]["monotonic_s"] - start["monotonic_s"],
        assembly_s=stages[2]["monotonic_s"] - stages[1]["monotonic_s"],
        dual_calls=len(times),
        within_20ms=sum(wall <= 0.02 for wall, _ in times),
        detector_call_wall_ms=distribution([1000 * wall for wall, _ in times]),
        detector_call_cpu_ms=distribution([1000 * cpu for _, cpu in times]),
        input_manifest_sha256=raw["input_manifest_sha256"],
        stages=stages,
        lanes=[{k: v for k, v in lane.items() if k != "native_timings_s"} for lane in raw["lanes"]],
    )
    row.update(input_sha256=_sha(request), native_sha256=_sha(native))
    if failed:
        return row, data, native
    end = stages[-1]
    data.update(
        wall_s=end["monotonic_s"] - start["monotonic_s"],
        position_s=end["monotonic_s"] - stages[2]["monotonic_s"],
        cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
        max_bytes=end["memory.peak"],
        swap_bytes=end["memory.swap.current"],
    )
    result = whole_iq.read(run / "position.json")
    validate_result(result)
    return dict(row, result=result), data, native


def pair_geometry(narrow, wide):
    if any(narrow.get(field) != wide.get(field) or not narrow.get(field) for field in COMMON):
        raise ValueError("the paired detector results used different waveform or probe support")


def seal(work, out):
    source = whole_iq.read(out / "source-lock.json")
    if source != whole_iq.read(work / "study.json"):
        raise ValueError("execution differs from the saved protocol")
    rows, evidence, files = [], {}, []
    for case in source["cases"]:
        evidence[case] = {}
        for arm in METHOD:
            row, receipt, native = attempt(work, case, arm, source)
            rows.append(row)
            evidence[case][arm] = receipt
            if arm == "wide" and native is not None:
                path = out / "native" / (case + ".json.gz")
                write(path, gzip.compress(native.read_bytes(), compresslevel=6, mtime=0))
                files.append(str(path.relative_to(out)))
        if all("raw_authority" in item for item in evidence[case].values()):
            pair_geometry(evidence[case]["narrow"], evidence[case]["wide"])
    pack(out / "positions.jsonl.gz", rows)
    save_json(out / "resources.json", evidence)
    files.extend(["positions.jsonl.gz", "resources.json", "source-lock.json"])
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(source["cases"]),
            files={f: _sha(out / f) for f in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score(out):
    lock = whole_iq.read(out / "prediction-lock.json")
    for name, checksum in lock["files"].items():
        whole_iq.checked(out / name, checksum)
    _, references = held_references(None, lock["cases"])
    by_id = {r["id"]: r for r in references}
    resources = whole_iq.read(out / "resources.json")
    records = list(
        map(json.loads, gzip.decompress((out / "positions.jsonl.gz").read_bytes()).splitlines())
    )
    scores = []
    for row in records:
        ident = row["id"]
        branch = next(k for k, v in METHOD.items() if v == row["method"])
        measurement = resources[ident][branch]
        ref = by_id[ident]
        for arm in ARMS:
            estimate = row["result"]["arms"][arm]
            original = ref["reference"]["baseline"][arm]["error_km"]
            error = (
                distance_km(ref["truth"], estimate["latlon"])
                if estimate["latlon"] is not None
                else None
            )
            scores.append(
                dict(
                    id=ident,
                    cohort=row["cohort"],
                    branch=branch,
                    arm=arm,
                    status=row["result"]["status"],
                    error_km=error,
                    original_v5_km=original,
                    within_5pct=error is not None and error <= 1.05 * original,
                    within_10pct=error is not None and error <= 1.10 * original,
                    conditional_rms_hz=estimate.get("rf_rms_hz"),
                    wall_s=measurement.get("wall_s"),
                    cpu_s=measurement.get("cpu_s"),
                    raw_s=measurement.get("raw_s"),
                    position_s=measurement.get("position_s"),
                )
            )
    csv_file(out / "scores.csv", scores)
    all_cases = lock["cases"]
    reserve = [
        case
        for case in all_cases
        if any(r["id"] == case and r["cohort"] == "additional reserve" for r in records)
    ]
    charts = []
    for suffix, cases, title in [
        ("six", all_cases, "Full-IQ position error with two GLRT frequency ranges"),
        ("reserve", reserve, "GLRT search bandwidth on two additional reserve recordings"),
    ]:
        # Each series file binds exactly the recordings advertised on this page.
        name = "positions.jsonl.gz" if suffix == "six" else "reserve.jsonl.gz"
        if suffix == "reserve":
            pack(out / name, [r for r in records if r["id"] in cases])
        chart_lock = f"{suffix}-figure-lock.json"
        save_json(
            out / chart_lock,
            dict(
                cases=cases,
                files={
                    f: _sha(out / f)
                    for f in (name, "prediction-lock.json", "resources.json", "scores.csv")
                },
            ),
        )
        charts.append(
            dict(
                id="whole-band-" + suffix,
                method=METHOD["wide"],
                scope="roof",
                cases=cases,
                title=title,
                seal=chart_lock,
                provenance=["prediction-lock.json", "resources.json", "scores.csv"],
                caption=(
                    "All eligible 20 ms visits on both receivers. Both runs use the same four "
                    "proposed epoch neighborhoods and differ in frequency span. Original v5 "
                    "used its capture-era detector. One physical roof."
                ),
                series=[
                    dict(
                        key=key,
                        label=label,
                        file=name,
                        value=METHOD[branch],
                        native_authority="ordinary",
                        native_field="paired_ordinary_sha256",
                        **(
                            {"match": ["tile", "catalog_sha256", "original_request_sha256", "mode"]}
                            if key == "stock"
                            else {}
                        ),
                    )
                    for key, branch, label in (
                        ("one", "wide", "Wide GLRT · ±800 kHz"),
                        ("stock", "narrow", "Narrow GLRT · ±400 kHz"),
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "score"))
    p.add_argument("--work", type=local_output)
    p.add_argument("--out", type=local_output, default=REPORT)
    args = p.parse_args()
    if args.action == "score":
        score(args.out)
    elif args.work:
        seal(args.work, args.out)
    else:
        p.error("seal requires --work")
