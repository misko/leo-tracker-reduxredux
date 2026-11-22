"""Freeze exact carrier-bin memoization, separately and with resident cancellation."""

import argparse
from collections import defaultdict
import ctypes as ct
import json
from pathlib import Path
from unittest.mock import patch

import receiver_compiler_trial as compiler
from receiver_refine_parity_trial import austin_windows
from receiver_resident_cancel_trial import austin, load_binaries, paired
from tools.pipeline_eval.variants.experimental import (
    receiver_build, receiver_carrier_eligibility, receiver_phase_packed_build, receiver_resident_cancel,
)
from tools.pipeline_eval.variants.experimental.receiver_benchmark import digest, read_archive, read_simulated_prefix
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical


MODES = ("cache", "combined")


def freeze(work, assets, resident_work, resident_manifest):
    originals = load_binaries(resident_work, resident_manifest)
    work.mkdir()
    native = receiver_build.build
    phase = receiver_phase_packed_build.overlay(native)
    cached = receiver_carrier_eligibility.overlay(phase)
    combined = receiver_carrier_eligibility.overlay(receiver_resident_cancel.overlay(phase))
    builds = {}
    for name, function, profile in (
        ("cache", cached, False), ("cache-profile", cached, True), ("combined", combined, False),
    ):
        def build(output, **recipe):
            if output.name == "control.so":
                return native(output, **recipe)
            return function(output, profile=profile, **recipe)

        with patch.object(receiver_build, "build", build):
            builds[name] = compiler.build(work / name, assets, integer_fir=False)
    return dict(
        originals={name: dict(path=str(path.resolve()), sha256=digest(path.read_bytes()))
                   for name, path in originals.items()},
        builds=builds, compiler_training_source_sha256=digest(Path(compiler.__file__).read_bytes()),
    )


def load(work, manifest):
    pins = json.loads(manifest.read_bytes())
    result = {}
    for name, row in pins["originals"].items():
        path = Path(row["path"])
        if digest(path.read_bytes()) != row["sha256"]:
            raise ValueError(f"Frozen reference changed: {name}")
        result[name] = path
    for name, build in pins["builds"].items():
        path = work / name / "use.so"
        if digest(path.read_bytes()) != build["library_sha256"]:
            raise ValueError(f"Frozen candidate changed: {name}")
        result[name] = path
    return result


def cache_stats(binary):
    fn = ct.CDLL(str(binary.resolve())).experimental_carrier_eligibility_stats
    fn.argtypes, fn.restype = [ct.POINTER(ct.c_uint64), ct.c_int], None
    values = (ct.c_uint64 * 2)()
    fn(values, 1)
    return dict(hits=values[0], rebuilds=values[1])


def timing(rows, assets, base, candidate, repeats=5):
    cache_stats(candidate)
    result = paired(rows, assets, (base, candidate), repeats=repeats)
    return result | dict(eligibility=cache_stats(candidate))


def physical(work, manifest, assets, binding, prospective, weak):
    binaries = load(work, manifest)
    chronological = list(read_physical(binding, Path("/srv/bulk"), 128))
    indexed = list(read_archive(prospective, 80))
    weak_rows = list(read_archive(weak, 18))
    mixed = []
    for index, (row, iq) in enumerate(weak_rows):
        offset = (-1 if index % 2 else 1) * 50_000
        acq = row["acquisition"]
        mixed.append((dict(row, acquisition=dict(acq, actual_if_center_hz=acq["actual_if_center_hz"] + offset)), iq))
    result = dict(
        profile=timing(indexed, assets, binaries["reference-profile"], binaries["cache-profile"], repeats=2),
        mixed_center=timing(mixed, assets, binaries["reference"], binaries["cache"], repeats=2),
    )
    for name in MODES:
        result[name] = {
            group: timing(rows, assets, binaries["reference"], binaries[name])
            for group, rows in (("chronological", chronological), ("prospective", indexed), ("weak", weak_rows))
        }
    return result


def offsite(work, manifest, assets, panel, archive, source_audit, wide_reference):
    binaries = load(work, manifest)
    groups = defaultdict(list)
    for row, iq in read_simulated_prefix(panel, 40):
        groups[row["case"]].append((row, iq))
    samples = list(austin_windows(archive, source_audit, wide_reference))
    results = {}
    for name in MODES:
        sims = {site: timing(rows, assets, binaries["reference"], binaries[name])
                for site, rows in groups.items()}
        cache_stats(binaries[name])
        field = austin(samples, assets, (binaries["reference"], binaries[name]))
        results[name] = dict(simulations=sims, Austin=field, Austin_eligibility=cache_stats(binaries[name]))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (freeze, ("work", "assets", "resident_work", "resident_manifest")),
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
