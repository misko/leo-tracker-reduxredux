"""Publish the frozen wide-factor original v5 comparison."""

import argparse
import gzip
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import original_v5
from . import wide_full_v5 as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

FULL = "original_full_v5_wide"
COMPACT = "compact_phase_release_wide"
V5_OPTIONS = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")


def _counter(state, key, divisor=1):
    value = state.get(key)
    return int(value) / divisor if value and value.isdecimal() else None


def run_resources(out, service):
    start = whole_iq.read(out / "start.json") if (out / "start.json").exists() else None
    end = whole_iq.read(out / "end.json") if (out / "end.json").exists() else None
    state = service["systemd"]
    if state.get("MainPID") != "0" or state.get("ControlPID") != "0":
        raise ValueError("service has no final manager process receipt")
    if start and (Path(start["cgroup"]).name != service["unit"] + ".service"):
        raise ValueError("original v5 service and measured cgroup differ")
    if start:
        group = Path(start["cgroup"])
        if not group.is_relative_to("/sys/fs/cgroup"):
            raise ValueError("original v5 service reported an invalid cgroup path")
        events = group / "cgroup.events"
        if events.exists() and "populated 0" not in events.read_text().splitlines():
            raise ValueError("original v5 cgroup still has a live process")
    for mark in (start, end):
        if mark and (
            mark["cgroup"] != start["cgroup"]
            or mark["memory.max"] != trial.MEMORY
            or mark["memory.swap.max"] != 0
            or mark["memory.swap.current"] != 0
        ):
            raise ValueError("original v5 left its diagnostic resource cap")
    if start and end:
        wall = end["monotonic_s"] - start["monotonic_s"]
        cpu = (end["cpu_usec"] - start["cpu_usec"]) / 1e6
        if wall < 0 or cpu < 0:
            raise ValueError("original v5 stage clocks moved backward")
        peak, clock = end["memory.peak"], "worker_cgroup_markers"
    else:
        entered = _counter(state, "ActiveEnterTimestampMonotonic", 1e6)
        stopped = _counter(state, "InactiveEnterTimestampMonotonic", 1e6)
        wall = stopped - entered if entered and stopped and stopped >= entered else None
        cpu = _counter(state, "CPUUsageNSec", 1e9)
        peak, clock = _counter(state, "MemoryPeak"), "systemd_manager"
    return dict(
        service=service,
        start=start,
        end=end,
        wall_s=wall,
        cpu_s=cpu,
        peak_bytes=peak,
        clock=clock,
        cap_bytes=trial.MEMORY,
    )


def official_result(out, request, service, resources, log):
    evidence = out / "original-output"
    receipt = evidence / "worker-result.json"
    state = service["systemd"]["Result"]
    if state == "success" and service["exit_code"] == 0 and receipt.exists():
        worker = whole_iq.read(receipt)
        if (
            worker["status"] != "complete"
            or worker["role"] != request["role"]
            or worker["policy"] != request["policy"]
            or worker["model"] != request["model"]
            or worker["request_sha256"] != trial.digest(request)
            or worker["source_sha256"] != request["source"]["sha256"]
            or worker["native_manifest_sha256"] != trial.digest(request["native_manifest"])
            or set(worker["arms"]) != set(ARMS)
            or set(worker["prediction_rows"]) != set(ARMS)
            or resources["end"]["worker_exit_code"] != 0
        ):
            raise ValueError("official original v5 result differs from its bound parameters")
        archive = evidence / original_v5.EVIDENCE
        if (
            worker["artifact"]["path"] != str(archive)
            or worker["artifact"]["bytes"] != archive.stat().st_size
        ):
            raise ValueError("the original v5 worker returned a different evidence archive")
        whole_iq.checked(archive, worker["artifact"]["sha256"])
        result = original_v5._result(worker, resources["wall_s"])
    else:
        text = log.read_text(errors="replace")
        if state == "timeout" or "Native job stage deadline exceeded" in text:
            status = "timed_out"
        elif "Complete science and every PNG required: no_active_curvature" in text:
            status = "withheld"
        else:
            status = "failed"
        detail = next((line for line in reversed(text.splitlines()) if "Error:" in line), state)
        result = original_v5._no_fix("baseline", status, detail, resources["wall_s"])
    validate_result(result)
    return result, receipt if receipt.exists() else None


def seal(work, report):
    source = whole_iq.checked(
        report / "source-lock.json", whole_iq.read(work / "launch-lock.json")["source_sha256"]
    )
    pins = whole_iq.read(source)
    whole_iq.checked(report / "PROTOCOL.md", pins["protocol_sha256"])
    whole_iq.checked(Path(trial.__file__), pins["launcher_sha256"])
    files = ["source-lock.json", "positions.jsonl.gz", "resources.json", "PROTOCOL.md"]
    predictions, evidence = [], {}
    for ident, item in pins["cases"].items():
        out = work / ident
        request = whole_iq.read(
            whole_iq.checked(out / "request.json", item["rebound_request_sha256"])
        )
        whole_iq.checked(out / "native.json", item["compact"]["native_sha256"])
        service = whole_iq.read(out / "service.json")
        log = whole_iq.checked(out / "service.log", service["log_sha256"])
        resources = run_resources(out, service)
        result, worker = official_result(out, request, service, resources, log)
        evidence[ident] = dict(full=resources, compact=item["compact_resources"])
        compact = dict(
            item["compact"],
            method=COMPACT,
            capture_era_native_sha256=item["original_native_sha256"],
        )
        compact.pop("paired_ordinary_sha256", None)
        full = dict(
            compact, method=FULL, input_sha256=item["rebound_request_sha256"], result=result
        )
        predictions.extend((full, compact))
        logfile = f"{ident}-service.log"
        write(report / logfile, log.read_bytes())
        files.append(logfile)
        if worker is not None:
            receipt = f"{ident}-worker-result.json.gz"
            write(report / receipt, gzip.compress(worker.read_bytes(), compresslevel=6, mtime=0))
            files.append(receipt)
    pack(report / "positions.jsonl.gz", predictions)
    save_json(report / "resources.json", evidence)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(pins["cases"]),
            files={name: _sha(report / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(records, references, resources):
    measurements = {(row["id"], row["method"]): row["result"] for row in records}
    rows = []
    for ident, ref in references.items():
        for arm in ARMS:
            capture = {method: ref["reference"][method][arm] for method in V5_OPTIONS}
            baseline = capture["baseline"]["error_km"]
            fits = dict(capture)
            for method in (FULL, COMPACT):
                result = measurements[ident, method]
                fit = result["arms"][arm]
                fits[method] = dict(
                    fit,
                    status=result["status"],
                    error_km=distance_km(ref["truth"], fit["latlon"]),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                )
            full, compact = (fits[method]["error_km"] for method in (FULL, COMPACT))
            for method, fit in fits.items():
                error = fit["error_km"]
                latitude, longitude = fit["latlon"] or (None, None)
                stock = resources[ident]["full"] if method == FULL else {}
                compact_service = resources[ident]["compact"] if method == COMPACT else {}
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=fit["status"],
                        published=latitude is not None,
                        latitude=latitude,
                        longitude=longitude,
                        error_km=error,
                        original_capture_km=baseline,
                        within_5pct=error is not None
                        and baseline is not None
                        and error <= 1.05 * baseline,
                        within_10pct=error is not None
                        and baseline is not None
                        and error <= 1.10 * baseline,
                        original_full_minus_compact_wide_km=full - compact
                        if method == FULL and full is not None and compact is not None
                        else None,
                        original_full_wide_minus_capture_km=full - baseline
                        if method == FULL and full is not None and baseline is not None
                        else None,
                        rms_hz=fit.get("rf_rms_hz"),
                        rms_kind="compact conditional"
                        if method == COMPACT
                        else "original residual",
                        frequency_score=fit.get("frequency_score"),
                        original_wide_worker_wall_s=stock.get("wall_s"),
                        original_wide_worker_cpu_s=stock.get("cpu_s"),
                        original_wide_peak_bytes=stock.get("peak_bytes"),
                        compact_wide_position_wall_s=compact_service.get("position_s"),
                        compact_wide_full_iq_wall_s=compact_service.get("wall_s"),
                    )
                )
    return rows


def score(report):
    seal = whole_iq.read(report / "prediction-lock.json")
    for name, digest in seal["files"].items():
        whole_iq.checked(report / name, digest)
    cases = seal["cases"]
    _, references = held_references(None, cases)
    records = rows_from(report / "positions.jsonl.gz")
    if {(row["id"], row["method"]) for row in records} != {
        (case, method) for case in cases for method in (FULL, COMPACT)
    }:
        raise ValueError("wide factor comparison must retain all original and compact attempts")
    scores = score_rows(
        records, {r["id"]: r for r in references}, whole_iq.read(report / "resources.json")
    )
    csv_file(report / "scores.csv", scores)
    provenance = ["source-lock.json", "prediction-lock.json", "resources.json", "scores.csv"]
    save_json(
        report / "figure-lock.json",
        dict(cases=cases, files={f: _sha(report / f) for f in ["positions.jsonl.gz", *provenance]}),
    )
    matches = ["native_sha256", "catalog_sha256", "tile", "original_request_sha256"]
    chart = dict(
        id="wide-full-v5",
        method=FULL,
        scope="roof",
        cases=cases,
        title="Original full v5 and compact on identical wide GLRT factors",
        caption=(
            "Both methods receive the same complete four-start ±800 kHz factors. "
            "The four original v5 references use capture-era factors. One roof."
        ),
        seal="figure-lock.json",
        provenance=provenance,
        series=[
            dict(
                key="one",
                label="Original full v5 · wide GLRT",
                file="positions.jsonl.gz",
                value=FULL,
                native_field="capture_era_native_sha256",
            ),
            dict(
                key="stock",
                label="Compact phase-release · wide GLRT",
                file="positions.jsonl.gz",
                value=COMPACT,
                native_field="capture_era_native_sha256",
                match=matches,
            ),
        ],
    )
    save_json(report / "figures.json", dict(version=1, charts=[chart]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)


if __name__ == "__main__":
    main()
