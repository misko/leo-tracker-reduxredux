"""Compare frozen packed FFTW estimates with bounded hardware-only wisdom."""

import argparse
import ctypes as ct
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from tools.pipeline_eval.variants.experimental import receiver_benchmark, receiver_fftw_wisdom
from tools.pipeline_eval.variants.experimental.receiver_acquisition_profile import prefix_entry


def physical_prefix(binding, bulk, limit):
    case, _, inventory = prefix_entry(binding, bulk, limit)
    source = FastSegmentSource(inventory["segments"][0], stop_sequence=limit)
    receivers = tuple(source.receiver_ids)
    if receivers != (0, 1):
        raise ValueError("Expected two ordered independent receiver lanes")
    policy = FastScanPolicyV2()
    for window in source.windows():
        a, t = window.acquisition, window.target
        if not valid_window_support(
            a, window.sample_rate_hz, window.samples.shape, receivers, policy
        ):
            continue
        visit = a["global_visit"]
        yield dict(case=case, key=f"{case}:{visit}", edge=t["edge"], acquisition=a,
                   target=t, visit=visit, sha256=window.iq_sha256), window.samples


def delta(after, before):
    return {key: value - before[key] for key, value in after.items()}


def compare(rows, axes, libraries, assets, repeats):
    receiver = receiver_benchmark.Receiver
    startup = defaultdict(list)
    native_setup = defaultdict(lambda: defaultdict(int))
    before = {binary: receiver_fftw_wisdom.counters(libraries[binary])
              for binary in axes if binary in libraries}

    def create(binary, asset):
        lib = libraries.get(binary)
        initial = receiver_fftw_wisdom.counters(lib) if lib else None
        cpu, wall = process_time_ns(), perf_counter_ns()
        context = receiver(binary, asset)
        startup[str(binary)].append(dict(cpu_ns=process_time_ns() - cpu,
                                         elapsed_ns=perf_counter_ns() - wall))
        if lib:
            for key, value in delta(receiver_fftw_wisdom.counters(lib), initial).items():
                native_setup[str(binary)][key] += value
        return context

    with patch.object(receiver_benchmark, "Receiver", create):
        result = receiver_benchmark.benchmark(axes, rows, assets, repeats)
    result["context_open"] = [startup[str(binary)] for binary in axes]
    result["planner_counters"] = [dict(native_setup[str(binary)]) for binary in axes]
    result["transform_counters"] = [
        {key: value - native_setup[str(binary)][key] for key, value in
         delta(receiver_fftw_wisdom.counters(libraries[binary]), before[binary]).items()}
        if binary in libraries else {} for binary in axes
    ]
    result["input_sha256"] = receiver_benchmark.digest(
        json.dumps([row for row, _ in rows], sort_keys=True).encode()
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen", "overlay", "estimate", "wisdom", "physical", "public_panel", "assets"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--bulk", type=Path, default=Path("/srv/bulk"))
    args = parser.parse_args()
    frozen, overlay, estimate = (p.resolve() for p in (args.frozen, args.overlay, args.estimate))
    if receiver_benchmark.digest(frozen.read_bytes()) != receiver_fftw_wisdom.PACKED_SHA256:
        raise ValueError("The reference must be the frozen packed receiver")
    text = receiver_fftw_wisdom.read_wisdom(args.wisdom)
    if text is None:
        raise ValueError("The benchmark requires compatible measured wisdom")
    if estimate.samefile(overlay) or estimate.read_bytes() != overlay.read_bytes():
        raise ValueError("The instrumented comparison needs two physical copies of the overlay")
    measured = ct.CDLL(str(overlay))
    baseline = ct.CDLL(str(estimate))
    libraries = {estimate: baseline, overlay: measured}
    inputs = (
        ("physical", physical_prefix(args.physical, args.bulk, 80)),
        ("simulated", receiver_benchmark.read_simulated_prefix(args.public_panel, 40)),
    )
    outcomes = {}
    for name, generator in inputs:
        rows = list(generator)
        receiver_fftw_wisdom.configure(measured, text)
        direct = compare(rows, (frozen, overlay), libraries, args.assets, repeats=4)
        receiver_fftw_wisdom.configure(measured, text, profile=True)
        receiver_fftw_wisdom.configure(baseline, None, profile=True)
        profiled = compare(rows, (estimate, overlay), libraries, args.assets, repeats=2)
        outcomes[name] = dict(direct=direct, profiled=profiled)
    metadata = json.loads(args.wisdom.read_bytes())
    print(json.dumps(dict(
        hardware=metadata["hardware"], measure=metadata["plans"], results=outcomes,
        wisdom_sha256=receiver_benchmark.digest(text),
        overlay_sha256=receiver_benchmark.digest(overlay.read_bytes()),
    ), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
