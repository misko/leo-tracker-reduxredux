"""Compare released post-scout verification with an independent held pilot aperture."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import json
import math
import os
from pathlib import Path
from statistics import mean, median, quantiles
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import V3_SHA
from tools.pipeline_eval.variants.experimental.receiver_tracking import agree

from .directed_verifier_trial import Timing, continuation, replace_once, tuple_factor


ARMS = ("release", "linked", "free_readout", "held_blocks")
ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "tools/pipeline_eval/variants/experimental/receiver_scout_readout.inc"
TWO_CARRIER = Path("/tmp/leo-algo08v2-2x-bench/site-free-mode-pair-pgo/candidate/objects/two_carrier_receiver.c")
SOURCE_SHA = "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7"
PILOT_SHA = {"lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
             "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c"}
ACQUISITION = Path(__file__).with_name("measurements") / "acquisition-split-DS30-0008.json"
ACQUISITION_SHA = "b4bd3489b7b7c3477f7177ca5714f420ce2b8bf845f5c03315f3f8d8c4192421"
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


class Stock(ct.Structure):
    _fields_ = [("examined", ct.c_uint), ("flags", ct.c_uint), ("offset", ct.c_double),
                ("residual_hz", ct.c_double), ("exact", ct.c_double), ("control", ct.c_double)]


class Held(ct.Structure):
    _fields_ = [*((n, ct.c_int) for n in ("examined", "accepted", "rolled_accepted", "frames")),
                *((n, ct.c_double) for n in ("offset", "hz", "exact", "control")),
                ("group_hz", ct.c_double * 2)]


class Trace(ct.Structure):
    _fields_ = [("scout", Timing * 2), ("stock", Stock * 2), ("block", Held * 2),
                ("loading_cpu_ns", ct.c_uint64), ("verification_cpu_ns", ct.c_uint64)]


def build(work, installed, archive):
    if digest(installed.read_bytes()) != V3_SHA or digest(TWO_CARRIER.read_bytes()) != SOURCE_SHA:
        raise ValueError("Unexpected pinned release or two-carrier layout")
    recipe = json.loads((archive / "build.json").read_bytes())
    source = TWO_CARRIER.read_text()
    header = source[:source.index("TwoCarrierReceiver *two_carrier_create(")]
    private = source[source.index("static int same_peak("):source.index("static int measure(")]
    private = replace_once(private, "        if (!(v.flags & PORTABLE_VERIFIER_FRACTIONAL_GATE)) continue;",
                           "        trace_stock_result(i, &v);\n"
                           "        if (!(v.flags & PORTABLE_VERIFIER_FRACTIONAL_GATE)) continue;")
    work.mkdir()
    origin = work / "readout.c"
    origin.write_text("#define _POSIX_C_SOURCE 200809L\n#include <time.h>\n" + header
                      + "static void trace_stock_result(int, const PortableVerifierResult *);\n" + private
                      + CODE.read_text())
    path = work / "readout.so"
    command = [*recipe["commands"][-2][:-4], "-shared", str(origin), str(installed), "-Wl,-z,defs", "-lm",
               "-o", str(path)]
    subprocess.run(command, check=True, cwd=recipe["cwd"])
    return path, dict(installed_sha256=V3_SHA, two_carrier_source_sha256=SOURCE_SHA,
                      readout_source_sha256=digest(CODE.read_bytes()), helper_sha256=digest(path.read_bytes()),
                      command=command)


def values(record):
    return {field: tuple(value) if isinstance(value, ct.Array) else value
            for field, _ in record._fields_ for value in (getattr(record, field),)}


def timed(native, receiver, samples, lane, center, mode, trace=None):
    out = (Factor * 2)()
    args = (receiver.ctx, samples.ctypes.data, lane, center - 800000, center + 800000, mode, out, trace)
    start, wall = process_time_ns(), perf_counter_ns()
    count = native(*args)
    cpu, elapsed = process_time_ns()-start, perf_counter_ns()-wall
    if not 0 <= count <= len(out):
        raise ValueError("Invalid scout readout result")
    return tuple(map(tuple_factor, out[:count])), cpu, elapsed


def factor_bytes(factors):
    return b"".join(bytes(Factor(*factor)) for factor in factors)


def distribution(xs):
    if not xs:
        return None
    return dict(n=len(xs), median=median(xs), p95=quantiles(xs, n=20, method="inclusive")[-1]
                if len(xs) > 1 else xs[0], maximum=max(xs))


def summary(rows, times, pairs):
    counts, by_rank = Counter(), [{"cfo": [], "epoch": [], "held_cfo": []} for _ in range(2)]
    for lane in rows:
        released, held = ({f[0]: f for f in lane[name]} for name in ("released", "candidate"))
        counts.update(released_empty=not released, held_empty=not held,
                      held_factors_on_released_empty=len(held) if not released else 0)
        for rank, (scout, stock, block) in enumerate(zip(lane["scout"], lane["stock"], lane["block"], strict=True)):
            counts[f"preconfirmed_{rank}"] += scout["confirmation"] != 0
            counts[f"preconfirmed_early_{rank}"] += scout["confirmation"] == 2
            counts[f"stock_examined_{rank}"] += stock["examined"]
            counts[f"stock_gate_{rank}"] += bool(stock["flags"] & 2)
            counts[f"held_rolled_gate_{rank}"] += block["rolled_accepted"]
            counts[f"held_issued_{rank}"] += rank in held
            counts[f"held_issued_without_stock_{rank}"] += rank in held and rank not in released
            if rank not in released:
                continue
            counts[f"released_{rank}"] += 1
            old = released[rank]
            counts[f"scout_cfo_exact_{rank}"] += old[3] == scout["hz"]
            if block["examined"]:
                counts[f"held_contrast_pass_{rank}"] += block["exact"] - block["control"] >= .010
                counts[f"held_group_cfo_pass_{rank}"] += abs(block["group_hz"][0] - block["group_hz"][1]) <= 350.
            by_rank[rank]["cfo"].append(abs(old[3] - scout["hz"]))
            by_rank[rank]["epoch"].append(abs(math.remainder(old[1] + old[2] - scout["epoch"], 13333)))
            if rank in held:
                counts[f"held_same_rank_{rank}"] += 1
                counts[f"held_matched_{rank}"] += agree(old, held[rank])
                by_rank[rank]["held_cfo"].append(abs(old[3] - held[rank][3]))
    return dict(counts=dict(counts), errors=[{k: distribution(v) for k, v in row.items()} for row in by_rank],
                mean_native_cpu_ms={arm: mean(t[0] for t in runs)/len(rows)/1e6 for arm, runs in times.items()},
                mean_native_wall_ms={arm: mean(t[1] for t in runs)/len(rows)/1e6 for arm, runs in times.items()},
                stock_verification_ms_per_lane=mean(lane["verification_cpu_ns"] for lane in rows)/1e6,
                stock_loading_ms_per_lane=mean(lane["loading_cpu_ns"] for lane in rows)/1e6,
                continuation=dict(released=sum(before is not None for before, _ in pairs),
                                  held=sum(after is not None for _, after in pairs),
                                  changed=sum(before != after for before, after in pairs),
                                  matched=sum(before is not None and after is not None and agree(before, after)
                                              for before, after in pairs)))


def measure(rows, installed, helper, assets, repeats):
    library = ct.CDLL(str(helper))
    native = library.scout_readout_run
    native.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.c_int,
                       ct.POINTER(Factor), ct.POINTER(Trace)]
    native.restype = ct.c_int
    traces, times, pairs = [], {name: [[] for _ in range(repeats)] for name in ARMS}, []
    histories = {name: {} for name in ("release", "held_blocks")}
    with ExitStack() as stack:
        receivers = {}
        for edge in {row["edge"] for row, _ in rows}:
            asset = (assets / f"{edge}.f32").read_bytes()
            if digest(asset) != PILOT_SHA[edge]:
                raise ValueError("Pinned pilot asset changed")
            radio = Receiver(installed, np.frombuffer(asset, dtype="<f4"))
            stack.callback(radio.close)
            receivers[edge] = radio
        for repeat in range(repeats):
            for index, (row, iq) in enumerate(rows):
                center = row["target"]["rf_center_hz"] - row["target"]["lnb_lo_hz"] - row["acquisition"]["actual_if_center_hz"]
                radio = receivers[row["edge"]]
                for lane in (0, 1):
                    offset = (index + lane + repeat) % len(ARMS)
                    order = ARMS[offset:] + ARMS[:offset]
                    result = {}
                    for arm in order:
                        if arm == "release":
                            got, cpu, wall = radio.timed(iq, lane, center)
                        else:
                            mode = {"linked": 0, "free_readout": 2, "held_blocks": 3}[arm]
                            got, cpu, wall = timed(native, radio, iq, lane, center, mode)
                        result[arm] = got
                        times[arm][repeat].append((cpu, wall))
                    if factor_bytes(result["release"]) != factor_bytes(result["linked"]) or result["free_readout"]:
                        raise ValueError("The linked control or measured no-verifier ceiling changed")
                    if repeat:
                        continue
                    trace, candidate = Trace(), Trace()
                    if factor_bytes(timed(native, radio, iq, lane, center, 1, trace)[0]) != factor_bytes(result["release"]):
                        raise ValueError("Tracing changed the released verifier")
                    if timed(native, radio, iq, lane, center, 3, candidate)[0] != result["held_blocks"]:
                        raise ValueError("Tracing changed the candidate gate")
                    if list(map(values, trace.scout)) != list(map(values, candidate.scout)):
                        raise ValueError("Experimental readout changed a scout or cancellation")
                    before, after = (continuation(histories[name], row, lane, result[name])
                                     for name in ("release", "held_blocks"))
                    pairs.append((before, after))
                    traces.append(dict(key=row["key"], lane=lane, digest=row["sha256"], center_hz=center,
                                       released=result["release"], candidate=result["held_blocks"],
                                       scout=list(map(values, trace.scout)), stock=list(map(values, trace.stock)),
                                       block=list(map(values, candidate.block)), selected=[before, after],
                                       loading_cpu_ns=trace.loading_cpu_ns, verification_cpu_ns=trace.verification_cpu_ns))
    totals = {arm: [tuple(map(sum, zip(*run, strict=True))) for run in runs] for arm, runs in times.items()}
    return dict(summary=summary(traces, totals, pairs), rows=traces, repeated_native_ns=totals)


def projected_ceiling(groups):
    blob = ACQUISITION.read_bytes()
    if digest(blob) != ACQUISITION_SHA:
        raise ValueError("Archived full acquisition CPU changed")
    reference = json.loads(blob)
    outside = reference["outside_detector_cpu_s"]
    paid = sum(row["cpu_s"] for row in reference["detector_groups"].values())
    arms = groups["dense"]["summary"]["mean_native_cpu_ms"]
    floor = paid * arms["free_readout"] / arms["linked"]
    return dict(source_sha256=ACQUISITION_SHA, full_acquisition_cpu_s=outside+paid,
                full_detector_cpu_s=paid, full_outside_cpu_s=outside,
                projected_free_readout_detector_cpu_s=floor,
                projected_free_readout_complete_cpu_s=outside+floor,
                projected_verifier_cpu_saved_s=paid-floor)


def check_machine():
    cpu = sorted(os.sched_getaffinity(0))
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    ionice = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    threads = {key: os.environ.get(key) for key in THREADS}
    if cpu != [2] or nice < 15 or "prio 7" not in ionice or any(value != "1" for value in threads.values()):
        raise RuntimeError("Expected one low-priority numerical CPU")
    return dict(cpu=cpu, nice=nice, ionice=ionice, threads=threads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "installed", "archive", "assets", "weak", "binding", "bulk"):
        parser.add_argument(name, type=lambda path: Path(path).resolve())
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()
    machine = check_machine()
    helper, receipt = build(args.work, args.installed, args.archive)
    data = {label: measure(list(rows), args.installed, helper, args.assets, args.repeats) for label, rows in (
        ("weak", read_archive(args.weak, 18)), ("dense", read_physical(args.binding, args.bulk, 48)),
    )}
    print(json.dumps(dict(build=receipt, groups=data, repeats=args.repeats, machine=machine,
                          projection=projected_ceiling(data)), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
