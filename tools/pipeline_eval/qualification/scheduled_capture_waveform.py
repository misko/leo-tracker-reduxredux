"""Replay a complete archived waveform with a fixed per-RF original acquisition cadence."""

import argparse
import json
import os
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.iq_stream import _read_prefix
from . import capture_whole as prior
from .capture_detector_replay import scan_capture_window
from .full_v5_check import BULK, _probe, _sha

IDENT = "DS26-0162"
MEMBERS = (IDENT, "DS26-0237", "DS29-0519")
PREVIOUS = prior.REPORT
REPORT = PREVIOUS.parents[1] / "original-support/scheduled-waveform"
WORK = Path("/var/tmp/leo-scheduled-capture-waveform-20261119")
CPUS = tuple(range(2, 8))
MODULE = "tools.pipeline_eval.qualification.scheduled_capture_waveform"
PERIOD = 4
METHOD = "original_capture_phase_staggered_four"


def selected(ordinal, channel):
    return (ordinal + channel - 1) % PERIOD == 0


def metadata(case):
    counters, rows, chunks = Counter(), [], []
    for segment, info in enumerate(case["recording"]["segments"]):
        path = BULK / info["path"]
        payload = _read_prefix(path, 65537)
        if sha256(payload).hexdigest() != info["sha256"]:
            raise ValueError("physical capture manifest digest changed")
        manifest = json.loads(payload)
        targets = {r["target_id"]: r for r in manifest["configuration"]["targets"]}
        base, sequence = len(rows), 0
        for item in manifest["chunks"]:
            index_name = item["index_relative_path"]
            if Path(index_name).name != index_name:
                raise ValueError("capture index member escapes the authoritative directory")
            data = _read_prefix(path.with_name(index_name), item["index_bytes"] + 1)
            if (
                len(data) != item["index_bytes"]
                or "sha256:" + sha256(data).hexdigest() != item["index_sha256"]
                or item["first_sequence"] != sequence
            ):
                raise ValueError("capture index digest or consecutive sequence changed")
            entries = [json.loads(line) for line in data.splitlines()]
            if len(entries) != item["window_count"]:
                raise ValueError("capture index count changed")
            chunks.append((segment, sequence, sequence + len(entries), base))
            for row in entries:
                a, target = row["acquisition"], targets[row["target_id"]]
                if row["sequence"] != sequence or a["global_visit"] != len(rows):
                    raise ValueError("capture index is not strictly chronological")
                channel, rf = target["channel"], target["rf_center_hz"]
                ordinal = counters[rf]
                counters[rf] += 1
                rows.append([channel, rf, ordinal, selected(ordinal, channel)])
                sequence += 1
    if len(rows) != case["recording"]["window_count"] or len(counters) != 8:
        raise ValueError("scheduled replay must preserve all eight recorded physical RF lanes")
    return rows, chunks


def freeze(work):
    from .fresh_replay_results import sealed

    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("prospective schedule already sealed")
    counts = {}
    for name in MEMBERS:
        case, _ = whole_iq.binding(name)
        loc = case["native"]
        archive = whole_iq.read(whole_iq.checked(BULK / loc["path"], loc["sha256"]))
        counts[name] = archive["provenance"]["processed_windows"]
    if min(counts, key=counts.get) != IDENT:
        raise ValueError("metadata-only selection changed")
    case, original = whole_iq.binding(IDENT)
    archive = whole_iq.read(
        whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    )
    exact = prior.exact
    receipt = sealed(exact.REPORT, "qualification-lock.json")
    bound = whole_iq.read(
        whole_iq.checked(exact.WORK / "source-lock.json", receipt["files"]["source-lock.json"])
    )
    cfg = bound["cases"][IDENT]
    capture = prior.capture_release.read_capture(case)
    if (
        capture["input_manifest_sha256"] != cfg["root"]["input_manifest_sha256"]
        or case["native"]["sha256"] != cfg["root"]["archived_native_sha256"]
    ):
        raise ValueError("recording does not match the prequalified capture implementation")
    capture.update(case={k: case[k] for k in ("id", "run_id", "session_id")})
    schedule, chunks = metadata(case)
    invalid = {p["visit"] for p in archive["provenance"]["excluded_windows"]}
    unneeded = {i for i, row in enumerate(schedule) if not row[-1]} | invalid
    known = set(cfg["root"]["visits"])
    untested = min(
        set(range(len(schedule))) - unneeded - known,
        key=lambda v: prior.recording.digest([IDENT, "phase4-unseen-v1", v]),
    )
    segment, _, _, base = next(c for c in chunks if c[3] + c[1] <= untested < c[3] + c[2])
    smoke = [(r["segment"], r["sequence"], r["visit"]) for r in cfg["rows"]]
    smoke.append((segment, untested - base, untested))
    common = whole_iq.read(PREVIOUS / "source-lock.json")
    source_files = (
        bound["sources"]
        | cfg["root"]["sources"]
        | {str(p): _sha(p) for p in (Path(__file__), Path(prior.__file__), REPORT / "PROTOCOL.md")}
    )
    work.mkdir(mode=0o755)
    save_json(work / "schedule.json", schedule)
    (work / "schedule.json").chmod(0o644)
    lock = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        libraries={k: bound["libraries"][k] for k in ("batched32", "cfo", "fused")},
        original=dict(
            native=case["native"],
            request=case["request"],
            catalog=case["catalog"],
            tile=case["regions"][0],
            causal_snapshots=original["causal_snapshots"],
        ),
        producer=cfg["root"]["producer"],
        python=cfg["python"],
        python_sha256=cfg["python_sha256"],
        sources=source_files,
        raw_limit_s=600,
        position_limit_s=180,
        receiver=common["receiver"],
        receiver_files=common["receiver_files"],
        qualification_sha256=_sha(exact.REPORT / "qualification-lock.json"),
        memory_max=whole_iq.MEMORY,
        smoke=smoke,
        counts=counts,
        workers=prior.partition(chunks, unneeded, CPUS),
        schedule_sha256=_sha(work / "schedule.json"),
        selected_valid=len(schedule) - len(unneeded),
        scheduled=sum(row[-1] for row in schedule),
    )
    for path in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(path, lock)
        path.chmod(0o644)
    print("selected valid", lock["selected_valid"], "smoke", smoke, flush=True)


def probe_skipped(window, receiver_ids, policy):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    def empty(_, ids):
        return tuple(FastScanReceiverV1(receiver_id=i, candidates=()) for i in ids)

    result = analyze_window(window, receiver_ids, None, policy, detector=empty)
    return result, [_probe(window, r.receiver_id, ()) for r in result.receivers]


def raw(work, cpu):
    from leo.analysis.starlink import acquisition
    from leo.storage import short_window

    lock, libraries = prior.configure(work)
    schedule = whole_iq.read(whole_iq.checked(work / "schedule.json", lock["schedule_sha256"]))
    _, planned, chunks = next(r for r in lock["workers"] if r[0] == cpu)
    policy, start = prior.policy_for(lock), prior.resources.memory()
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("raw acquisition must use its selected capped CPU")
    grid = prior.exact.capture_fft.FullGrid(libraries["batched32"])
    member, verified = short_window.ShortWindowReader._member, []

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return prior.resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    valid = 0
    with ExitStack() as scope:
        scope.enter_context(prior.exact.refiners(libraries))
        scope.enter_context(grid.route(acquisition, prior.exact.starts.screen_module()))
        scope.enter_context(patch.object(short_window.ShortWindowReader, "_member", stream))
        for segment, first, stop, base in chunks:
            source, history = prior.open_span(lock, segment, first, stop), len(verified)
            count, chunk_start = 0, perf_counter()
            for window in source.windows():
                a, t = window.acquisition, window.target
                visit = base + first + count
                channel, rf, ordinal, acquire = schedule[visit]
                if (a["global_visit"], t["channel"], t["rf_center_hz"], t["edge"]) != (
                    visit,
                    channel,
                    rf,
                    lock["capture"]["edge"],
                ) or acquire != selected(ordinal, channel):
                    raise ValueError("sealed scheduling metadata differs from decoded input")
                fn = scan_capture_window if acquire else probe_skipped
                wall, cpu_time = perf_counter(), process_time()
                result, probes = fn(window, source.receiver_ids, policy)
                wall, cpu_time = perf_counter() - wall, process_time() - cpu_time
                if result.status == "processed":
                    if acquire:
                        if len(grid.calls) < 2 or not all(c["applied"] for c in grid.calls):
                            raise ValueError("selected visit omitted original FFT acquisition")
                        valid += 1
                    elif grid.calls or any(p["candidates"] for p in probes):
                        raise ValueError("scheduled omission acquired original data")
                    status = "processed" if acquire else "skipped_policy"
                elif result.status == "invalid_capture" and not grid.calls and not probes:
                    status = result.status
                else:
                    raise ValueError("unexpected capture validity or folded work")
                retune = json.loads(a.get("retune_receipt") or "{}")
                print(
                    prior.recording.encoded(
                        dict(
                            kind="visit",
                            segment=segment,
                            sequence=window.sequence,
                            visit=visit,
                            iq_sha256=window.iq_sha256,
                            sample_start=result.sample_start,
                            sample_end=result.sample_end,
                            generation=result.generation,
                            status=status,
                            reason=result.reason,
                            rf_mapping_authority=result.rf_mapping_authority,
                            probes=probes,
                            input_bytes=window.samples.nbytes,
                            grid_calls=len(grid.calls),
                            clock_anchor=retune.get("utc_clock_bracket"),
                            delivery_clock=retune.get("host_delivery_clock"),
                            detector_wall_s=wall,
                            detector_cpu_s=cpu_time,
                            rf_center_hz=rf,
                            selected=acquire,
                        )
                    ),
                    flush=True,
                )
                grid.calls.clear()
                count += 1
            if count != stop - first or len(verified) != history + 1:
                raise ValueError("scheduled replay failed complete chunk authentication")
            print(
                prior.recording.encoded(
                    dict(
                        kind="chunk",
                        segment=segment,
                        first=first,
                        stop=stop,
                        path=str(source.reader.path),
                        manifest_digest=source.manifest_digest,
                        radio_id=source.radio["serial"],
                        compressed_bytes=verified[-1],
                        wall_s=perf_counter() - chunk_start,
                    )
                ),
                flush=True,
            )
    if valid != planned:
        raise ValueError("selected measured validity differs from its original capture authority")
    print(
        prior.recording.encoded(
            dict(
                kind="worker",
                cpu=cpu,
                count=valid,
                start=start,
                end=prior.resources.memory(),
                source_lock_sha256=_sha(work / "source-lock.json"),
            )
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "run", "raw"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=2)
    args = parser.parse_args()
    with patch.multiple(prior, REPORT=REPORT, MODULE=MODULE):
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "smoke":
            prior.smoke(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        elif args.action == "run":
            prior.run(args.work)
        else:
            import subprocess

            smoke = subprocess.run(
                prior.command(args.work, args.cpu, "smoke"),
                check=True,
                stdout=subprocess.PIPE,
                timeout=60,
            )
            save_json(args.work / "smoke.json", json.loads(smoke.stdout))
            print(smoke.stdout.decode(), end="")


if __name__ == "__main__":
    main()
