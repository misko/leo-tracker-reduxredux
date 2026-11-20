"""Execute every recorded visit using the pinned original capture detector."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants.iq_stream import _read_prefix
from . import capture_exact_trial as exact
from . import capture_release
from . import recording_to_v5 as recording
from . import whole_memory_chain_worker as resources
from .capture_detector_replay import scan_capture_window
from .full_v5_check import BULK, _sha

IDENT = "DS29-0082"
REPORT = exact.REPORT.with_name("capture-whole")
WORK = Path("/var/tmp/leo-capture-whole-20261119")
CPUS = (2, 3, 4, 5, 6, 7, 12, 13, 22, 23)
LIMIT = 720
POSITION_LIMIT = 180
METHOD = "capture_combined_complete_iq"
MODULE = "tools.pipeline_eval.qualification.capture_whole"


def partition(chunks, invalid, cpus):
    """Disjoint authenticated chunk spans, prioritizing equal detector work."""
    work = {cpu: [] for cpu in cpus}
    totals = dict.fromkeys(cpus, 0)
    weights = [
        (sum(visit not in invalid for visit in range(base + first, base + stop)), item)
        for item in chunks
        for _, first, stop, base in [item]
    ]
    for n, item in sorted(weights, key=lambda x: (-x[0], x[1])):
        cpu = min(cpus, key=lambda c: (totals[c], len(work[c]), c))
        work[cpu].append(item)
        totals[cpu] += n
    return [(cpu, totals[cpu], sorted(work[cpu])) for cpu in cpus]


def freeze(work, cpus):
    from .fresh_replay_results import sealed

    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("this complete capture replay is already locked")
    case, original = whole_iq.binding(IDENT)
    receipt = sealed(exact.REPORT, "qualification-lock.json")
    prior = whole_iq.read(
        whole_iq.checked(exact.WORK / "source-lock.json", receipt["files"]["source-lock.json"])
    )
    cfg = prior["cases"][IDENT]
    cfg_sources = {**prior["sources"], **cfg["root"]["sources"]}
    for path, digest in cfg_sources.items():
        whole_iq.checked(Path(path), digest)
    libraries = {k: prior["libraries"][k] for k in ("batched32", "cfo", "fused")}
    for entry in libraries.values():
        whole_iq.checked(Path(entry["path"]), entry["sha256"])
    native = whole_iq.read(
        whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    )
    invalid = frozenset(row["visit"] for row in native["provenance"]["excluded_windows"])
    capture = capture_release.read_capture(case)
    if (
        capture["input_manifest_sha256"] != cfg["root"]["input_manifest_sha256"]
        or case["native"]["sha256"] != cfg["root"]["archived_native_sha256"]
        or len(invalid) != 1904
        or len(native["source"]["probes"]) != 9736
    ):
        raise ValueError("whole replay no longer matches the original qualified capture authority")
    chunks, count = [], 0
    for index, locator in enumerate(case["recording"]["segments"]):
        path = BULK / locator["path"]
        manifest = json.loads(_read_prefix(path, 65537))
        offset = 0
        for chunk in manifest["chunks"]:
            if chunk["first_sequence"] != offset or chunk["window_count"] <= 0:
                raise ValueError("segment chunk ranges are not complete and consecutive")
            stop = offset + chunk["window_count"]
            chunks.append((index, offset, stop, count))
            offset = stop
        if offset != manifest["window_count"]:
            raise ValueError("chunk roster omits recorded sequences")
        count += offset
    if count != 6772:
        raise ValueError("recording roster changed")
    known = {row["visit"] for row in cfg["rows"]}
    exclude = set(cfg["root"]["visits"]) | known | invalid
    unseen = sorted(
        set(range(count)) - exclude, key=lambda v: recording.digest([IDENT, "whole-smoke-v1", v])
    )[:2]
    smoke = [(row["segment"], row["sequence"], row["visit"]) for row in cfg["rows"]]
    for visit in unseen:
        index, _, _, base = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((index, visit - base, visit))
    prior_receiver = exact.REPORT.parent / "on-hit-waveforms/source-lock.json"
    prior_install = whole_iq.read(prior_receiver)
    receiver = Path(prior_install["receiver"])
    if whole_iq.receiver_identity(receiver) != prior_install["receiver_files"]:
        raise ValueError("same standalone compact release must be available")
    capture.update(case={k: case[k] for k in ("id", "run_id", "session_id")})
    lock = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        libraries=libraries,
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
        sources=cfg_sources | {str(p): _sha(p) for p in (Path(__file__), REPORT / "PROTOCOL.md")},
        qualification_sha256=_sha(exact.REPORT / "qualification-lock.json"),
        workers=partition(chunks, invalid, cpus),
        smoke=smoke,
        raw_limit_s=LIMIT,
        position_limit_s=POSITION_LIMIT,
        receiver=str(receiver),
        receiver_files=prior_install["receiver_files"],
        memory_max=whole_iq.MEMORY,
    )
    work.mkdir(mode=0o755)
    for path in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(path, lock)
        path.chmod(0o644)
    print(
        "cpu / planned valid / chunks",
        [(c, n, len(s)) for c, n, s in lock["workers"]],
        "smoke",
        smoke,
        flush=True,
    )


def configure(work):
    local = work / "source-lock.json"
    lock = whole_iq.read(whole_iq.checked(local, _sha(REPORT / local.name)))
    for name, digest in lock["sources"].items():
        whole_iq.checked(Path(name), digest)
    libs = {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libraries"].items()}
    whole_iq.checked(Path(lock["python"]), lock["python_sha256"])
    return lock, libs


def open_span(lock, segment, first, stop):
    from leo.storage.fast_scan import FastSegmentSource

    locator = lock["recording"]["segments"][segment]
    path = (BULK / locator["path"]).resolve()
    if path.name != "manifest.json" or not path.is_relative_to(BULK / "leo/fast-scan-recordings"):
        raise ValueError("unexpected IQ manifest path")
    source = FastSegmentSource(
        dict(path=str(path.parent), manifest_digest="sha256:" + locator["sha256"]),
        start_sequence=first,
        stop_sequence=stop,
    )
    if source.receiver_ids != (0, 1):
        raise ValueError("capture release requires both original physical receivers")
    return source


def policy_for(lock):
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    policy = FastScanPolicyV2()
    producer = capture_release.producer(lock["capture"]["case"], lock["capture"])
    if str(producer.root) != lock["producer"] or Path(sys.executable) != Path(lock["python"]):
        raise ValueError("installed capture policy source changed")
    from .full_v5_check import _bind_producer

    _bind_producer(lock["capture"]["case"], producer, policy)
    return policy


def smoke(work):
    lock, libs = configure(work)
    policy = policy_for(lock)
    results = []
    for segment, sequence, visit in lock["smoke"]:
        (window,) = open_span(lock, segment, sequence, sequence + 1).windows()
        if window.acquisition["global_visit"] != visit:
            raise ValueError("smoke addressed an unexpected visit")
        # The held harness requires its small reading view to expose receiver IDs.
        from types import SimpleNamespace

        observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
        base, combined = (
            exact.trial(observed, policy, mode, libs) for mode in ("installed", "combined")
        )
        if combined["status"] != "processed" or any(
            base[k] != combined[k] for k in ("public", "probes", "attempts")
        ):
            raise ValueError(f"original and combined detector differ on launch check {visit}")
        results.append(
            dict(
                visit=visit,
                iq_sha256=window.iq_sha256,
                installed_cpu_ns=base["cpu_ns"],
                combined_cpu_ns=combined["cpu_ns"],
                combined_wall_ns=combined["wall_ns"],
                probes_sha256=recording.digest(combined["probes"]),
            )
        )
    print(
        recording.encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=results)),
        flush=True,
    )


def raw(work, cpu):
    from leo.analysis.starlink import acquisition
    from leo.storage import short_window

    lock, libs = configure(work)
    _, planned, chunks = next(x for x in lock["workers"] if x[0] == cpu)
    policy, start = policy_for(lock), resources.memory()
    if start["cpus"] != [cpu]:
        raise ValueError("worker outside its planned CPU")
    grid = exact.capture_fft.FullGrid(libs["batched32"])
    member, verified = short_window.ShortWindowReader._member, []

    def stream(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return resources.AuthenticatedMember(path, size, digest, verified)
        return member(reader, name, size, digest)

    valid = 0
    with ExitStack() as scope:
        scope.enter_context(exact.refiners(libs))
        scope.enter_context(grid.route(acquisition, exact.starts.screen_module()))
        scope.enter_context(patch.object(short_window.ShortWindowReader, "_member", stream))
        for segment, first, stop, base in chunks:
            source, history = open_span(lock, segment, first, stop), len(verified)
            count, t = 0, perf_counter()
            for window in source.windows():
                a = window.acquisition
                if (
                    window.target["edge"] != lock["capture"]["edge"]
                    or a["global_visit"] != base + first + count
                ):
                    raise ValueError("signed physical edge or global window ordering changed")
                retune = json.loads(a.get("retune_receipt") or "{}")
                wall, elapsed = perf_counter(), process_time()
                status, probes = scan_capture_window(window, source.receiver_ids, policy)
                wall, elapsed = perf_counter() - wall, process_time() - elapsed
                grid_calls = len(grid.calls)
                if status.status == "processed":
                    if grid_calls < 2 or not all(c["applied"] for c in grid.calls):
                        raise ValueError("processed visit did not apply the full FFT grid")
                    valid += 1
                elif status.status != "invalid_capture" or grid_calls:
                    raise ValueError("original capture validity contract changed")
                grid.calls.clear()
                print(
                    recording.encoded(
                        dict(
                            kind="visit",
                            segment=segment,
                            sequence=window.sequence,
                            visit=a["global_visit"],
                            iq_sha256=window.iq_sha256,
                            sample_start=status.sample_start,
                            sample_end=status.sample_end,
                            generation=status.generation,
                            status=status.status,
                            reason=status.reason,
                            rf_mapping_authority=status.rf_mapping_authority,
                            probes=probes,
                            input_bytes=window.samples.nbytes,
                            grid_calls=grid_calls,
                            clock_anchor=retune.get("utc_clock_bracket"),
                            delivery_clock=retune.get("host_delivery_clock"),
                            detector_wall_s=wall,
                            detector_cpu_s=elapsed,
                        )
                    ),
                    flush=True,
                )
                count += 1
            if count != stop - first or len(verified) != history + 1:
                raise ValueError("capture chunk is incomplete or failed authentication")
            print(
                recording.encoded(
                    dict(
                        kind="chunk",
                        segment=segment,
                        first=first,
                        stop=stop,
                        path=str(source.reader.path),
                        manifest_digest=source.manifest_digest,
                        radio_id=source.radio["serial"],
                        compressed_bytes=verified[-1],
                        wall_s=perf_counter() - t,
                    )
                ),
                flush=True,
            )
    if valid != planned:
        raise ValueError("actual capture qualification differs from original exclusions")
    print(
        recording.encoded(
            dict(
                kind="worker",
                cpu=cpu,
                count=valid,
                start=start,
                end=resources.memory(),
                source_lock_sha256=_sha(work / "source-lock.json"),
            )
        ),
        flush=True,
    )


def command(work, cpu, action):
    lock, _ = configure(work)
    threads = {
        name + "_NUM_THREADS": "1"
        for name in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS")
    }
    return [
        "taskset",
        "-c",
        str(cpu),
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={lock['producer']}:{ROOT}",
        *(f"{k}={v}" for k, v in threads.items()),
        lock["python"],
        "-Bu",
        "-m",
        MODULE,
        action,
        str(work),
        str(cpu),
    ]


def service(unit, limit, args):
    return [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--working-directory=" + str(ROOT),
        "--property=MemoryMax=" + str(whole_iq.MEMORY),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={limit}s",
        *args,
    ]


def run(work):
    lock, _ = configure(work)
    variants = work / "smoke.json"
    if not variants.is_file():
        raise ValueError("complete workers require their genuine stock and combined IQ preflight")
    smoke_receipt = whole_iq.read(variants)
    if smoke_receipt["source_lock_sha256"] != _sha(work / "source-lock.json") or [
        s["visit"] for s in smoke_receipt["rows"]
    ] != [s[2] for s in lock["smoke"]]:
        raise ValueError("preflight did not validate the frozen visits")
    jobs = []
    started = perf_counter()
    with ExitStack() as scope:
        for cpu, _, _ in lock["workers"]:
            unit = f"leo-capture-whole-{cpu}-{uuid4().hex[:8]}"
            args = service(unit, lock["raw_limit_s"], command(work, cpu, "raw"))
            sink = scope.enter_context((work / f"cpu-{cpu}.jsonl").open("xb"))
            log = scope.enter_context((work / f"cpu-{cpu}.log").open("xb"))
            jobs.append((cpu, unit, subprocess.Popen(args, stdout=sink, stderr=log), args))
        save_json(
            work / "launch.json",
            dict(
                start_s=started,
                commands={c: a for c, _, _, a in jobs},
                source_lock_sha256=_sha(work / "source-lock.json"),
            ),
        )
        with ExitStack() as cancelled:
            for _, unit, process, _ in jobs:
                if process.poll() is None:
                    cancelled.callback(stop_if_running, process, unit)
            exits = {
                c: p.wait(timeout=max(10, started + lock["raw_limit_s"] + 25 - perf_counter()))
                for c, _, p, _ in jobs
            }
    save_json(work / "raw-exits.json", dict(exits=exits, wall_s=perf_counter() - started))
    print(exits, flush=True)


def stop_if_running(process, unit):
    if process.poll() is None:
        subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "run", "raw"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=12)
    parser.add_argument("--cpus", nargs="+", type=int, default=CPUS)
    args = parser.parse_args()
    if args.action == "freeze":
        if len(args.cpus) != len(set(args.cpus)) or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("choose distinct CPU assignments available to the worker")
        freeze(args.work, args.cpus)
    elif args.action == "preflight":
        result = subprocess.run(
            command(args.work, args.cpu, "smoke"), check=True, stdout=subprocess.PIPE, timeout=60
        )
        save_json(args.work / "smoke.json", json.loads(result.stdout))
        print(result.stdout.decode(), end="")
    elif args.action == "smoke":
        smoke(args.work)
    elif args.action == "raw":
        raw(args.work, args.cpu)
    else:
        run(args.work)
