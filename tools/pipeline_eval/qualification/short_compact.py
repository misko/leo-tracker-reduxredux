"""Replay the compact receiver on disjoint causal factor blocks and full controls."""

import argparse
import gzip
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, validate_result
from . import short_compact_worker
from .full_v5_check import BULK, _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "support-preserving/short-compact"
WAVE = SCREEN / "acquisition-frontier/waveform-holdout"
WAVE_WORK = Path("/home/mouse9911/.cache/waveform-holdout-20261119/public")
ROOF = ("DS26-0036", "DS29-0082", "DS26-0168", "DS29-0604")
BLOCKS = ((0, 75), (75, 150), (150, 225))
LIMIT = {"block": 180, "full": 240}
THREAD_ENV = whole_iq.recording.SINGLE_THREAD


def scopes(doc):
    """Build sample support once. Do not alter the original UTC anchor or counters."""
    source, receipt = doc["source"], doc["provenance"]
    rate = source["sample_rate_hz"]
    span = rate * source["probe_ms"] // 1000
    first = doc["clock_anchor"]["sample_counter"]
    clocks = doc["delivery_clocks"]
    by_visit = defaultdict(list)
    for row in source["probes"]:
        by_visit[row["visit_index"]].append(row)
    invalid = {row["visit"]: row for row in receipt["excluded_windows"]}
    if (
        len(clocks) != receipt["window_count"]
        or len(by_visit) != receipt["processed_windows"]
        or len(invalid) != receipt["invalid_capture"]
        or by_visit.keys() & invalid.keys()
        or by_visit.keys() | invalid.keys() != set(range(len(clocks)))
        or any(
            a["monotonic_ns"] >= b["monotonic_ns"] for a, b in zip(clocks, clocks[1:], strict=False)
        )
    ):
        raise ValueError("native visit and original delivery authority disagree")
    stop = first
    intervals = []
    for visit, clock in enumerate(clocks):
        probes = by_visit.get(visit, [])
        bad = invalid.get(visit)
        if bad is None:
            if len(probes) != 2 or {p["receiver_id"] for p in probes} != {0, 1}:
                raise ValueError("a physical visit must contain two receiver probes")
            start = probes[0]["valid_start_counter"]
            end = start + span
            if any(p["valid_start_counter"] != start for p in probes):
                raise ValueError("receiver probes disagree on their device input interval")
        else:
            start, end = bad["sample_start"], bad["sample_end"]
        if start < stop or end - start != span:
            raise ValueError("device capture windows overlap or have wrong sample count")
        intervals.append((start, end, clock, probes, bad, visit))
        stop = end
    if stop != doc["last_sample_counter"]:
        raise ValueError("native visit authority fails to close at the original final counter")
    return intervals


def snapshot(doc, intervals, block):
    anchor, source = doc["clock_anchor"], doc["source"]
    first, rate = anchor["sample_counter"], source["sample_rate_hz"]
    start, stop = (0, None) if block is None else block
    a = first + start * rate
    b = doc["last_sample_counter"] if stop is None else first + stop * rate
    selected = [row for row in intervals if a <= row[0] and row[1] <= b]
    if not selected:
        raise ValueError("time block contains no complete visit")
    probes = [probe for row in selected for probe in row[3]]
    excluded = [row[4] for row in selected if row[4] is not None]
    last_clock = selected[-1][2]["monotonic_ns"]
    availability = [
        max(stop or 0, (last_clock - anchor[edge]["monotonic_ns"]) / 1e9)
        for edge in ("after", "before")
    ]
    projected = dict(
        clock_anchor=anchor,
        delivery_clocks=[row[2] for row in selected],
        last_sample_counter=selected[-1][1],
        source={k: source[k] for k in ("probe_ms", "sample_rate_hz", "session_id")}
        | dict(probes=probes),
        provenance=dict(
            window_count=len(selected),
            processed_windows=len(selected) - len(excluded),
            invalid_capture=len(excluded),
            excluded_windows=excluded,
        ),
    )
    info = dict(
        block=block,
        seconds=[(selected[0][0] - first) / rate, (selected[-1][1] - first) / rate],
        available_s=availability,
        first_visit=selected[0][-1],
        last_visit=selected[-1][-1],
        scheduled=len(selected),
        invalid=len(excluded),
        probe_count=len(probes),
    )
    return projected, info


def original(ident):
    case, original_request = whole_iq.binding(ident)
    job = original_request["job"]
    path = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    return dict(
        profile="roof",
        id=ident,
        tile=case["regions"][0],
        original_request_sha256=case["request"]["sha256"],
        native=str(path),
        native_sha256=_sha(path),
        catalog_sha256=case["catalog"]["sha256"],
        snapshots=original_request["causal_snapshots"],
        session=case["session_id"],
        archive=job["tle_root"],
        track_config=job["track_config"]["path"],
        config_sha256=job["track_config"]["sha256"],
        screen_center=job["screen_center"],
    )


def waveform(base):
    receipt = whole_iq.read(WAVE / "detector-lock.json")
    for name in ("native.json.gz", "requests.json"):
        whole_iq.checked(WAVE / name, receipt["files"][name])
    native = base / "waveform-native.json"
    write(native, gzip.decompress((WAVE / "native.json.gz").read_bytes()))
    history = whole_iq.read(WAVE / "causal-authority.json")
    archive = WAVE_WORK / "tle"
    snapshots = {name: row["sha256"] for name, row in history.items()}
    if {p.name: _sha(p) for p in archive.rglob("*.tle")} != snapshots:
        raise ValueError("waveform causal TLE history differs from its measured envelope")
    results = []
    for row in whole_iq.read(WAVE / "requests.json"):
        source = whole_iq.checked(native, row["native_sha256"])
        config = whole_iq.checked(WAVE_WORK / row["track_config"], row["config_sha256"])
        results.append(
            dict(
                row,
                profile="waveform",
                native=str(source),
                snapshots=snapshots,
                archive=str(archive),
                track_config=str(config),
                tile=dict(center=row["tile"], width_km=25.0),
            )
        )
    return results


def prepare(base):
    protocol = REPORT / "PROTOCOL.md"
    plan = REPORT / "source-lock.json"
    if plan.exists():
        raise FileExistsError("a short-compact source lock is already published")
    base.mkdir(exist_ok=False)
    plans = [*(original(ident) for ident in ROOF), *waveform(base)]
    receiver = cavity_runtime.install(base / "receiver", profile="phase-release")
    lock = dict(
        cases={row["id"]: row for row in plans},
        orders={
            "18": [plans[i]["id"] for i in (0, 3, 4, 6)],
            "19": [plans[i]["id"] for i in (1, 2, 5)],
        },
        receiver=str(receiver),
        receiver_files=whole_iq.receiver_identity(receiver),
        protocol_sha256=_sha(protocol),
        sources={
            str(path.relative_to(ROOT)): _sha(path)
            for path in (Path(__file__), Path(short_compact_worker.__file__))
        },
        waveform_files={
            name: _sha(WAVE / name) for name in ("detector-lock.json", "causal-authority.json")
        },
        limits_s=LIMIT,
        blocks=BLOCKS,
    )
    save_json(plan, lock)
    write(base / "source-lock.sha256", (_sha(plan) + "\n").encode())


def no_fix(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary="Archived native detection factors through compact v5",
        arms={arm: {"latlon": None} for arm in ARMS},
        metrics={},
    )


def run_method(base, spec, doc, visits, receiver, cpu, name, limits):
    import os

    block = None if name == "full" else BLOCKS[int(name)]
    attempt = base / spec["id"] / name
    if (attempt / "prediction.json").is_file():
        return
    attempt.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    view, timing = snapshot(doc, visits, block)
    native = attempt / "block.json"
    if block is None:
        native = Path(spec["native"])
    else:
        write(native, encoded(view) + b"\n")
    request = dict(
        native=str(native),
        native_sha256=_sha(native),
        archive=spec["archive"],
        track_config=spec["track_config"],
        config_sha256=spec["config_sha256"],
        tile=spec["tile"]["center"],
        width_km=spec["tile"].get("width_km", 25.0),
        session=spec["session"],
        screen_center=spec["screen_center"],
    )
    parameters = attempt / "request.json"
    if block is None:
        solve = [sys.executable, "-IB", str(receiver)]
        for key, value in request.items():
            values = value if isinstance(value, list) else [value]
            solve.extend(["--" + key.replace("_", "-"), *map(str, values)])
    else:
        save_json(
            parameters,
            dict(
                request,
                native_backend=str(receiver / "native/manifest.json"),
                library=str(receiver / "projector.so"),
            ),
        )
        solve = [
            sys.executable,
            "-IB",
            short_compact_worker.__file__,
            str(receiver),
            str(parameters),
        ]
    preparation = perf_counter() - started
    wall = perf_counter()
    usage = attempt / "usage"
    deadline = limits["full" if block is None else "block"]
    with (attempt / "stdout.json").open("wb") as stdout, (attempt / "stderr.log").open("wb") as log:
        status = subprocess.run(
            [
                "nice",
                "-n",
                "10",
                "taskset",
                "-c",
                str(cpu),
                "/usr/bin/time",
                "-o",
                str(usage),
                "-f",
                "%U %S %M",
                "timeout",
                "-k",
                "5",
                str(deadline),
                *solve,
            ],
            stdout=stdout,
            stderr=log,
            env=os.environ | THREAD_ENV,
            check=False,
        ).returncode
    elapsed = perf_counter() - wall
    user, system, rss = usage.read_text().splitlines()[-1].split()
    result = (
        whole_iq.read(attempt / "stdout.json")
        if status == 0
        else no_fix("timed_out" if status in (124, 137) else "failed", f"worker exit {status}")
    )
    validate_result(result)
    row = dict(
        id=spec["id"],
        profile=spec["profile"],
        name=name,
        native_sha256=spec["native_sha256"],
        catalog_sha256=spec["catalog_sha256"],
        tile=spec["tile"],
        cpu=cpu,
        input_sha256=request["native_sha256"],
        input_preparation_wall_s=preparation,
        worker_wall_s=elapsed,
        worker_cpu_s=float(user) + float(system),
        peak_rss_kib=int(rss),
        support=timing,
        result=result,
    )
    save_json(attempt / "prediction.json", row)
    print(spec["id"], name, result["status"], elapsed, flush=True)


def run(base):
    path = REPORT / "source-lock.json"
    lock = whole_iq.read(whole_iq.checked(path, (base / "source-lock.sha256").read_text().strip()))
    receiver = Path(lock["receiver"])
    if whole_iq.receiver_identity(receiver) != lock["receiver_files"]:
        raise ValueError("phase-release executable differs from the frozen source")
    for name, digest in lock["sources"].items():
        whole_iq.checked(ROOT / name, digest)

    def lane(item):
        cpu, ids = item
        for ident in ids:
            spec = lock["cases"][ident]
            native = whole_iq.checked(Path(spec["native"]), spec["native_sha256"])
            whole_iq.checked(Path(spec["track_config"]), spec["config_sha256"])
            archives = {p.name: _sha(p) for p in Path(spec["archive"]).rglob("*.tle")}
            if archives != {
                name: h.removeprefix("sha256:") for name, h in spec["snapshots"].items()
            }:
                raise ValueError("replay causal catalogue differs from the frozen roster")
            doc = whole_iq.read(native)
            visits = scopes(doc)
            for name in ("0", "1", "2", "full"):
                run_method(base, spec, doc, visits, receiver, int(cpu), name, lock["limits_s"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lane, lock["orders"].items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("base", type=local_output)
    args = parser.parse_args()
    (prepare if args.command == "prepare" else run)(args.base)


if __name__ == "__main__":
    main()
