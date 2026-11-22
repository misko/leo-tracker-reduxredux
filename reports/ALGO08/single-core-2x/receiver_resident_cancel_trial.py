"""Freeze the resident cancellation PGO build and compare saved native calls."""

import argparse
from collections import defaultdict
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from struct import pack
from unittest.mock import patch

import numpy as np

import receiver_compiler_trial as compiler
from receiver_refine_parity_trial import austin_windows
from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_phase_packed_build, receiver_resident_cancel,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Receiver, benchmark, digest, read_archive, read_simulated_prefix,
)
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical


LEAD_SHA = "dd2d83a8cc865b156115922e057823300e269c2fcb65f525f81e6fa620ed1a20"


def freeze(work, assets, reference):
    if digest(reference.read_bytes()) != LEAD_SHA:
        raise ValueError("Unexpected floating/FIR packed phase lead")
    work.mkdir()
    native = receiver_build.build
    phase = receiver_phase_packed_build.overlay(native)
    resident = receiver_resident_cancel.overlay(phase)
    builds = {}
    for name, function, profile in (
        ("resident", resident, False), ("reference-profile", phase, True), ("resident-profile", resident, True),
    ):
        def build(output, **recipe):
            if output.name == "control.so":
                return native(output, **recipe)
            return function(output, profile=profile, **recipe)

        with patch.object(receiver_build, "build", build):
            builds[name] = compiler.build(work / name, assets, integer_fir=False)
    return dict(
        reference=dict(path=str(reference.resolve()), sha256=LEAD_SHA),
        builds=builds, compiler_training_source_sha256=digest(Path(compiler.__file__).read_bytes()),
    )


def load_binaries(work, manifest):
    manifest = json.loads(manifest.read_bytes())
    lead = manifest["reference"]
    if lead["sha256"] != LEAD_SHA or digest(Path(lead["path"]).read_bytes()) != LEAD_SHA:
        raise ValueError("Frozen lead changed")
    bins = {"reference": Path(lead["path"])}
    for name in ("resident", "reference-profile", "resident-profile"):
        path = work / name / "use.so"
        if digest(path.read_bytes()) != manifest["builds"][name]["library_sha256"]:
            raise ValueError(f"Frozen receiver changed: {name}")
        bins[name] = path
    return bins


def summarize(times):
    return dict(median_cpu_s=[median(column) for column in zip(*times, strict=True)],
                median_paired_saved=median(1 - b / a for a, b in times))


def paired(rows, assets, binaries, repeats=5):
    result = benchmark(binaries, rows, assets, repeats=repeats)
    return result | summarize(result["total_cpu_s"]) | dict(
        iq_sha256=digest(json.dumps([row["sha256"] for row, _ in rows]).encode()))


def physical(work, manifest, assets, binding, prospective, weak):
    bins = load_binaries(work, manifest)
    chronological = list(read_physical(binding, Path("/srv/bulk"), 128))
    snapshots = list(read_archive(prospective, 80))
    weak_rows = list(read_archive(weak, 18))
    measured = bins["reference"], bins["resident"]
    mixed = []
    # Keep all stored waveforms but use a nonzero symmetric retune displacement per window.
    for index, (row, iq) in enumerate(weak_rows):
        offset = (-1 if index % 2 else 1) * 50_000
        acq = row["acquisition"]
        mixed.append((dict(row, acquisition=dict(acq, actual_if_center_hz=acq["actual_if_center_hz"] + offset)), iq))
    return dict(
        chronological=paired(chronological, assets, measured),
        prospective=paired(snapshots, assets, measured),
        weak=paired(weak_rows, assets, measured),
        mixed_center_fallback=paired(mixed, assets, measured, repeats=2),
        prospective_profile=paired(snapshots, assets, (bins["reference-profile"], bins["resident-profile"]),
                                   repeats=2),
    )


def austin(rows, assets, binaries):
    output = {}
    with ExitStack() as stack:
        detectors = {}
        for edge in {row[1] for row in rows}:
            template = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            detectors[edge] = [Receiver(path, template) for path in binaries]
            for detector in detectors[edge]:
                stack.callback(detector.close)
        for group in ("physical", "null"):
            windows = [row[1:] for row in rows if row[0] == group]
            changes = set()
            times, measured = [], []
            for repeat in range(9):
                cpu, observed = [0, 0], []
                for i, (edge, start, iq_digest, iq) in enumerate(windows):
                    first = (i + repeat) % 2
                    rows_by_arm = [None, None]
                    for arm in (first, 1 - first):
                        rows_by_arm[arm], nanos, _ = detectors[edge][arm].timed(iq, 0, 0)
                        cpu[arm] += nanos
                    before, after = [b"".join(pack("<ii4d", *f) for f in arm) for arm in rows_by_arm]
                    if before != after:
                        changes.add((edge, start))
                    observed.append(dict(edge=edge, start_ms=start, iq_sha256=iq_digest,
                                         factors=rows_by_arm, factor_digests=[digest(before), digest(after)]))
                times.append([elapsed / 1e9 for elapsed in cpu])
                measured.append(observed)
            if any(receipt != measured[0] for receipt in measured[1:]):
                raise ValueError("Repeated Austin trial returned different measurements")
            output[group] = dict(total_cpu_s=times, changed=sorted(changes), rows=measured[0], **summarize(times))
    return output


def offsite(work, manifest, assets, panel, archive, source_audit, wide_reference):
    bins = load_binaries(work, manifest)
    measured = bins["reference"], bins["resident"]
    groups = defaultdict(list)
    for row, iq in read_simulated_prefix(panel, 40):
        groups[row["case"]].append((row, iq))
    simulations = {name: paired(rows, assets, measured) for name, rows in groups.items()}
    field = austin(list(austin_windows(archive, source_audit, wide_reference)), assets, measured)
    return dict(simulations=simulations, Austin=field)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (freeze, ("work", "assets", "reference")),
        (physical, ("work", "manifest", "assets", "binding", "prospective", "weak")),
        (offsite, ("work", "manifest", "assets", "panel", "archive", "source_audit", "wide_reference")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for field in fields:
            command.add_argument(field, type=Path)
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
