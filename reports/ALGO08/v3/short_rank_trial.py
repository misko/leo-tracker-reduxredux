"""Profile strict timing and signed-carrier peak selection in the active 8 ms detector."""

import argparse
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.blind_compact_run import Factor
from .dense_geographic_trial import host
from .full_short_run import EIGHT_MS_SHA
from .mixed_aperture_receiver import NativePath, PILOT_SHA, StereoSchedule, verified

HERE = Path(__file__).resolve().parent
PUBLISH_BUILD = Path("/var/tmp/leo-v3-eight-ms-build-padded")
BUILD_PIN = "3ee8b9ceb4ec5b8b910520a673309f1799e632618b525d8234058c63d22f86b1"
RELINK_PIN = "b2324c7cfe3c60eecd59a98eda6b8d508c46e01df6ac81375db2f5f500493a30"
PRIMARY_WRAPPER_OBJECT = "90e6b9af8a0c9de5160016e0eba606f4e0ead8678576c24523138b72c0a3b5a2"
BUILD_CWD = Path("/tmp/leo-algo08v2-2x/native/algo08v2")
ASSETS = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets")
SOURCES = {
    "DS30-0008": (Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"),
                  "5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759", 77_442_779),
    "DS30-0016": (Path("/dev/shm/leo-v3-guarded-selective-0016-stage01/fast8-auto-20261113-112146-b04f5461-1-lower"
                      "/fast8-auto-20261113-112146-b04f5461-1-lower-segment-00000000"),
                  "1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc", 78_554_951),
}
RANK_GATE_NS = 40_000
ORDERS = (("active", "trace", "rebuilt"), ("rebuilt", "trace", "active"),
          ("trace", "active", "rebuilt"), ("rebuilt", "active", "trace"))


def one(text, old, new):
    if text.count(old) != 1:
        raise ValueError("The pinned rank boundary has changed")
    return text.replace(old, new, 1)


def traced(source):
    source = one(source, "    int radius = (int)nearbyint(6. / w->stride);",
                 "    uint64_t time_rank_started = rank_now();\n    int radius = (int)nearbyint(6. / w->stride);")
    source = one(source, "\n}\n\nstatic double bin_hz(",
                 "\n    rank_cost[0] += rank_now() - time_rank_started;\n}\n\nstatic double bin_hz(")
    source = one(source, "        int prev = -1;",
                 "        uint64_t carrier_rank_started = rank_now();\n        int prev = -1;")
    return one(source, "            prev = best;\n        }",
               "            prev = best;\n        }\n        rank_cost[1] += rank_now() - carrier_rank_started;")


def build(root):
    doc = json.loads(verified(PUBLISH_BUILD / "build.json", BUILD_PIN))["scout"]["arms"]["8ms"]
    link = json.loads(verified(PUBLISH_BUILD / "8ms/build-receipt.json", RELINK_PIN))
    command = link["relink"]
    objects = {Path(path).name: Path(path) for path in command if path.endswith(".o")}
    object_pins = link["short_object_sha256"] | {"two_carrier_receiver.o": PRIMARY_WRAPPER_OBJECT}
    for name, pin in object_pins.items():
        verified(objects[name], pin)
    name = "timing_first_receiver"
    text = verified(objects[name + ".o"].with_suffix(".c"), doc["source_sha256"][name]).decode()
    position = command.index(str(objects[name + ".o"]))
    calls = []

    def execute(args):
        args = list(map(str, args))
        calls.append(args)
        subprocess.run(args, cwd=BUILD_CWD, check=True)

    libraries = {"active": root / "active.so"}
    execute([*command[:-1], libraries["active"]])
    verified(libraries["active"], EIGHT_MS_SHA)
    for arm in ("trace", "rebuilt"):
        path = root / arm
        path.mkdir()
        c_path, obj = (path / name).with_suffix(".c"), (path / name).with_suffix(".o")
        c_path.write_text(traced(text) if arm == "trace" else text)
        trace_options = ["-D_POSIX_C_SOURCE=200809L", "-include", HERE / "short_rank_trace.h"] if arm == "trace" else []
        execute([*link["compile"][:-4], *trace_options, "-c", c_path, "-o", obj])
        libraries[arm] = path / "rank.so"
        execute([*command[:position], obj, *command[position+1:-1], libraries[arm]])
    return libraries, dict(commands=calls, pins={name: sha256(path.read_bytes()).hexdigest()
                                                for name, path in libraries.items()})


def read_member(case):
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    path, pin, length = SOURCES[case]
    if path.resolve(strict=True) != path or path.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Only the enrolled resident original member is admitted")
    verified(path / "manifest.json", pin)
    reader = ShortWindowReader(path)
    chunk = reader.manifest.chunks[0]
    if (chunk.first_sequence, chunk.window_count, chunk.compressed_bytes) != (0, 64, length):
        raise ValueError("Wrong signed first member")
    paths = [path / name for name in ("manifest.json", chunk.payload_relative_path, chunk.index_relative_path)]
    from .visit_frame_raw_0016 import resident

    if any(member.resolve(strict=True) != member or member.stat().st_dev != path.stat().st_dev for member in paths):
        raise ValueError("The original descriptor points beyond the declared tmpfs stage")
    before = resident(paths)
    loaded = process_time_ns(), perf_counter_ns()
    targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
    policy, schedule = FastScanPolicyV2(), StereoSchedule(full_coverage=True)
    rows, exclusions, anchors, hashes = [], [], [], []
    for window in reader.windows(start_sequence=0, stop_sequence=64):
        index = window.index
        if index.sequence != len(hashes):
            raise ValueError("Original signed visit order changed")
        hashes.append(index.iq_sha256)
        samples = window.samples
        if not valid_window_support(index.acquisition, reader.manifest.sample_rate_hz,
                                    samples.shape, reader.manifest.receiver_ids, policy):
            exclusions.append(index.sequence)
            continue
        target = targets[index.target_id]
        _, mode = schedule.visit(target["edge"], target, index.acquisition)
        if mode == "full":
            anchors.append(index.sequence)
            continue
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - index.acquisition["actual_if_center_hz"]
        rows.append((index.sequence, target["edge"], center, samples))
    if len(hashes) != 64 or len(anchors) != 8 or len(hashes) != len(rows) + len(exclusions) + len(anchors):
        raise ValueError("This trial requires the original mixed schedule through signed EOF")
    return rows, dict(manifest_sha256=pin, member=chunk.model_dump(mode="json"), before=before, after=resident(paths),
        excluded=exclusions, full_anchor=anchors, window_sha256=hashes,
        load_cpu_ns=process_time_ns()-loaded[0], load_wall_ns=perf_counter_ns()-loaded[1])


def callback(engine, samples, lane, center):
    result = (Factor * 2)()
    start = process_time_ns(), perf_counter_ns()
    count = engine.call(engine.native.ctx, samples.ctypes.data, lane, center-800000., center+800000., result)
    timing = process_time_ns()-start[0], perf_counter_ns()-start[1]
    if count not in (0, 1) or count and result[0].rank != 0:
        raise ValueError("The exact 8 ms ABI must produce zero or one verified primary")
    return bytes(result)[:count*ct.sizeof(Factor)], timing


def replay(rows, libraries, orders=ORDERS):
    with ExitStack() as stack:
        engines = {}
        for edge in sorted({row[1] for row in rows}):
            pilot = np.frombuffer(verified(ASSETS / (edge + ".f32"), PILOT_SHA[edge]), dtype="<f4")
            for arm, path in libraries.items():
                engine = NativePath(path, pilot, "short_primary")
                stack.callback(engine.close)
                engines[arm, edge] = engine
                if arm == "trace":
                    trace = engine.native.lib.short_rank_trace_take
                    trace.argtypes, trace.restype = (ct.POINTER(ct.c_uint64),), None
        records, fingerprint = [], []
        for visit, edge, center, samples in rows:
            trace = engines["trace", edge].native.lib.short_rank_trace_take
            for lane in (0, 1):
                expected = None
                trials = []
                for round_index, order in enumerate(orders):
                    rotated = order if (round_index+visit+lane) % 2 else order[::-1]
                    timed = {}
                    for arm in rotated:
                        result, (cpu, wall) = callback(engines[arm, edge], samples, lane, center)
                        if expected is None:
                            expected = result
                        if result != expected:
                            raise ValueError(f"The complete exported factor changed at {(visit, lane, arm)}")
                        observed = (ct.c_uint64 * 2)()
                        if arm == "trace":
                            trace(observed)
                        timed[arm] = dict(cpu=cpu, wall=wall, timing_rank=observed[0], carrier_rank=observed[1])
                    trials.append(timed)
                fingerprint.append(expected.hex())
                records.append(dict(visit=visit, lane=lane, center=center, positive=bool(expected), runs=trials))
    return records, sha256(json.dumps(fingerprint).encode()).hexdigest()


def summarize(rows):
    return {arm: {stage: median(sum(row["runs"][i][arm][stage] for row in rows)
                                 for i in range(len(rows[0]["runs"]))) / len(rows)
                   for stage in ("cpu", "wall", "timing_rank", "carrier_rank")}
            for arm in rows[0]["runs"][0]}


def profile(root, cases):
    machine = host()
    root.mkdir()
    libraries, binding = build(root)
    result = {}
    for case in cases:
        rows, proof = read_member(case)
        records, digest = replay(rows, libraries)
        summary = summarize(records)
        result[case] = dict(source=proof, lanes=len(records), positive=sum(r["positive"] for r in records),
                            exact_raw_factor_sha256=digest, records=records, ns_per_lane=summary,
                            advance=summary["trace"]["timing_rank"]+summary["trace"]["carrier_rank"] >= RANK_GATE_NS)
    (root / "profile.json").write_text(json.dumps(dict(machine=machine, build=binding, cases=result,
        stage_gate_ns=RANK_GATE_NS, waveform_backing_bytes=0), sort_keys=True) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--case", choices=SOURCES, required=True)
    args = cli.parse_args()
    profile(args.root, (args.case,))
