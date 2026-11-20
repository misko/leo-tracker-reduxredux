"""Verify both concurrent branches against complete independent waveform archives."""

import argparse
import gzip
import json
import subprocess
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import arrival_queue as pace
from . import (
    capture_whole,
    capture_whole_results,
    one_lane_roster,
    paced_original,
    prepared_capture_waveform,
)
from . import parallel_acquisition as trial
from . import parallel_acquisition_source as staging
from .exact_wide_iq_results import detector_rows
from .full_v5_check import _sha

STOCK_LOCK = "355665d05245ff43d2a33cfb3af2ee7a294715312c97a6709755f7cb60fb328b"
STRIDE = staging.SCREEN / "receiver-core/full-stride"
IDENTS = tuple(staging.CPUS)


def sealed_member(folder, seal, name):
    lock = whole_iq.read(whole_iq.checked(folder / "prediction-lock.json", seal))
    return whole_iq.checked(folder / name, lock["files"][name])


def references(case):
    roster = one_lane_roster.REPORT
    stock_plan = whole_iq.read(sealed_member(roster, STOCK_LOCK, "plan.json"))
    audit = whole_iq.read(sealed_member(roster, STOCK_LOCK, "packet-audit.json"))
    if len(stock_plan["groups"]["all"]) != 22 or set(audit) != set(stock_plan["groups"]["all"]):
        raise ValueError("wide reference needs the independently authenticated 22-case roster")
    wide_archive = audit[case]["native_archive"]
    wide_doc = one_lane_roster.stock_document(wide_archive)
    stride_pin = paced_original.WIDE_PIN
    resources = whole_iq.read(sealed_member(STRIDE, stride_pin, "resources.json"))
    control = resources[case]["control"]
    service = control["service"]
    attempt = Path(service["binding"]["attempt"])
    plan = whole_iq.read(whole_iq.checked(attempt / "plan.json", service["binding"]["plan_sha256"]))
    whole_iq.checked(attempt / "service.log", service["log_sha256"])
    full_path = sealed_member(STRIDE, stride_pin, f"native/control/{case}.json.gz")
    if (
        pace.readgz(full_path) != wide_doc
        or service["exit_code"] != 0
        or plan["detector_sha256"] != trial.WIDE["sha256"]
        or wide_doc["provenance"]["detector_sha256"] != "sha256:" + trial.WIDE["sha256"]
    ):
        raise ValueError("independent complete wide waveform and 22-case roster differ")
    wide_frames, _, _ = detector_rows(attempt)
    origin_folder, original_pin = staging.ORIGINAL[case]
    origin_lock = sealed_member(origin_folder, original_pin, "source-lock.json")
    original_doc, binding = staging.original_reference(case)
    original_work = capture_whole.WORK if case == "DS29-0082" else prepared_capture_waveform.WORK
    whole_iq.checked(original_work / origin_lock.name, _sha(origin_lock))
    shards, completed, _ = capture_whole_results.collect(original_work, binding)
    if len(completed) != len(binding["workers"]) or any(r["exit_code"] for r in completed.values()):
        raise ValueError("original independent complete acquisition is missing a terminal shard")
    original_frames = sorted(
        (paced_original.packet(row) for _, rows in shards.values() for row in rows),
        key=lambda row: row["visit"],
    )
    data = {"wide": (wide_doc, wide_frames), "original": (original_doc, original_frames)}
    provenance = dict(
        wide=dict(
            roster_seal=STOCK_LOCK,
            whole_waveform_seal=stride_pin,
            full_waveform_native=wide_archive,
            raw_attempt=str(attempt),
        ),
        original=dict(
            seal=original_pin,
            full_waveform_native=str(origin_folder / "native.json.gz"),
            native_sha256=_sha(origin_folder / "native.json.gz"),
            raw_attempt=str(original_work),
        ),
    )
    return data, provenance


def audit_archive(doc, frames, events, members, spec):
    if (
        doc["source"]["raw_recording_authority_digest"] != spec["raw_recording_sha256"]
        or doc["source"]["input_manifest_sha256"] != spec["capture"]["input_manifest_sha256"]
        or staging.clock_events(doc) != events
        or [p for row in frames for p in row["probes"]] != doc["source"]["probes"]
    ):
        raise ValueError("independent dual waveform differs from original physical ingress")
    invalid = {item["visit"]: item for item in doc["provenance"]["excluded_windows"]}
    for due, member, packet in zip(events, members, frames, strict=True):
        if (
            any(
                packet[k] != due[k]
                for k in ("visit", "delivery_clock", "status", "sample_start", "sample_end")
            )
            or any(packet[k] != member[k] for k in ("iq_sha256", "segment", "sequence"))
            or packet["clock_anchor"] != member["bracket"]
            or packet["input_bytes"] != staging.spool.WINDOW_BYTES
            or packet["generation"] != member["acquisition"]["generation"]
        ):
            raise ValueError(f"staged physical packet differs at visit {due['visit']}")
        if due["status"] == "processed":
            if [p["receiver_id"] for p in packet["probes"]] != [0, 1] or any(
                p["actual_rf_hz"] != due["center_hz"] for p in packet["probes"]
            ):
                raise ValueError("complete reference packet lost one physical antenna")
        elif packet["probes"] or any(packet[k] != v for k, v in invalid[due["visit"]].items()):
            raise ValueError("hardware exclusion contradicts its reference packet")


def assemble_trace(events, arrivals, output, archival_packets, role, *, selected_rf_hz=None):
    observed = {row["visit"]: row for row in output}
    if list(observed) != sorted(observed) or len(observed) != len(output):
        raise ValueError("detector FIFO produced duplicate or out-of-order work")
    trace = []
    cutoff = events[-1]["arrival_ns"]
    previous = -1
    for due, release, exact in zip(events, arrivals, archival_packets, strict=True):
        visit = due["visit"]
        released = release["released_ns"]
        detail = release["outcomes"][role]
        admission = detail["admission"]
        if due["status"] == "invalid_capture":
            allowed = ("invalid_capture",)
        elif selected_rf_hz is not None and role not in trial.assigned_roles(due, selected_rf_hz):
            allowed = ("unassigned",)
        else:
            allowed = ("queued", "dropped_busy")
        if (
            visit != release["visit"]
            or not due["arrival_ns"] <= released <= detail["offered_ns"]
            or admission not in allowed
        ):
            raise ValueError("source did not replay its full bound physical visit")
        measured = observed.pop(visit, None)
        if (admission == "queued") != (measured is not None):
            raise ValueError("a branch packet appeared without the corresponding admission")
        row = dict(
            due,
            **detail,
            released_ns=released,
            start_ns=None,
            finish_ns=None,
            native_wall_ns=None,
            native_cpu_ns=None,
            packet=None,
            observed_by_cutoff=False,
            start_minus_last_arrival_ns=None,
            finish_minus_last_arrival_ns=None,
            reference_packet_sha256=pace.fingerprint(exact),
        )
        if measured is not None:
            begin, finish = measured["start_ns"], measured["finish_ns"]
            if (
                measured["packet"] != exact
                or not max(previous, released) <= begin <= finish
                or not 0 < measured["native_wall_ns"] <= finish - begin
                or measured["native_cpu_ns"] <= 0
            ):
                raise ValueError(f"{role} complete measured packet or timing differs at {visit}")
            previous = finish
            row.update(
                measured,
                observed_by_cutoff=finish <= cutoff,
                start_minus_last_arrival_ns=begin - cutoff,
                finish_minus_last_arrival_ns=finish - cutoff,
            )
        trace.append(row)
    if observed:
        raise ValueError("worker emitted a packet outside the full recording clock")
    return trace


def native_document(reference, trace, lineage, detector_sha, *, cutoff_only, scope=None):
    packets = [
        r["packet"]
        for r in trace
        if r["packet"] is not None and (not cutoff_only or r["observed_by_cutoff"])
    ]
    digest = pace.fingerprint([lineage, cutoff_only, [p["visit"] for p in packets]])
    return dict(
        reference,
        source=dict(
            reference["source"],
            probes=[p for item in packets for p in item["probes"]],
            analysis_manifest_sha256=f"sha256:{digest}",
        ),
        provenance=dict(
            reference["provenance"],
            run_id=f"replay-{digest[:32]}",
            processed_windows=len(packets),
            detector_sha256=detector_sha,
            scope=scope or "actual concurrent recorded-clock dual detector emissions",
        ),
    )


def lines(path):
    with path.open("rb") as stream:
        return [json.loads(line) for line in stream]


def observed_stats(trace, resources, origin, cutoff):
    selected = [row for row in trace if row["observed_by_cutoff"]]
    drain = [row for row in trace if row["packet"] is not None and not row["observed_by_cutoff"]]

    def positive(row):
        return any(
            c["passed_fractional_margin_gate"]
            for p in row["packet"]["probes"]
            for c in p["candidates"]
        )

    before, end = resources["start"], resources["end"]
    return dict(
        counts=dict(Counter(row["admission"] for row in trace)),
        observed_by_cutoff=len(selected),
        late_drain_packets=len(drain),
        late_drain_visits=[row["visit"] for row in drain],
        late_drain_complete_ns=max((row["finish_ns"] - cutoff for row in drain), default=0),
        positive_by_cutoff=sum(positive(row) for row in selected),
        positive_within_20ms=sum(
            positive(row) and row["finish_ns"] - row["arrival_ns"] <= 20_000_000 for row in selected
        ),
        detector_cpu_ns=sum(row["native_cpu_ns"] or 0 for row in trace),
        worker_cpu_ns=end["process_cpu_ns"] - before["process_cpu_ns"],
        startup_cpu_ns=before["process_cpu_ns"],
        worker_ready_before_origin_ns=origin - before["monotonic_ns"],
        worker_terminal_after_cutoff_ns=end["monotonic_ns"] - origin - cutoff,
        peak_cgroup_memory_bytes=end["memory.peak"],
        peak_worker_rss_kib=end["rss_peak_kib"],
        swap_charge_bytes=end["memory.swap.current"],
    )


def replay_overlap(left, right):
    active = [
        [(row["start_ns"], row["finish_ns"]) for row in rows if row["packet"] is not None]
        for rows in (left, right)
    ]
    result, i, j = 0, 0, 0
    while i < len(active[0]) and j < len(active[1]):
        a, b = active[0][i], active[1][j]
        result += max(0, min(a[1], b[1]) - max(a[0], b[0]))
        if a[1] < b[1]:
            i += 1
        else:
            j += 1
    return result


def audit_case(work, stage, report, case, *, routing=None):
    out = report / case
    raw, folder = work / case, stage / case
    spec, ready, events, members = trial.source_input(folder)
    arrivals = lines(raw / "source.jsonl")
    plan = whole_iq.read(raw / "plan.json")
    source = whole_iq.read(raw / "source-resources.json")
    origin = whole_iq.read(raw / "clock-start.json")["origin_ns"]
    cutoff = spec["last_arrival_ns"]
    routing = {} if routing is None else routing
    selected_rf_hz = routing.get("selected_rf_hz")
    ref, binding = references(case)
    if (
        source["origin_ns"] != origin
        or source["last_release_ns"] != arrivals[-1]["released_ns"]
        or len(arrivals) != len(events)
        or source["stage_charge"]["start"]["cgroup"] != ready["end"]["cgroup"]
        or source["stage_charge"]["end"]["cgroup"] != ready["end"]["cgroup"]
        or source["end"]["cgroup"] == ready["end"]["cgroup"]
        or plan.get("routing", {}) != routing
    ):
        raise ValueError("shared replay clock or stage charge changed before terminal")
    out.mkdir(parents=True, exist_ok=True)
    files = []

    def emit(name, value=None, *, copy=None, gz=False):
        path = out / name
        if copy is not None:
            write(path, copy.read_bytes())
        elif gz:
            pace.writegz(path, value)
        else:
            save_json(path, value)
        rel = str(path.relative_to(report))
        files.append(rel)
        return rel

    clock = emit("clock.json.gz", copy=folder / "events.json.gz")
    member_file = emit("members.json.gz", copy=folder / "members.json.gz")
    source_ledger = emit("source-arrivals.json.gz", arrivals, gz=True)
    emit("launch.json", plan)
    emit("clock-start.json", copy=raw / "clock-start.json")
    emit("reference-bindings.json", binding)
    detector_groups = {source["end"]["cgroup"], ready["end"]["cgroup"]}
    traces, branches = {}, {}
    for role in trial.ROLES:
        doc, packets = ref[role]
        audit_archive(doc, packets, events, members, spec)
        resources = whole_iq.read(raw / f"{role}-resources.json")
        group = resources["end"]["cgroup"]
        if (
            resources["origin_ns"] != origin
            or group in detector_groups
            or resources["start"]["cgroup"] != group
            or resources["start"]["cpus"] != [plan["cpus"][role]]
            or resources["end"]["cpus"] != [plan["cpus"][role]]
            or resources["start"]["monotonic_ns"] >= origin
            or resources["end"]["monotonic_ns"] < origin + cutoff
            or trial.WORD.unpack((raw / f"{role}.count").read_bytes())[0] != 0
        ):
            raise ValueError("worker did not start at the shared barrier or complete its own FIFO")
        detector_groups.add(group)
        trace = assemble_trace(
            events,
            arrivals,
            lines(raw / f"{role}.jsonl"),
            packets,
            role,
            selected_rf_hz=selected_rf_hz,
        )
        traces[role] = trace
        timing = observed_stats(trace, resources, origin, cutoff)
        trace_name = emit(f"{role}-trace.json.gz", trace, gz=True)
        lineage = _sha(report / trace_name)
        detector = trial.WIDE["sha256"]
        if role == "original":
            kernel = plan["original_libraries"]
            if selected_rf_hz is not None:
                kernel = dict(libraries=kernel, peak_selector=plan["peak_selector"])
            detector = pace.fingerprint(kernel)
        scope = "actual exclusive-RF recorded-clock detector emissions" if routing else None
        native, cutoff_native = (
            emit(
                name,
                native_document(
                    doc, trace, lineage, f"sha256:{detector}", cutoff_only=cutoff_only, scope=scope
                ),
                gz=True,
            )
            for cutoff_only, name in (
                (False, f"{role}-native.json.gz"),
                (True, f"{role}-cutoff-native.json.gz"),
            )
        )
        retained = [row for row in trace if row["packet"] is not None]
        branches[role] = dict(
            trace=trace_name,
            native=native,
            cutoff_native=cutoff_native,
            resources=emit(f"{role}-resources.json", dict(resources, summary=timing)),
            parity=dict(
                archived_physical_rows=len(packets),
                archived_valid_dual_packets=doc["provenance"]["processed_windows"],
                emitted_dual_packets_compared=len(retained),
                archived_full_packet_ledger_sha256=pace.fingerprint(
                    [r["reference_packet_sha256"] for r in trace]
                ),
                mismatches=0,
            ),
            summary=timing,
        )
    overlap = replay_overlap(traces["wide"], traces["original"])
    if selected_rf_hz is None and overlap <= 0:
        raise ValueError("detector timing intervals did not actually overlap")
    extra = dict(
        source=spec,
        stage=ready,
        pacing=source,
        physical_members=member_file,
        source_clock=clock,
        source_ledger=source_ledger,
        source_buffer_ownership="separate zero-swap tmpfs stage service",
        stage_start_to_ready_ns=ready["end"]["monotonic_ns"] - ready["start"]["monotonic_ns"],
        stage_ready_to_replay_ns=origin - ready["end"]["monotonic_ns"],
        stage_decode_and_readback_cpu_us=ready["end"]["cpu.stat.usage_usec"]
        - ready["start"]["cpu.stat.usage_usec"],
        stage_cpu_during_replay_us=source["stage_charge"]["end"]["cpu.stat.usage_usec"]
        - source["stage_charge"]["start"]["cpu.stat.usage_usec"],
        publisher_startup_cpu_ns=source["start"]["process_cpu_ns"],
        publisher_replay_cpu_ns=source["end"]["process_cpu_ns"] - source["start"]["process_cpu_ns"],
    )
    stage_name = emit("stage.json", extra)
    units = [spec["stage_unit"], *plan["units"].values()]
    logs = subprocess.run(
        [
            "journalctl",
            "--user",
            "--no-pager",
            "-o",
            "short-monotonic",
            *(arg for unit in units for arg in ("-u", unit)),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    journal = out / "services.log.gz"
    write(journal, gzip.compress(logs.stdout, mtime=0))
    files.append(str(journal.relative_to(report)))
    return dict(
        clock=clock,
        stage=stage_name,
        branches=branches,
        clock_origin_monotonic_ns=origin,
        last_arrival_ns=cutoff,
        last_arrival_visit=events[-1]["visit"],
        last_actual_release_ns=source["last_release_ns"],
        edge=spec["capture"]["edge"],
        valid_visits=sum(row["status"] == "processed" for row in events),
        invalid_visits=sum(row["status"] == "invalid_capture" for row in events),
        concurrent_detector_service_overlap_ns=overlap,
    ), files


def publish(work, stage, report):
    if (report / "manifest.json").exists():
        raise FileExistsError("this parallel acquisition report is already sealed")
    cases, files = {}, ["PROTOCOL.md"]
    for case in IDENTS:
        cases[case], names = audit_case(work, stage, report, case)
        files.extend(names)
    stage = dict(
        cases={case: row["stage"] for case, row in cases.items()},
        scope="authenticated on-disk captures predecoded into separately charged host tmpfs",
        measurement="recorded monotonic arrivals and actual parallel worker service",
        worker_budget_s=trial.BUDGET_S,
        staging_budget_s=staging.STAGE_LIMIT_S,
        waiting_slots=trial.CAPACITY - 1,
    )
    save_json(report / "stage.json", stage)
    files.append("stage.json")
    save_json(
        report / "manifest.json",
        dict(
            schema_version=1,
            cutoff="last original valid or invalid delivery on the recorded arrival clock",
            cases=cases,
            stage="stage.json",
            measured_sources={
                str(Path(module.__file__).name): _sha(Path(module.__file__))
                for module in (staging, trial)
            },
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--stage", type=Path, default=staging.STAGE)
    parser.add_argument("--report", type=local_output, default=staging.REPORT)
    args = parser.parse_args()
    publish(args.work, args.stage, args.report)
