"""Build causal native compact inputs for fixed recorded-arrival queue policies."""

import argparse
import csv
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, original_receiver as original, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distribution
from ..variants import native_arrival as queue
from . import accelerated_command_results as accelerated
from . import arrival_queue_position, capture_whole_results as capture, portable_field_scores as field
from . import recording_to_v5 as recording
from .full_v5_check import BULK, _load_case, _sha

OUT = field.OUT.with_name("native-arrival")
CASE = field.CASE
POLICY_ORDER = (
    (4, queue.Policy.ROUND_ROBIN),
    (1, queue.Policy.ROUND_ROBIN),
    (4, queue.Policy.FIFO),
    (4, queue.Policy.REPLACE),
    (1, queue.Policy.FIFO),
    (1, queue.Policy.REPLACE),
)
MISSING = "next-delivery"
LIMIT_S = 180
EXPRESS = "accelerated-secondary"
NATIVE = "portable-field"


def method(workers, policy):
    return f"{workers}w-{policy.value}"


def pack(path, document):
    write(path, gzip.compress(encoded(document) + b"\n", mtime=0))


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def signed_bytes(path, digest, limit):
    data = original._read_prefix(path, limit + 1)
    if len(data) > limit or sha256(data).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"signed input differs from its capture manifest: {path}")
    return data


def signed_inputs(case):
    identities, rf_bins, visits, members = None, None, [], {}
    for locator in case["recording"]["segments"]:
        path = BULK / locator["path"]
        manifest = json.loads(signed_bytes(path, locator["sha256"], 65536))
        targets = manifest["configuration"]["targets"]
        identity = {target["target_id"]: target["rf_center_hz"] for target in targets}
        order = [target["rf_center_hz"] for target in targets]
        if rf_bins is not None and (rf_bins != order or identities != identity):
            raise ValueError("signed configured RF order changed within the recording")
        rf_bins, identities = order, identity
        for chunk in manifest["chunks"]:
            index = path.parent / chunk["index_relative_path"]
            members[str(index)] = chunk["index_sha256"]
            data = signed_bytes(index, chunk["index_sha256"], chunk["index_bytes"])
            for line in data.splitlines():
                row = json.loads(line)
                acquire = row["acquisition"]
                clocks = json.loads(acquire["retune_receipt"])
                if acquire["global_visit"] != len(visits) or acquire["counter_authority"] != "hardware":
                    raise ValueError("signed index lacks ordered hardware-counter authority")
                visits.append(dict(
                    visit=len(visits),
                    rf=identity[row["target_id"]],
                    sample_start=acquire["sample_start"],
                    sample_end=acquire["sample_end"],
                    delivery_clock=clocks["host_delivery_clock"],
                    iq_sha256=row["iq_sha256"],
                    input_bytes=row["payload_bytes"],
                ))
    if len(visits) != case["recording"]["window_count"] or len(rf_bins) != queue.WAITING:
        raise ValueError("capture differs from the signed arrival roster or RF budget")
    return visits, rf_bins, members


def archived_timing(case, physical):
    parent = whole_iq.checked(field.HISTORICAL / field.PREDICTION_SEAL, field.HISTORICAL_PREDICTION_SHA)
    files = whole_iq.read(parent)["files"]
    name = "secondary-raw-visits.csv"
    path = whole_iq.checked(field.HISTORICAL / name, files[name])
    witness = "secondary-raw-receipt.json"
    receipt = whole_iq.read(whole_iq.checked(field.HISTORICAL / witness, files[witness]))
    native = whole_iq.read(whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"]))
    with path.open() as source:
        samples = list(csv.DictReader(source))
    if not receipt["complete"] or len(samples) != len(physical):
        raise ValueError("accelerated timing baseline lacks a complete measured replay")
    invalid = {r["visit"] for r in native["provenance"]["excluded_windows"]}
    for row, visit, clock in zip(samples, physical, native["delivery_clocks"], strict=True):
        i = visit["visit"]
        status = "invalid_capture" if i in invalid else "processed"
        if (int(row["visit"]), row["status"], clock) != (i, status, visit["delivery_clock"]):
            raise ValueError("accelerated timing baseline shifts original visit authority")
    return samples, dict(predictions=_sha(parent), timings=_sha(path), receipt=files[witness])


def native_timing(work, case, physical):
    lock_path = work / "source-lock.json"
    lock = whole_iq.read(lock_path)
    roster = sorted(tuple(c) for _, _, pieces in lock["workers"] for c in pieces)
    if lock["case"] != case or roster != sorted(original.chunks(case)) or lock["smoke"]:
        raise ValueError("portable detector run lacks the complete frozen capture roster")
    shards, workers, _ = original.collect(work, lock)
    if any(r["exit_code"] != 0 for r in workers.values()):
        raise ValueError("portable detector run lacks authenticated worker terminals")
    index_receipts = field.verify_signed_chunks(case, shards)
    full, counts = capture.assemble(case, lock, shards)
    full["provenance"]["scope"] = "fresh portable C original acquisition and GLRT from signed CI16"
    rows = capture.summary_rows(shards)
    if len(rows) != len(physical) or full["delivery_clocks"] != [a["delivery_clock"] for a in physical]:
        raise ValueError("native raw ledgers differ from the signed physical arrivals")
    full_sha = recording.digest(full)
    return rows, full, dict(
        source_lock=_sha(lock_path),
        raw_exits=_sha(work / "raw-exits.json"),
        index_receipts=index_receipts,
        workers={cpu: r["output_sha256"] for cpu, r in workers.items()},
        native_document_sha256=full_sha,
        counts=counts,
    )


def schedule_inputs(physical, samples):
    origin = physical[0]["delivery_clock"]["monotonic_ns"]
    arrivals, cpu, wall = [], [], []
    for row, visit in zip(samples, physical, strict=True):
        if int(row["visit"]) != visit["visit"] or row["status"] not in ("processed", "invalid_capture"):
            raise ValueError("timing row lacks a signed physical visit and measured validity")
        valid = row["status"] == "processed"
        offset = visit["delivery_clock"]["monotonic_ns"] - origin
        arrivals.append(queue.Arrival(visit["visit"], offset, visit["rf"], valid))
        cpu.append(round(float(row["cpu_ms"]) * 1e6) if valid else 0)
        wall.append(round(float(row["wall_ms"]) * 1e6) if valid else 0)
    return arrivals, {"cpu": cpu, "wall": wall}


def stats(arrivals, trace, durations, selected):
    finishes = trace["finish_ns"]
    starts = trace["start_ns"]
    return dict(
        outcomes=dict(Counter(trace["outcomes"].values())),
        ready_count=len(selected),
        ready_by_last_delivery=sum(finishes[i] <= arrivals[-1].time_ns for i in selected),
        ready_by_next_count=len(trace["ready_next"]),
        valid_count=sum(r.valid for r in arrivals),
        last_delivery=trace["last_delivery"],
        final_deadline=trace["deadline"],
        final_deadline_s=trace["deadline_ns"] / queue.NS,
        peak_waiting=trace["peak_waiting"],
        ready_per_rf=dict(sorted(Counter(arrivals[i].rf for i in selected).items())),
        age_ms=distribution((finishes[i] - arrivals[i].time_ns) / 1e6 for i in selected),
        wait_ms=distribution((starts[i] - arrivals[i].time_ns) / 1e6 for i in selected),
        service_ms=distribution(ns / 1e6 for ns in durations if ns),
    )


def schedules(physical, samples, rf_bins):
    arrivals, durations = schedule_inputs(physical, samples)
    models = {}
    for timing, span in durations.items():
        models[timing] = {}
        for workers, policy in POLICY_ORDER:
            trace = queue.simulate(arrivals, span, workers, policy, rf_bins)
            retained = [i for i, outcome in sorted(trace["outcomes"].items()) if outcome == "ready"]
            models[timing][method(workers, policy)] = dict(
                selected=retained,
                trace=trace,
                summary=stats(arrivals, trace, span, retained),
            )
        trace = queue.simulate(arrivals, span, 1, queue.Policy.FIFO, rf_bins, capacity=0)
        models[timing][MISSING] = dict(
            selected=trace["ready_next"], trace=trace,
            summary=stats(arrivals, trace, span, trace["ready_next"]),
        )
    return models


def prepare(output, native):
    case = _load_case(CASE)
    physical, rf_bins, members = signed_inputs(case)
    if native is None:
        label = EXPRESS
        samples, source = archived_timing(case, physical)
        full = None
    else:
        label = NATIVE
        samples, full, source = native_timing(native, case, physical)
    schedules_path = output / f"{label}-schedules.json.gz"
    physical_path = output / f"{label}-physical.json.gz"
    pack(schedules_path, schedules(physical, samples, rf_bins))
    pack(physical_path, dict(windows=physical, timings=samples, rf_bins=rf_bins))
    save_json(output / f"{label}-schedule-lock.json", dict(
        files={p.name: _sha(p) for p in (schedules_path, physical_path)},
        source=source,
        native=str(native) if native is not None else None,
        signed_indices=members,
        sources={str(p): _sha(p) for p in (Path(__file__), Path(queue.__file__), OUT / "PROTOCOL.md")},
    ))
    return case, full


def retained_document(full, selected, schedule_sha):
    found = [r for r in full["source"]["probes"] if r["visit_index"] in selected]
    if [(r["visit_index"], r["receiver_id"]) for r in found] != [
        (i, lane) for i in sorted(selected) for lane in (0, 1)
    ]:
        raise ValueError("selected physical visits lack their complete ordered dual-receiver pair")
    all_valid = {r["visit_index"] for r in full["source"]["probes"]}
    if selected == all_valid:
        return full
    reduced = arrival_queue_position.subtract(full, all_valid - selected, schedule_sha)
    reduced["provenance"]["scope"] = "whole portable C probe pairs selected by a modeled bounded arrival queue"
    return reduced


def fit_case(work, output, case, compact_lock, full, key, cpu, selection):
    selected = set(selection["selected"])
    if not selected:
        return dict(method=key, native_sha256=None, fit=None, selected=0, result=dict(
            status="withheld", reason="no measured detector packet satisfies the publication boundary",
            boundary="modeled detector publication to matched compact solver",
            metrics=dict(terminal_position_decision=True, position_attempted=False),
            arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
        ))
    base = work / key
    base.mkdir()
    native = base / "native.json"
    schedule_sha = recording.digest(selection)
    recording.save(native, retained_document(full, selected, schedule_sha))
    save_json(base / "source-lock.json", compact_lock | dict(
        schedule_lock_sha256=_sha(output / f"{NATIVE}-schedule-lock.json"),
        schedule_sha256=schedule_sha,
        original_request_sha256=case["request"]["sha256"],
        catalogue_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
    ))
    attempt = base / "position"
    request = attempt / "recording/request.json"
    request.parent.mkdir(parents=True)
    native_sha = original.bind_fresh(case, native, request)
    save_json(attempt / "raw.json", dict(native_sha256=native_sha, request_sha256=_sha(request)))
    receiver = compact_lock["receiver"]
    service = original.service(attempt, cpu, LIMIT_S, "position", dict(receiver=receiver))
    result, fit = accelerated.position_state(
        base, service, original.failure_status((service,)), _sha(base / "source-lock.json"), receiver, cpu,
    )
    row = dict(method=key, native_sha256=native_sha, result=result, fit=fit, selected=len(selected))
    save_json(base / "fit.json", row)
    return row


def fit(work, output, native, cpus):
    work.mkdir()
    case, full = prepare(output, native)
    lock = whole_iq.read(native / "source-lock.json")
    compact_lock = {k: lock[k] for k in ("receiver", "receiver_files")}
    path = output / f"{NATIVE}-schedules.json.gz"
    selections = unpack(path)["cpu"]
    modes = [method(w, p) for w, p in POLICY_ORDER] + [MISSING]

    def lane(index):
        return [fit_case(work, output, case, compact_lock, full, mode, cpus[index], selections[mode])
                for mode in modes[index::len(cpus)]]

    with (patch.object(iq_service, "MODULE", original.MODULE),
          ThreadPoolExecutor(max_workers=len(cpus)) as pool):
        results = {row["method"]: row for rows in pool.map(lane, range(len(cpus))) for row in rows}
    pack(output / "queue-fits.json.gz", [results[key] for key in modes])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("baseline", "fit"))
    parser.add_argument("--output", default=OUT, type=local_output)
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--native", type=local_output)
    parser.add_argument("--cpus", nargs="+", type=int, default=[1, 2])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.stage == "baseline":
        prepare(args.output, None)
    else:
        if args.work is None or args.native is None or len(set(args.cpus)) != len(args.cpus):
            parser.error("fit requires fresh work, complete native raw directory and distinct CPUs")
        fit(args.work, args.output, args.native, args.cpus)


if __name__ == "__main__":
    main()
