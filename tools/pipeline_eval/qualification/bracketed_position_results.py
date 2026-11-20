"""Seal measured bracketed-peak positions before joining frozen roof scores."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import bracketed_position as trial
from . import bracketed_position_edits as prepared
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

STOCK, CANDIDATE = "bracketed_wide_archive_control", "bracketed_peak_phase_release"
BOUNDARY = "Complete archived or privately promoted wide factors through installed phase-release"
FAMILIES = ("diagnostic", "held")
V5_OPTIONS = ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks")


def scientific(result):
    return dict(
        result, metrics={key: value for key, value in result["metrics"].items() if key != "stage_s"}
    )


def counter(state, key, scale=1):
    value = state.get(key)
    return int(value) / scale if value and value.isdecimal() else None


def service_result(out, cpu):
    service = whole_iq.read(out / "service.json")
    state = service["state"]
    whole_iq.checked(out / "service.log", service["log_sha256"])
    start, end = [
        whole_iq.read(out / f"{name}.json") if (out / f"{name}.json").exists() else None
        for name in ("start", "end")
    ]
    if any(state.get(key) != "0" for key in ("MainPID", "ControlPID")):
        raise ValueError("factor-only service is not terminal")
    for mark in (start, end):
        if mark is None:
            continue
        group = Path(mark["cgroup"])
        if group.name != service["unit"] + ".service" or mark["cgroup"] != start["cgroup"]:
            raise ValueError("factor-only service left the original cgroup")
        if (
            mark["cpus"] != [cpu]
            or mark["memory.max"] != whole_iq.MEMORY
            or mark["memory.swap.max"] != 0
            or mark["memory.swap.current"] != 0
        ):
            raise ValueError("factor-only service changed CPU or resource limits")
    if start:
        group = Path("/sys/fs/cgroup") / start["cgroup"].lstrip("/")
        events = group / "cgroup.events"
        if events.exists() and "populated 0" not in events.read_text().splitlines():
            raise ValueError("factor-only service still has live work")
    if service["exit_code"] == 0 and state["Result"] == "success" and end:
        result = whole_iq.read(out / "position.json")
        if end["memory.events.oom_kill"] or end["monotonic_s"] < start["monotonic_s"]:
            raise ValueError("completed factor-only service has inconsistent counters")
        wall = end["monotonic_s"] - start["monotonic_s"]
        cpu_s = (end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6
        peak = end["memory.peak"]
    else:
        status = "timed_out" if state["Result"] == "timeout" else "failed"
        result = dict(
            status=status,
            reason=state["Result"],
            boundary=BOUNDARY,
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        )
        before, after = (
            counter(state, key, 1e6)
            for key in ("ActiveEnterTimestampMonotonic", "InactiveEnterTimestampMonotonic")
        )
        wall = after - before if before and after and after >= before else None
        cpu_s, peak = counter(state, "CPUUsageNSec", 1e9), counter(state, "MemoryPeak")
    validate_result(result)
    return result, dict(
        service=service, start=start, end=end, wall_s=wall, cpu_s=cpu_s, peak_bytes=peak
    )


def seal(work, report):
    source = prepared.source_lock(work, report)
    path = whole_iq.checked(
        report / "candidate-lock.json",
        whole_iq.read(work / "candidate-lock.json")["candidate_sha256"],
    )
    candidate_lock = whole_iq.read(path)
    whole_iq.checked(Path(prepared.__file__), candidate_lock["materializer_sha256"])
    whole_iq.checked(report / "selection.csv", candidate_lock["selector_files"]["selection.csv"])
    material = [
        "source-lock.json",
        "candidate-lock.json",
        "selection.csv",
        "PROTOCOL.md",
        "positions.jsonl.gz",
        "resources.json",
    ]
    rows, evidence = [], {}
    for ident, case in source["cases"].items():
        archived = case["archived"]
        choice = candidate_lock["cases"][ident]
        control, treatment = (work / ident / name for name in ("control", "candidate"))
        whole_iq.checked(control / "native.json", choice["stock_native_sha256"])
        whole_iq.checked(control / "request.json", case["control_request_sha256"])
        fresh, stock_resource = service_result(control, case["cpu"])
        equal = (
            scientific(fresh) == scientific(archived["result"]) if fresh["status"] == "ok" else None
        )
        if equal is False:
            raise ValueError(
                "fresh stock produced different non-timing science from the archived control"
            )
        candidate_resource = None
        if choice["exact_archive_reuse"]:
            if choice["derived_native_sha256"] != archived["native_sha256"] or choice["edits"]:
                raise ValueError("non-identical candidate cannot reuse a control position")
            fit = archived["result"]
            origin = "exact archived control · zero edits"
        else:
            whole_iq.checked(treatment / "native.json", choice["derived_native_sha256"])
            whole_iq.checked(treatment / "request.json", choice["candidate_request_sha256"])
            fit, candidate_resource = service_result(treatment, case["cpu"])
            origin = "fresh fitted candidate"
        evidence[ident] = dict(
            fresh_control=stock_resource,
            candidate=candidate_resource,
            archived_control_exact=fresh["status"] == "ok" and equal,
            fresh_control_status=fresh["status"],
            candidate_origin=origin,
        )
        shared = dict(
            archived,
            stock_native_sha256=archived["native_sha256"],
            capture_era_native_sha256=case["original_native_sha256"],
            cohort="held" if ident in ("DS26-0162", "DS29-0519") else "diagnostic",
        )
        shared.pop("paired_ordinary_sha256", None)
        rows.extend(
            (
                dict(shared, method=STOCK, origin="sealed full-stride control", promoted=0),
                dict(
                    shared,
                    method=CANDIDATE,
                    result=fit,
                    promoted=len(choice["edits"]),
                    origin=origin,
                    native_sha256=choice["derived_native_sha256"],
                    input_sha256=choice.get("candidate_request_sha256", archived["input_sha256"]),
                ),
            )
        )
        for attempt in (control, treatment):
            for name in ("service.log", "position.json"):
                path = attempt / name
                if path.exists():
                    filename = f"{ident}-{attempt.name}-{name}"
                    write(report / filename, path.read_bytes())
                    material.append(filename)
    pack(report / "positions.jsonl.gz", rows)
    save_json(report / "resources.json", evidence)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(source["cases"]),
            files={name: _sha(report / name) for name in material},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(rows, refs, resources):
    pairs = {(row["id"], row["method"]): row for row in rows}
    output = []
    for ident, reference in refs.items():
        for arm in ARMS:
            old = {name: reference["reference"][name][arm] for name in V5_OPTIONS}
            baseline = old["baseline"]["error_km"]
            fits = dict(old)
            for method in (STOCK, CANDIDATE):
                selected = pairs[ident, method]
                result = selected["result"]
                endpoint = result["arms"][arm]
                fits[method] = dict(
                    endpoint,
                    error_km=distance_km(endpoint["latlon"], reference["truth"]),
                    status=result["status"],
                    conditional_frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    origin=selected["origin"],
                    promoted=selected["promoted"],
                    observations=result["metrics"].get("observations"),
                    tracks=result["metrics"].get("tracks"),
                )
            displacement = distance_km(fits[STOCK]["latlon"], fits[CANDIDATE]["latlon"])
            for method, endpoint in fits.items():
                error, stock = endpoint["error_km"], fits[STOCK]["error_km"]
                measurement = (
                    (resources[ident]["candidate"] or {})
                    if method == CANDIDATE
                    else resources[ident]["fresh_control"]
                    if method == STOCK
                    else {}
                )
                output.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=method,
                        cohort=pairs[ident, STOCK]["cohort"],
                        status=endpoint["status"],
                        published=endpoint["latlon"] is not None,
                        promoted=endpoint.get("promoted"),
                        origin=endpoint.get("origin"),
                        error_km=error,
                        original_v5_km=baseline,
                        within_5pct=error is not None
                        and baseline is not None
                        and error <= 1.05 * baseline,
                        within_10pct=error is not None
                        and baseline is not None
                        and error <= 1.10 * baseline,
                        paired_error_delta_km=error - stock
                        if method == CANDIDATE and error is not None and stock is not None
                        else None,
                        paired_position_shift_km=displacement if method == CANDIDATE else None,
                        rms_hz=endpoint.get("rf_rms_hz"),
                        conditional_frequency_score=endpoint.get("conditional_frequency_score"),
                        observations=endpoint.get("observations"),
                        tracks=endpoint.get("tracks"),
                        instrumented_position_wall_s=measurement.get("wall_s"),
                        position_cpu_s=measurement.get("cpu_s"),
                        position_peak_bytes=measurement.get("peak_bytes"),
                    )
                )
    return output


def score(report):
    lock = whole_iq.read(report / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    _, references = held_references(None, lock["cases"])
    rows = rows_from(report / "positions.jsonl.gz")
    if {(r["id"], r["method"]) for r in rows} != {
        (case, method) for case in lock["cases"] for method in (CANDIDATE, STOCK)
    }:
        raise ValueError("paired bracketed predictions do not cover the whole roster")
    scores = score_rows(
        rows, {r["id"]: r for r in references}, whole_iq.read(report / "resources.json")
    )
    csv_file(report / "scores.csv", scores)
    descriptor = []
    provenance = [
        "source-lock.json",
        "candidate-lock.json",
        "prediction-lock.json",
        "resources.json",
        "scores.csv",
        "selection.csv",
    ]
    for name, cases in [
        ("bracketed-position-all", lock["cases"]),
        (
            "bracketed-position-held",
            [r["id"] for r in rows if r["method"] == STOCK and r["cohort"] == "held"],
        ),
    ]:
        predictions = "positions.jsonl.gz" if name.endswith("-all") else "held-positions.jsonl.gz"
        if predictions != "positions.jsonl.gz":
            pack(report / predictions, [r for r in rows if r["id"] in cases])
        seal = name + "-figure-lock.json"
        save_json(
            report / seal,
            dict(cases=cases, files={f: _sha(report / f) for f in [predictions, *provenance]}),
        )
        descriptor.append(
            dict(
                id=name,
                method=CANDIDATE,
                scope="roof",
                cases=cases,
                seal=seal,
                provenance=provenance,
                title="Bracketed weak peaks through the installed position receiver"
                if name.endswith("-all")
                else "Bracketed weak peaks on two held waveforms",
                caption=(
                    "Complete wide native factors drive the same compact phase-release. "
                    "The candidate promotes only selected existing rows. Original v5 uses "
                    "capture-era factors."
                ),
                series=[
                    dict(
                        key="one",
                        label="Bracketed weak peaks",
                        file=predictions,
                        value=CANDIDATE,
                        native_field="capture_era_native_sha256",
                    ),
                    dict(
                        key="stock",
                        label="Archived wide control",
                        file=predictions,
                        value=STOCK,
                        native_field="capture_era_native_sha256",
                        match=[
                            "stock_native_sha256",
                            "catalog_sha256",
                            "tile",
                            "original_request_sha256",
                        ],
                    ),
                ],
            )
        )
    save_json(report / "figures.json", dict(version=1, charts=descriptor))


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
