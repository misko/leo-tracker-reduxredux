"""Compare two ALGO08 factor libraries on a bounded, indexed I/Q archive."""

import argparse
import ctypes as ct
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import process_time_ns, perf_counter_ns
from zipfile import ZipFile

import numpy as np

from ..carrier_continuation import Continuation


class Factor(ct.Structure):
    _fields_ = [
        ("rank", ct.c_int), ("integer", ct.c_int), ("offset", ct.c_double),
        ("hz", ct.c_double), ("exact", ct.c_double), ("control", ct.c_double),
    ]


class ProfileStat(ct.Structure):
    _fields_ = [("calls", ct.c_uint64), ("ns", ct.c_uint64)]


STAGES = (
    "measure", "timing", "input", "decimate", "modes", "time_search", "carrier_search",
    "refine", "gate", "cancel", "verify_load", "verify",
)


class Receiver:
    def __init__(self, binary, asset):
        self.lib = ct.CDLL(str(binary.resolve()))
        self.lib.two_carrier_create.argtypes = [ct.c_void_p]
        self.lib.two_carrier_create.restype = ct.c_void_p
        self.lib.two_carrier_free.argtypes = [ct.c_void_p]
        self.lib.two_carrier_free.restype = None
        self.run = self.lib.cancellation_factors
        self.run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double,
                             ct.POINTER(Factor)]
        self.run.restype = ct.c_int
        self.ctx = self.lib.two_carrier_create(asset.ctypes.data)
        if not self.ctx:
            raise ValueError("receiver creation failed")

    def close(self):
        self.lib.two_carrier_free(self.ctx)

    def profile(self):
        read = getattr(self.lib, "experimental_receiver_profile_read", None)
        if read is None:
            return None
        stats = (ProfileStat * len(STAGES))()
        read.argtypes = [ct.POINTER(ProfileStat), ct.c_uint]
        read.restype = ct.c_uint
        if read(stats, len(stats)) != len(STAGES):
            raise ValueError("receiver profiling interface disagrees with benchmark")
        return {name: {"calls": stat.calls, "cpu_s": stat.ns / 1e9}
                for name, stat in zip(STAGES, stats, strict=True)}

    def reset_profile(self):
        reset = getattr(self.lib, "experimental_receiver_profile_reset", None)
        if reset is not None:
            reset.argtypes = []
            reset.restype = None
            reset()

    @staticmethod
    def criteria(rank, integer, offset, hz, exact, control):
        return {"candidate_rank": rank, "fractional_tracking_cfo_hz": hz,
                "fractional_margin": exact - control}

    def timed(self, samples, lane, center):
        out = (Factor * 2)()
        args = (self.ctx, samples.ctypes.data, lane, center - 800000, center + 800000, out)
        wall, cpu = perf_counter_ns(), process_time_ns()
        count = self.run(*args)
        cpu, wall = process_time_ns() - cpu, perf_counter_ns() - wall
        if not 0 <= count <= 2:
            raise ValueError(f"invalid receiver factor count {count}")
        return tuple(tuple(getattr(row, key) for key, _ in Factor._fields_)
                     for row in out[:count]), cpu, wall


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_archive(path, limit):
    with ZipFile(path) as archive:
        entries = json.loads(archive.read("index.json"))["visits"]
        chosen = sorted(entries, key=lambda row: (row["case"], row["visit"]))[:limit]
        for row in chosen:
            file = archive.getinfo(row["file"])
            if file.file_size != 1_600_000 or row["shape"] != [200000, 2, 2]:
                raise ValueError("archive contains invalid I/Q shape")
            raw = archive.read(file)
            if f"sha256:{digest(raw)}" != row["sha256"]:
                raise ValueError(f"archive I/Q digest mismatch for {row['key']}")
            yield row, np.frombuffer(raw, dtype="<i2").reshape(row["shape"])


def read_simulated_prefix(panel, limit):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource, safe_id

    jobs = json.loads(panel.read_bytes())["jobs"]
    recordings = sorted({safe_id(job["recording"]) for job in jobs})
    if len(recordings) != 2 or not 1 <= limit <= 40:
        raise ValueError("expected two public simulations and a prefix of at most 40 visits each")
    for name in recordings:
        _, _, inventory = FastScanStore(panel.parent).inventory(panel.parent / name, verify_windows=False)
        segment = inventory["segments"][0]
        if segment["windows"] < limit:
            raise ValueError("requested prefix spans multiple sealed segments")
        source = FastSegmentSource(segment, stop_sequence=limit)
        receivers = tuple(source.receiver_ids)
        if receivers != (0, 1):
            raise ValueError("expected two ordered independent receiver lanes")
        policy = FastScanPolicyV2()
        for window in source.windows():
            a, t = window.acquisition, window.target
            if not valid_window_support(a, window.sample_rate_hz, window.samples.shape, receivers, policy):
                continue
            visit = a["global_visit"]
            yield dict(case=name, key=f"{name}:{visit}", edge=t["edge"], acquisition=a,
                       target=t, visit=visit, sha256=window.iq_sha256), window.samples


def benchmark(binaries, rows, assets, repeats):
    timings, walls, distributions = {}, {}, {}
    ranks, continuation_kept = [Counter(), Counter()], [Counter(), Counter()]
    changed, selection_changed, ordered, max_delta = set(), set(), [[], []], [0.0] * 4
    with ExitStack() as closer:
        receivers = {}
        edges = sorted({row["edge"] for row, _ in rows})
        for edge in edges:
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            if asset.shape != (133413,):
                raise ValueError("invalid receiver pilot asset")
            for arm, binary in enumerate(binaries):
                receiver = Receiver(binary, asset)
                closer.callback(receiver.close)
                receivers[edge, arm] = receiver
        for arm in (0, 1):
            receivers[edges[0], arm].reset_profile()
        for repeat in range(repeats):
            history = {}
            for index, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for lane in (0, 1):
                    observations, selections = {}, {}
                    first = (index + lane + repeat) % 2
                    for arm in (first, 1 - first):
                        receiver = receivers[row["edge"], arm]
                        factors, cpu, wall = receiver.timed(samples, lane, center)
                        case = (arm, row["case"])
                        if case not in history:
                            history[case] = Continuation()
                        probe = dict(receiver_id=lane, channel=target["channel"],
                                     actual_rf_hz=acq["actual_if_center_hz"] + target["lnb_lo_hz"],
                                     valid_start_counter=acq["sample_start"],
                                     candidates=[receiver.criteria(*f) for f in factors])
                        selections[arm] = history[case].select(probe)
                        observations[arm] = factors
                        timings.setdefault((repeat, arm), []).append(cpu)
                        walls.setdefault((repeat, arm), []).append(wall)
                        if not repeat:
                            distributions.setdefault(arm, Counter())[len(factors)] += 1
                            ordered[arm].append((row["key"], lane, factors, selections[arm]))
                            ranks[arm].update(f[0] for f in factors)
                            keep = selections[arm][1]
                            if keep is not None:
                                continuation_kept[arm][factors[keep][0]] += 1
                    if observations[0] != observations[1]:
                        changed.add((row["key"], lane))
                    if selections[0] != selections[1]:
                        selection_changed.add((row["key"], lane))
                    for base, candidate in zip(observations[0], observations[1]):
                        if base[:2] == candidate[:2]:
                            for col, (a, b) in enumerate(zip(base[2:], candidate[2:])):
                                max_delta[col] = max(max_delta[col], abs(a - b))
        profiles = [receivers[edges[0], arm].profile() for arm in (0, 1)]
    return dict(
        lane_calls=2 * len(rows), repeats=repeats, changed=sorted(changed),
        changed_continuation=sorted(selection_changed), max_field_deltas=max_delta,
        factor_histograms=[dict(distributions[arm]) for arm in (0, 1)],
        ranks=ranks, continuation_kept=continuation_kept,
        factor_digests=[digest(json.dumps(data, sort_keys=True).encode()) for data in ordered],
        median_cpu_ms=[median(timings[0, arm]) / 1e6 for arm in (0, 1)],
        total_cpu_s=[[sum(timings[k, arm]) / 1e9 for arm in (0, 1)] for k in range(repeats)],
        total_wall_s=[[sum(walls[k, arm]) / 1e9 for arm in (0, 1)] for k in range(repeats)],
        profiles=profiles,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--visits", type=int, default=80)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--simulated-panel", action="store_true",
                        help="read the requested prefix of each public simulation in the panel")
    args = parser.parse_args()
    if not 1 <= args.visits <= 128 or not 1 <= args.repeats <= 5:
        parser.error("this benchmark is limited to 128 visits and five repetitions")
    reader = read_simulated_prefix if args.simulated_panel else read_archive
    rows = list(reader(args.archive, args.visits))
    if not rows:
        parser.error("archive has no indexed visits")
    binaries = (args.oracle, args.candidate)
    result = benchmark(binaries, rows, args.assets, args.repeats)
    result["binaries_sha256"] = [digest(path.read_bytes()) for path in binaries]
    result["input_sha256"] = digest(json.dumps([row for row, _ in rows], sort_keys=True).encode())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
