"""Freeze two guarded phase-verifier PGO builds and score small saved slices."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from unittest.mock import patch

import numpy as np

import receiver_compiler_trial as compiler
from receiver_refine_parity_trial import austin_windows
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental import receiver_build, receiver_phase_packed_build
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Receiver, digest, read_archive, read_simulated_prefix,
)
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_phase_trial import phase_stats


REFERENCE_PINS = {
    "float": "cc06336a86d06b356d0b7394c55a10e6e5d81471fbe2215a4c88be405f2762b8",
    "q15": "64432addf6997f1ebd45daa8e73fd8337d0ab6abbeade254f611055542b71ea3",
}
REFERENCE = "float"
PHASE_MODES = ("float-phase", "q15-phase")
ARMS = (*REFERENCE_PINS, *PHASE_MODES)


def freeze(work, assets, float_library, q15_library):
    base = dict(zip(REFERENCE_PINS, (float_library.resolve(), q15_library.resolve()), strict=True))
    if {name: digest(path.read_bytes()) for name, path in base.items()} != REFERENCE_PINS:
        raise ValueError("Full-scan PGO controls differ from their reviewed builds")
    work.mkdir()
    native = receiver_build.build
    combined = receiver_phase_packed_build.overlay(native)

    def build(output, **recipe):
        function = native if output.name == "control.so" else combined
        return function(output, **recipe)

    receipts = {}
    with patch.object(receiver_build, "build", build):
        for name in PHASE_MODES:
            output = work / name
            receipts[name] = compiler.build(output, assets, integer_fir=(name == "q15-phase"))
            base[name] = (output / "use.so").resolve()
    pins = REFERENCE_PINS | {name: row["library_sha256"] for name, row in receipts.items()}
    source = Path(compiler.__file__).read_bytes()
    return dict(
        arms={name: dict(path=str(path), sha256=pins[name]) for name, path in base.items()},
        primary_candidate="q15-phase", compiler_training_source_sha256=digest(source),
        compiler_builds=receipts,
    )


def libraries(manifest):
    spec = json.loads(manifest.read_bytes())
    if set(spec["arms"]) != set(ARMS) or spec["primary_candidate"] != "q15-phase":
        raise ValueError("Unexpected frozen native arms")
    if {name: spec["arms"][name]["sha256"] for name in REFERENCE_PINS} != REFERENCE_PINS:
        raise ValueError("Frozen manifest changed its full-scan PGO controls")
    files = {}
    for name in ARMS:
        row = spec["arms"][name]
        path = Path(row["path"])
        if digest(path.read_bytes()) != row["sha256"]:
            raise ValueError("Receiver bytes differ from frozen composition")
        files[name] = path
    return files


def visits(rows):
    for row, samples in rows:
        target, acquisition = row["target"], row["acquisition"]
        rf = acquisition["actual_if_center_hz"] + target["lnb_lo_hz"]
        center = target["rf_center_hz"] - rf
        for lane in (0, 1):
            metadata = dict(receiver_id=lane, channel=target["channel"], actual_rf_hz=rf,
                            valid_start_counter=acquisition["sample_start"])
            yield row["key"], row["case"], row["edge"], row["sha256"], lane, center, metadata, samples


def ordered(factors):
    return tuple(row[:4] for row in factors)


def selected(factors, selection):
    return None if selection is None or selection[1] is None else factors[selection[1]][:4]


def compare(old, new, old_selection, new_selection, counts, maximum):
    old_values, new_values = ordered(old), ordered(new)
    changed = old_values != new_values
    counts["native_identity_changed_lanes"] += changed
    counts["score_only_changed_lanes"] += not changed and old != new
    counts["factor_counts_changed_lanes"] += len(old) != len(new)
    counts["continuation_state_changed_lanes"] += old_selection != new_selection
    before, after = selected(old, old_selection), selected(new, new_selection)
    counts["selected_measurements_changed_lanes"] += before != after
    counts["selected_added"] += before is None and after is not None
    counts["selected_lost"] += before is not None and after is None
    counts["selected_replaced"] += before is not None and after is not None and before != after
    direct = {value: factor for value, factor in zip(old_values, old, strict=True)}
    for value, factor in zip(new_values, new, strict=True):
        if value in direct:
            reference = direct[value]
            counts["matched_factors"] += 1
            counts["ref_exact_gate_class_changed"] += (reference[4] - reference[5] >= .025) != (
                factor[4] - factor[5] >= .025)
            counts["ref_strong_margin_class_changed"] += (reference[4] - reference[5] >= .1) != (
                factor[4] - factor[5] >= .1)
            for i, (a, b) in enumerate(zip(reference[4:], factor[4:], strict=True)):
                maximum[i] = max(maximum[i], abs(a - b))
            maximum[2] = max(maximum[2], abs((reference[4] - reference[5]) - (factor[4] - factor[5])))
    return changed or before != after


def benchmark(rows, binaries, assets, repeats):
    time, statistics = [], []
    changes = {name: [] for name in ARMS[1:]}
    ranks, continued = {name: Counter() for name in ARMS}, {name: Counter() for name in ARMS}
    with ExitStack() as stack:
        receivers = {}
        for edge in {row[2] for row in rows}:
            asset = assets / f"{edge}.f32"
            if digest(asset.read_bytes()) != PINS[asset.name]:
                raise ValueError("Unexpected pinned pilot asset")
            template = np.fromfile(asset, dtype="<f4")
            for name, binary in binaries.items():
                detector = Receiver(binary, template)
                receivers[edge, name] = detector
                stack.callback(detector.close)
        for repeat in range(repeats):
            history = defaultdict(Continuation)
            cpu = dict.fromkeys(ARMS, 0)
            counts = {name: Counter() for name in ARMS[1:]}
            maxima = {name: [0., 0., 0.] for name in ARMS[1:]}
            for name in PHASE_MODES:
                phase_stats(binaries[name])
            for index, (key, case, edge, _, lane, center, metadata, samples) in enumerate(rows):
                offset = (index + repeat) % len(ARMS)
                order = ARMS[offset:] + ARMS[:offset]
                if repeat % 2:
                    order = order[::-1]
                factors, selections = {}, {}
                for name in order:
                    detector = receivers[edge, name]
                    factors[name], nanos, _ = detector.timed(samples, lane, center)
                    cpu[name] += nanos
                    state = history[case, name].select(dict(
                        metadata, candidates=[detector.criteria(*factor) for factor in factors[name]],
                    )) if metadata is not None else None
                    selections[name] = state
                    if repeat == 0:
                        ranks[name].update(factor[0] for factor in factors[name])
                        measured = selected(factors[name], state)
                        if measured is not None:
                            continued[name][measured[0]] += 1
                for name in ARMS[1:]:
                    if compare(factors[REFERENCE], factors[name], selections[REFERENCE], selections[name],
                               counts[name], maxima[name]) and repeat == 0:
                        changes[name].append(dict(
                            key=key, lane=lane, reference=factors[REFERENCE], tested=factors[name],
                            reference_continuation=selections[REFERENCE], tested_continuation=selections[name],
                        ))
            time.append({name: value / 1e9 for name, value in cpu.items()})
            statistics.append(dict(
                comparative=counts, max_exact_control_margin_deltas=maxima,
                phase={name: phase_stats(binaries[name]) for name in PHASE_MODES},
            ))
    if any(row != statistics[0] for row in statistics[1:]):
        raise ValueError("Scientific results differ between matched CPU repeats")
    return dict(
        lanes=len(rows), repeats=repeats, total_cpu_s=time,
        median_total_cpu_s={name: median(row[name] for row in time) for name in ARMS},
        median_paired_cpu_saved={name: median(1 - row[name] / row[REFERENCE] for row in time)
                                 for name in ARMS[1:]},
        iq_index_sha256=digest(json.dumps([row[:5] for row in rows]).encode()),
        ranks=ranks, continuation_selected=continued, changes=changes, **statistics[0],
    )


def physical(manifest, assets, binding, weak):
    binaries = libraries(manifest)
    return {
        "chronological": benchmark(list(visits(read_physical(binding, Path("/srv/bulk"), 128))),
                                   binaries, assets, 5),
        "weak": benchmark(list(visits(read_archive(weak, 18))), binaries, assets, 5),
    }


def offsite(manifest, assets, panel, archive, source_audit, wide_reference):
    binaries = libraries(manifest)
    groups = defaultdict(list)
    for case, edge, start, receipt, samples in austin_windows(archive, source_audit, wide_reference):
        key = f"Austin:{case}:{edge}:{start}"
        groups[f"Austin-{case}"].append((key, case, edge, receipt, 0, 0., None, samples))
    for row, samples in read_simulated_prefix(panel, 40):
        groups[row["case"]].extend(visits([(row, samples)]))
    return {name: benchmark(rows, binaries, assets, 9 if name.startswith("Austin") else 5)
            for name, rows in groups.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, arguments in (
        (freeze, ("work", "assets", "float_library", "q15_library")),
        (physical, ("manifest", "assets", "binding", "weak")),
        (offsite, ("manifest", "assets", "panel", "archive", "source_audit", "wide_reference")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for argument in arguments:
            command.add_argument(argument, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
