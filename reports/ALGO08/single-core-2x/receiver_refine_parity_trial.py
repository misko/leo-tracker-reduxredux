"""Compare the exact parity-pruning receiver on saved Gauss and Austin I/Q."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
import gzip
import json
from pathlib import Path
from statistics import median
from struct import pack

import numpy as np

from austin_receiver_trial import WIDE_REFERENCE_SHA256
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification import austin_waveform as wave
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Receiver, benchmark, digest, read_archive,
)


def parity_counters(binary):
    library = ct.CDLL(str(binary.resolve()))
    reset = library.experimental_receiver_parity_reset
    reset.argtypes, reset.restype = [], None
    read = library.experimental_receiver_parity_read
    read.argtypes, read.restype = [ct.POINTER(ct.c_uint64)], None

    def counts():
        rows = (ct.c_uint64 * 2)()
        read(rows)
        return dict(attempted=rows[0], pruned=rows[1])

    reset()
    return counts


def austin_windows(archive, source_audit, wide_reference):
    reference = wide_reference.read_bytes()
    if digest(reference) != WIDE_REFERENCE_SHA256:
        raise ValueError("Unexpected archived field input receipt")
    rows = [json.loads(line) for line in gzip.decompress(reference).splitlines()]
    expected = {(r["edge"], r["panel"], r["start_ms"]): r["iq_sha256"] for r in rows
                if r["template"] == "exact"}
    raw, _, authority = wave.archive(archive, source_audit)
    for edge in wave.EDGE_HZ:
        signal = wave.extract_edge(raw, authority["actual_center_hz"], edge)
        for start in (0, 20):
            index = start * wave.RATE // 1000
            observed = signal[index:index + wave.DWELL_SAMPLES]
            null = wave.phase_null(observed, wave.BASE_SEED + start)
            for panel, data in (("physical", observed), ("null", null)):
                iq, _ = wave.ci16(data)
                value = digest(iq.tobytes())
                documented_panel = "phase-null" if panel == "null" else panel
                if value != expected[edge, documented_panel, start] or iq.shape != (200000, 1, 2):
                    raise ValueError("Measured field input differs from its pinned waveform")
                samples = np.zeros((200000, 2, 2), dtype="<i2")
                samples[:, :1] = iq
                yield panel, edge, start, value, samples


def austin_benchmark(binaries, panels, assets, repeats):
    result = {}
    with ExitStack() as stack:
        receivers = {}
        for edge in wave.EDGE_HZ:
            asset = assets / (edge + ".f32")
            if digest(asset.read_bytes()) != PINS[asset.name]:
                raise ValueError("Unexpected pilot asset")
            pilot = np.fromfile(asset, dtype="<f4")
            for arm, binary in enumerate(binaries):
                receiver = Receiver(binary, pilot)
                stack.callback(receiver.close)
                receivers[edge, arm] = receiver
        for panel in ("physical", "null"):
            windows = [(edge, start, value, samples) for group, edge, start, value, samples in panels
                       if group == panel]
            read_counts = parity_counters(binaries[1])
            times, changed = [], set()
            ranks, inputs = Counter(), {}
            for repeat in range(repeats):
                elapsed = [0, 0]
                for index, (edge, start, value, samples) in enumerate(windows):
                    first, factors = (repeat + index) % 2, {}
                    for arm in (first, 1 - first):
                        rows, cpu, _ = receivers[edge, arm].timed(samples, 0, 0.)
                        elapsed[arm] += cpu
                        factors[arm] = b"".join(pack("<ii4d", *row) for row in rows)
                        if arm == repeat == 0:
                            ranks.update(row[0] for row in rows)
                    key = f"{edge}:{start}"
                    inputs[key] = value
                    if factors[0] != factors[1]:
                        changed.add(key)
                times.append([value / 1e9 for value in elapsed])
            result[panel] = dict(
                total_cpu_s=times, median_total_cpu_s=[median(col) for col in zip(*times, strict=True)],
                old_ranks=ranks, changed_lanes=sorted(changed), counters=read_counts(), input_sha256=inputs,
            )
    return result


def run(reference, candidate, profile_reference, profile_candidate, assets,
        prospective, weak, archive, source_audit, wide_reference):
    binaries, profiled = (reference, candidate), (profile_reference, profile_candidate)
    output = dict(binaries_sha256=[digest(path.read_bytes()) for path in binaries],
                  profiled_sha256=[digest(path.read_bytes()) for path in profiled])
    for name, archive_path, limit in (("prospective", prospective, 80), ("weak", weak, 18)):
        rows = list(read_archive(archive_path, limit))
        read_counts = parity_counters(candidate)
        result = benchmark(binaries, rows, assets, repeats=5)
        result["counters"] = read_counts()
        result["median_total_cpu_s"] = [median(col) for col in zip(*result["total_cpu_s"], strict=True)]
        result["input_sha256"] = digest(json.dumps([row for row, _ in rows], sort_keys=True).encode())
        if name == "prospective":
            counts = parity_counters(profile_candidate)
            result["profile"] = benchmark(profiled, rows, assets, repeats=2)
            result["profile"]["counters"] = counts()
        output[name] = result
    output["Austin"] = austin_benchmark(
        binaries, list(austin_windows(archive, source_audit, wide_reference)), assets, repeats=9,
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("reference", "candidate", "profile_reference", "profile_candidate", "assets",
                  "prospective", "weak", "archive", "source_audit", "wide_reference"):
        parser.add_argument(field, type=Path)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, sort_keys=True, allow_nan=False))
