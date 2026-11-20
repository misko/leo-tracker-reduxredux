"""Seal the relocated waveform services and check antenna scheduling and resource outcomes."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import one_lane_schedule, partner_on_hit, second_on_miss
from ..variants.iq_stream import _read_prefix
from ..variants.selective_capture import visit_pairs
from . import on_hit_waveforms as direct
from . import one_lane_roster
from . import portable_stream_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .portable_receiver_results import equal_science, read_worker_file
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

MODE = "partner-on-strict-primary-hit/observed-packets-v1"
SOURCE_ID = {"analysis_manifest_sha256"}
PROVENANCE_ID = {"run_id", "scope", "detector_mode"}
CHECKED = (
    "request.json",
    "raw-0.json",
    "raw-resources.json",
    "position.json",
    "position-resources.json",
)
SEAL = "prediction-lock.json"
READOUT = "terminal.json"
PROTOCOL = "PROTOCOL.md"
REPORT = trial.REPORT


def factors(document):
    """Keep each detector value and all clocks; only replace declared identity fields."""
    return dict(
        document,
        source={k: v for k, v in document["source"].items() if k not in SOURCE_ID},
        provenance={k: v for k, v in document["provenance"].items() if k not in PROVENANCE_ID},
    )


def independent_identity(document):
    source = document["source"]
    provenance = document["provenance"]
    identity = [
        MODE,
        provenance["detector_sha256"],
        source["input_manifest_sha256"],
        source["probes"],
        provenance["excluded_windows"],
    ]
    digest = whole_iq.recording.digest(identity).removeprefix("sha256:")
    if (
        source["analysis_manifest_sha256"] != "sha256:" + digest
        or provenance["run_id"] != "replay-" + digest[:32]
        or provenance["scope"] != MODE
        or provenance["detector_mode"] != MODE
    ):
        raise ValueError("Factor identity does not derive solely from observed replay outputs")


def dispatch_projection(stock, centers):
    schedule = one_lane_schedule.dispatch(stock, centers)
    expected, counts = partner_on_hit.project(stock, schedule)
    calls = [
        dict(
            visit=entry["visit"],
            rf_center_hz=entry["rf_center_hz"],
            primary_receiver=rx,
            partner_required=not second_on_miss.needs_partner(lanes[rx]),
        )
        for entry, (_, lanes) in zip(schedule, visit_pairs(stock["source"]["probes"]), strict=True)
        for rx in (entry["selected_receiver"],)
    ]
    return expected, counts, calls


def verify_parity(native, expected, direct_factors, measured, calls):
    norm = encoded(factors(native))
    if norm != encoded(factors(expected)) or norm != encoded(factors(direct_factors)):
        raise ValueError("Ordered probes, delivery, exclusions or scientific metadata differ")
    independent_identity(native)
    observed = [
        {k: row[k] for k in ("visit", "rf_center_hz", "primary_receiver", "partner_required")}
        for row in measured
    ]
    if encoded(observed) != encoded(calls):
        raise ValueError("Recorded partner dispatch differs from the independent strict gate")


def capture_records(folder):
    records = []
    for lane in range(2):
        file = folder / f"lane-{lane}.jsonl"
        if not file.is_file():
            continue
        for line in read_worker_file(file).splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A terminated service can leave a final incomplete line. Its source log stays.
                continue
            if record["kind"] == "visit":
                records.append(
                    {
                        key: record[key]
                        for key in (
                            "segment",
                            "sequence",
                            "visit",
                            "status",
                            "iq_sha256",
                            "delivery_clock",
                            "sample_start",
                            "sample_end",
                            "reason",
                        )
                    }
                )
    return sorted(records, key=lambda r: r["visit"])


def seal(work, out):
    """Write the terminal lock using only portable outputs and explicit input receipts."""
    if (out / SEAL).exists():
        raise FileExistsError("The four complete service attempts already have a frozen lock")
    sources = whole_iq.read(out / "source-lock.json")
    plan = whole_iq.read(whole_iq.checked(out / "input-lock.json", sources["input_lock_sha256"]))
    files = {"source-lock.json", "input-lock.json", *plan["files"]}
    handoff = {}
    for ident, case in plan["cases"].items():
        whole_iq.checked(out / f"{ident}-input.json", case["manifest_sha256"])
        handoff[ident] = {}
        for workers in case["order"]:
            run = work / ident / f"workers-{workers}"
            service = whole_iq.read(run / "service.json")
            whole_iq.checked(run / "service.log", service["log_sha256"])
            prefix = Path("receipts") / ident / f"workers-{workers}"
            target = out / prefix
            folder = run / "actual"
            assets = []
            for name in ("launch.json", "service.json", "service.log"):
                write(target / name, (run / name).read_bytes())
                assets.append(name)
            for name in CHECKED:
                if (folder / name).is_file():
                    write(target / name, read_worker_file(folder / name))
                    assets.append(name)
            for name in ("native.json", "conditional-visits.jsonl"):
                if (folder / name).is_file():
                    write(
                        target / f"{name}.gz",
                        gzip.compress(read_worker_file(folder / name), mtime=0),
                    )
                    assets.append(f"{name}.gz")
            visits = b"".join(encoded(p) + b"\n" for p in capture_records(folder))
            if visits:
                write(target / "physical-visits.jsonl.gz", gzip.compress(visits, mtime=0))
                assets.append("physical-visits.jsonl.gz")
            handoff[ident][str(workers)] = dict(
                returncode=service["exit_code"], prefix=str(prefix), assets=assets
            )
            files.update(str(prefix / n) for n in assets)
    save_json(out / READOUT, handoff)
    save_json(
        out / SEAL,
        dict(
            cases=list(trial.SCHEDULE), files={n: _sha(out / n) for n in sorted(files | {READOUT})}
        ),
    )


def stock_context(ident, case):
    base = direct.REPORT
    seal_path = base / SEAL
    lock = whole_iq.read(seal_path)
    parent = whole_iq.read(
        whole_iq.checked(base / "source-lock.json", lock["files"]["source-lock.json"])
    )["cases"][ident]
    for key in (
        "recording",
        "orbit_snapshots",
        "capture_native_sha256",
        "request_sha256",
        "catalog_sha256",
        "tile",
    ):
        if case[key] != parent[key]:
            raise ValueError(f"Direct whole-IQ position reference uses a different {key}")
    stock = one_lane_roster.stock_document(parent["stock"])
    path = f"native/{ident}.json.gz"
    payload = gzip.decompress(whole_iq.checked(base / path, lock["files"][path]).read_bytes())
    positions = rows_from(
        whole_iq.checked(base / "positions.jsonl.gz", lock["files"]["positions.jsonl.gz"])
    )
    (reference,) = [p for p in positions if p["id"] == ident and p["method"] == direct.METHOD]
    if sha256(payload).hexdigest() != reference["native_sha256"]:
        raise ValueError("Direct whole-IQ position reference used a different factor input")
    direct_factors = json.loads(payload)
    return (
        stock,
        direct_factors,
        reference,
        dict(
            direct_lock_sha256=_sha(seal_path),
            stock_native_sha256=parent["stock"]["native_sha256"],
            direct_native_sha256=reference["native_sha256"],
        ),
    )


def rf_centers(manifest):
    centers = None
    for item in manifest["segments"]:
        body = _read_prefix(Path(item["path"]), 65_537)
        if len(body) > 65_536 or sha256(body).hexdigest() != item["sha256"]:
            raise ValueError("A raw tuning segment failed input digest verification")
        targets = json.loads(body)["configuration"]["targets"]
        current = {(x["channel"], x["edge"]): x["rf_center_hz"] for x in targets}
        if centers is not None and current != centers:
            raise ValueError("Tuning schedule changed its physical per-channel frequency")
        centers = current
    if not centers:
        raise ValueError("No authenticated RF tuning keys")
    return centers


def check_recording(physical, native, counts, window_sizes):
    excluded = {r["visit"]: r for r in native["provenance"]["excluded_windows"]}
    schedule = [(segment, seq) for segment, n in enumerate(window_sizes) for seq in range(n)]
    for visit, ((segment, seq), row, clock) in enumerate(
        zip(schedule, physical, native["delivery_clocks"], strict=True)
    ):
        if (
            (row["visit"], row["segment"], row["sequence"]) != (visit, segment, seq)
            or row["status"] != ("invalid_capture" if visit in excluded else "processed")
            or not row["iq_sha256"]
        ):
            raise ValueError("Raw chronology omitted an acquisition or shifted an exclusion")
        if visit in excluded and any(row[key] != value for key, value in excluded[visit].items()):
            raise ValueError("Raw exclusion fields differ from the assembled native exclusion")
        for key, value in row["delivery_clock"].items():
            if clock[key] != value:
                raise ValueError("Raw delivery differs from the assembled native clock")
    source = native["source"]
    digest = whole_iq.recording.digest(
        [source["input_manifest_sha256"], [r["iq_sha256"] for r in physical]]
    )
    if (
        len(excluded) != counts["invalid_visits"]
        or digest != source["raw_recording_authority_digest"]
    ):
        raise ValueError("Complete input excluded-window count does not match independent stock")


def memory_marks(raw, position):
    start, raw_end, handoff, before, end = (
        raw["start"],
        raw["raw_end"],
        raw["handoff"],
        position["start"],
        position["end"],
    )
    for mark in (start, raw_end, handoff, before, end):
        if (
            mark["cgroup"] != start["cgroup"]
            or mark["memory.max"] != whole_iq.MEMORY
            or mark["memory.swap.max"] != 0
            or mark["memory.swap.current"] != 0
            or mark["memory.events"]["oom_kill"] != 0
        ):
            raise ValueError("A stage escaped the actual 512 MiB isolated service")
    return start, raw_end, handoff, before, end


def resource_row(measured, service, raw, worker, fit, fact, case, workers, ident):
    start, raw_end, handoff, before, end = memory_marks(raw, fit)
    if worker["cpus"] != case["cpus"][:workers] or worker["authenticated_chunks"] < 1:
        raise ValueError("Qualified raw worker affinity or authenticated chunk receipt changed")
    elapsed = [m["detector_wall_ns"] / 1e6 for m in measured]
    cpu = [m["detector_cpu_ns"] / 1e6 for m in measured]
    valid, calls = len(measured), sum(m["partner_required"] for m in measured)
    return dict(
        id=ident,
        variant=workers,
        scheduled_order=case["order"].index(workers) + 1,
        edge=case["edge"],
        cpu_pair="/".join(map(str, case["cpus"])),
        service_status="completed",
        raw_windows=case["recording"]["window_count"],
        raw_clock_span_s=raw["counts"]["window_delivery_span_s"],
        nominal_stored_iq_s=case["recording"]["window_count"] * 0.020,
        raw_valid=valid,
        raw_invalid=fact["invalid_visits"],
        native_probes=valid * 2,
        primary_calls=valid,
        partner_calls=calls,
        physical_receiver_calls=valid + calls,
        authenticated_chunks=worker["authenticated_chunks"],
        compressed_bytes=worker["compressed_bytes"],
        raw_child_wall_s=worker["wall_s"],
        raw_child_cpu_s=worker["cpu_s"],
        raw_through_factor_wall_s=handoff["monotonic_s"] - start["monotonic_s"],
        raw_through_factor_cpu_s=(
            handoff["cpu.stat"]["usage_usec"] - start["cpu.stat"]["usage_usec"]
        )
        / 1e6,
        visits_p50_ms=distribution(elapsed)["p50"],
        visits_p95_ms=distribution(elapsed)["p95"],
        visits_20ms_count=sum(t <= 20 for t in elapsed),
        visits_thread_cpu_s=sum(cpu) / 1e3,
        visits_thread_cpu_p50_ms=distribution(cpu)["p50"],
        position_wall_s=end["monotonic_s"] - before["monotonic_s"],
        position_cpu_s=(end["cpu.stat"]["usage_usec"] - before["cpu.stat"]["usage_usec"]) / 1e6,
        raw_cgroup_peak_bytes=raw_end["memory.peak"],
        raw_memory_cap_events=raw_end["memory.events"]["max"] - start["memory.events"]["max"],
        factor_handoff_peak_bytes=handoff["memory.peak"],
        full_cgroup_peak_bytes=end["memory.peak"],
        full_memory_cap_events=end["memory.events"]["max"] - start["memory.events"]["max"],
        position_rss_peak_kib=end["rss_peak_kib"],
        full_service_wall_s=service["wall_s"],
        cpu_through_fit_s=(end["cpu.stat"]["usage_usec"] - start["cpu.stat"]["usage_usec"]) / 1e6,
        cpu_throttled_through_fit_s=(
            end["cpu.stat"].get("throttled_usec", 0) - start["cpu.stat"].get("throttled_usec", 0)
        )
        / 1e6,
    )


def endpoint_rows(result, ident, workers, reference, native_sha):
    truth = reference["truth"]
    out = []
    for arm in ARMS:
        value = result.get("arms", {}).get(arm, {})
        point = value.get("latlon")
        out.append(
            dict(
                id=ident,
                variant=workers,
                arm=arm,
                status=value.get("status", result["status"]),
                native_sha256=native_sha,
                latitude=point[0] if point else None,
                longitude=point[1] if point else None,
                error_km=distance_km(point, truth),
                rf_rms_hz=value.get("rf_rms_hz"),
                frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
            )
        )
    return out


def verify_run(path, service, release, case, workers, ident, control, reference):
    expected, direct_native, counts, calls, direct_position = control
    request = whole_iq.read(path / "request.json")
    body = gzip.decompress((path / "native.json.gz").read_bytes())
    digest = sha256(body).hexdigest()
    if (
        request["request_sha256"] != case["manifest_sha256"]
        or request["package_files_sha256"] != release["package"]["manifest_sha256"]
        or request["detector_sha256"] != release["stock_wide_sha256"]
        or request["native_sha256"] != digest
        or request["detector"] != "partner-on-hit"
        or request["visit_workers"] != workers
        or request["cpus"] != case["cpus"]
        or request["count"] != case["recording"]["window_count"]
        or request["edge"] != case["edge"]
    ):
        raise ValueError("Relocated portable invocation or its freshly assembled factors differ")
    native = json.loads(body)
    measured = rows_from(path / "conditional-visits.jsonl.gz")
    verify_parity(native, expected, direct_native, measured, calls)
    physical = rows_from(path / "physical-visits.jsonl.gz")
    check_recording(physical, native, counts, case["windows"])
    result = whole_iq.read(path / "position.json")
    validate_result(result)
    if set(result["arms"]) != set(ARMS) or not equal_science(result, direct_position["result"]):
        raise ValueError("A compact geographic or frequency result differs on the matched input")
    raw, worker, fit = (
        whole_iq.read(path / name)
        for name in ("raw-resources.json", "raw-0.json", "position-resources.json")
    )
    row = resource_row(measured, service, raw, worker, fit, counts, case, workers, ident)
    checks = dict(
        variant=workers,
        exact_complete_observations=True,
        exact_direct_fit=True,
        native_sha256=digest,
        physical_clock_exclusion_match=True,
    )
    return row, checks, endpoint_rows(result, ident, workers, reference, digest)


def paired_deltas(rows):
    by_key = {(r["id"], r["variant"]): r for r in rows}
    metrics = (
        "raw_through_factor_wall_s",
        "raw_through_factor_cpu_s",
        "full_service_wall_s",
        "cpu_through_fit_s",
        "position_wall_s",
        "position_rss_peak_kib",
    )
    result = []
    for ident in trial.SCHEDULE:
        serial, parallel = (by_key[ident, workers] for workers in (1, 2))
        completed = serial["service_status"] == parallel["service_status"] == "completed"
        result.append(
            dict(
                id=ident,
                both_completed=completed,
                **{
                    f"two_minus_one_{key}": parallel[key] - serial[key] if completed else None
                    for key in metrics
                },
            )
        )
    return result


def stage_figure(out, rows):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(11, 5.5), layout="constrained")
    FigureCanvasAgg(figure)
    wall, memory = figure.subplots(1, 2)
    labels = [
        f"{r['id']} · {r['variant']} {'worker' if r['variant'] == 1 else 'workers'}" for r in rows
    ]
    raw = [r.get("raw_through_factor_wall_s") or 0 for r in rows]
    fit = [r.get("position_wall_s") or 0 for r in rows]
    other = [
        max(r["full_service_wall_s"] - x - y, 0) for r, x, y in zip(rows, raw, fit, strict=True)
    ]
    wall.barh(labels, raw, label="Saved IQ through factors", color="#2b6a9a")
    wall.barh(labels, fit, left=raw, label="Compact fit", color="#247a59")
    wall.barh(
        labels,
        other,
        left=[x + y for x, y in zip(raw, fit, strict=True)],
        label="Other recorded service wall",
        color="#bac5cf",
    )
    memory.barh(
        labels,
        [(r.get("full_cgroup_peak_bytes") or 0) / 2**20 for r in rows],
        label="Full service cgroup",
        color="#9eb9d1",
    )
    memory.barh(
        labels,
        [(r.get("position_rss_peak_kib") or 0) / 1024 for r in rows],
        label="Position process RSS",
        color="#2b6a9a",
        height=0.42,
    )
    memory.axvline(512, color="#a44b43", label="512 MiB cap", ls="--", lw=1)
    wall.set(xlabel="Elapsed seconds", title="Relocated raw I/Q through both calibration arms")
    memory.set(xlabel="Charged peak MiB", title="Host memory with zero swap", xlim=(0, 555))
    for ax in (wall, memory):
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.24)
        ax.set_axisbelow(True)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), frameon=False, fontsize=8)
    for index, row in enumerate(rows):
        if row["service_status"] != "completed":
            memory.text(0, index, row["service_status"], va="center")
    for suffix in ("png", "pdf"):
        figure.savefig(out / f"resources.{suffix}", dpi=150)


def publish(out):
    terminal = out / SEAL
    lock = whole_iq.read(terminal)
    if lock["cases"] != list(trial.SCHEDULE):
        raise ValueError("Terminal replay roster differs from the frozen input")
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    source = whole_iq.read(out / "source-lock.json")
    cases = whole_iq.read(out / "input-lock.json")["cases"]
    handoff = whole_iq.read(out / READOUT)
    _, geographic = held_references(None, trial.SCHEDULE)
    references = {row["id"]: row for row in geographic}
    timing, parity, endpoints = [], {}, []
    for ident, case in cases.items():
        stock, direct_native, prior_fit, bound = stock_context(ident, case)
        manifest = whole_iq.read(out / f"{ident}-input.json")
        expected, counts, calls = dispatch_projection(stock, rf_centers(manifest))
        parent = (expected, direct_native, counts, calls, prior_fit)
        parity[ident] = dict(bound, workers=[])
        for count in sorted(case["order"]):
            receipt = handoff[ident][str(count)]
            path = out / receipt["prefix"]
            service = whole_iq.read(path / "service.json")
            if service["exit_code"] != receipt["returncode"]:
                raise ValueError("Terminal receipt has an inconsistent return code")
            if service["exit_code"]:
                log = (path / "service.log").read_text(errors="replace")
                status = "timed_out" if "timeout" in log.lower() else "failed"
                timing.append(
                    dict(
                        id=ident,
                        variant=count,
                        edge=case["edge"],
                        scheduled_order=case["order"].index(count) + 1,
                        cpu_pair="/".join(map(str, case["cpus"])),
                        service_status=status,
                        full_service_wall_s=service["wall_s"],
                    )
                )
                missing = dict(status=status, metrics={})
                endpoints.extend(endpoint_rows(missing, ident, count, references[ident], None))
                parity[ident]["workers"].append(dict(variant=count, status=status))
                continue
            row, check, positions = verify_run(
                path, service, source, case, count, ident, parent, references[ident]
            )
            timing.append(row)
            parity[ident]["workers"].append(check)
            endpoints.extend(positions)
        pair = parity[ident]["workers"]
        native = [row.get("native_sha256") for row in pair]
        parity[ident]["worker_count_byte_equivalent"] = all(native) and len(set(native)) == 1
        if all(native) and len(set(native)) != 1:
            raise ValueError("Worker scheduling changed complete acquired factor bytes")
    # Keep missing numeric measurements explicitly blank even if a service failed before dispatch.
    columns = dict.fromkeys(key for row in timing for key in row)
    csv_file(out / "resources.csv", [dict(columns, **row) for row in timing])
    csv_file(out / "paired-resource-deltas.csv", paired_deltas(timing))
    csv_file(out / "positions.csv", endpoints)
    save_json(out / "parity.json", parity)
    stage_figure(out, timing)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="portable-stream-on-hit",
            title="Relocated partner-on-hit visit parallelism",
            sample="Two complete recordings, one and two visit workers on matched per-case CPUs",
            boundary="Authenticated saved IQ, portable GLRT, native factors and both compact arms",
            note="Fixed four-center kernel; measured 512 MiB host cgroups with zero swap.",
            image="resources.png",
            pdf="resources.pdf",
            csv="resources.csv",
            seal="stage-lock.json",
        ),
    )
    files = (
        SEAL,
        "resources.csv",
        "paired-resource-deltas.csv",
        "positions.csv",
        "parity.json",
        "resources.png",
        "resources.pdf",
        "stage-figure.json",
    )
    save_json(
        out / "stage-lock.json",
        dict(
            cases=list(trial.SCHEDULE),
            files={name: _sha(out / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
            component_test_sha256=_sha(trial.ROOT / "tests/pipeline_eval/test_portable_stream.py"),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=REPORT)
    opts = parser.parse_args()
    if opts.action == "seal":
        seal(opts.work, opts.out)
    else:
        publish(opts.out)
