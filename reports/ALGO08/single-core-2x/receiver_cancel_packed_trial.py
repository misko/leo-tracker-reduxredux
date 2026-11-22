"""Replace one c803 receiver object and time exact signed cancellation."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from struct import pack
import subprocess
import sys
from zipfile import ZipFile

import numpy as np

import receiver_mixer_profile_trial as mixer_profile
from austin_receiver_trial import score
from receiver_refine_parity_trial import austin_windows
from receiver_resident_cancel_trial import paired
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification import austin_waveform as wave
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental import receiver_build, receiver_cancel_packed
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest, read_archive


REFERENCE_SHA = "d44c60320320be8281ed6e71285f8cb50cc0e204df9fa1eef53d36c514e51128"
PROFILE_SHA = "b7b59245564f215482db1cdaa23ada2973bfe7e7c9536f4325bd5b80079ecc32"


def assemble(work, build, expected, assets):
    work.mkdir()
    pinned = receiver_build.PINNED
    recipe = json.loads((pinned / "build.json").read_bytes())
    first_source = next(i for i, value in enumerate(recipe["args"]) if value.endswith(".c"))
    source_paths = [Path(value) for value in recipe["args"][first_source:] if value.endswith(".c")]
    objects = [build / "objects" / source.with_suffix(".o").name for source in source_paths]
    if expected == PROFILE_SHA:
        objects.append(build / "objects/receiver_profile.o")
    object_paths = {path.name: path for path in objects}
    original = build / "use.so"

    def link(output, object_map, feedback=()):
        subprocess.run([
            recipe["cc"], *feedback, "-shared", "-Wl,--gc-sections", *object_map.values(),
            "-lfftw3f", "-pthread", "-lm", "-o", output,
        ], check=True)

    relinked = work / "reference.so"
    link(relinked, object_paths)
    if digest(relinked.read_bytes()) != expected or digest(original.read_bytes()) != expected:
        raise ValueError("The available objects did not reproduce the pinned receiver")
    compiled_source = object_paths["pilot_cancel.o"].with_suffix(".c")
    source = work / "pilot_cancel.c"
    source.write_text(receiver_cancel_packed.overlay(compiled_source.read_text()))
    object_paths["pilot_cancel.o"] = source.with_suffix(".o")
    profiles = work / "profiles"
    profiles.mkdir()
    compile_flags = [flag for flag in recipe["args"][:first_source]
                     if flag not in ("-shared", "-Wl,--gc-sections")]
    for mode in ("generate", "use"):
        binary = work / f"{mode}.so"
        feedback = [f"-fprofile-{mode}={profiles}", "-fno-profile-values"]
        if mode == "use":
            feedback += ["-Werror=missing-profile", "-Werror=coverage-mismatch"]
        subprocess.run([
            recipe["cc"], *feedback, *compile_flags, "-I", pinned / "tools/pipeline_eval/variants",
            "-I", receiver_build.HERE, "-c", source, "-o", object_paths["pilot_cancel.o"],
        ], cwd=pinned, check=True)
        link(binary, object_paths, feedback)
        if mode == "generate":
            process = subprocess.run(
                [sys.executable, mixer_profile.__file__, "train", binary, assets],
                stdout=subprocess.PIPE, text=True, check=True,
            )
            training = json.loads(process.stdout)
    return {
        "reference_sha256": expected,
        "reference_source_sha256": digest(compiled_source.read_bytes()),
        "candidate_sha256": digest(binary.read_bytes()),
        "training": training,
    }


def trial(work, builds, archive, assets):
    work.mkdir()
    receipts = {}
    variants = (("candidate", REFERENCE_SHA), ("candidate-profile", PROFILE_SHA))
    for variant, expected in variants:
        receipts[variant] = assemble(work / variant, builds / variant, expected, assets)
    rows = list(read_archive(archive, 18))
    if len(rows) != 18:
        raise ValueError("Expected the existing 18-visit weak-carrier sample")
    native = {}
    for variant, _ in variants:
        target = work / variant
        native[variant] = paired(rows, assets, (target / "reference.so", target / "use.so"), repeats=5)
    return {"builds": receipts, "native": native}


def offsite(work, frozen, archive, source_audit, wide_reference, assets):
    expected = json.loads(frozen.read_bytes())["builds"]["candidate"]
    paths = work / "candidate/reference.so", work / "candidate/use.so"
    pins = [digest(path.read_bytes()) for path in paths]
    if pins != [REFERENCE_SHA, expected["candidate_sha256"]]:
        raise ValueError("The Austin trial requires the exact already-measured candidate")
    windows = list(austin_windows(archive, source_audit, wide_reference))
    measured = []
    with ExitStack() as stack:
        radios = {}
        for edge in wave.EDGE_HZ:
            asset = assets / f"{edge}.f32"
            if digest(asset.read_bytes()) != PINS[asset.name]:
                raise ValueError("Unexpected pilot asset")
            template = np.fromfile(asset, dtype="<f4")
            pair = tuple(Receiver(path, template) for path in paths)
            radios[edge] = pair
            for receiver in pair:
                stack.callback(receiver.close)
        for test in ("resident", "nonzero-fallback"):
            history = [{panel: Continuation() for panel in ("physical", "null")} for _ in paths]
            for index, (panel, edge, start, authority, samples) in enumerate(windows):
                center = 0. if test == "resident" else (-50_000. if edge == "lower" else 50_000.)
                first = (index + (test != "resident")) % 2
                results = [None, None]
                for arm in (first, 1 - first):
                    receiver = radios[edge][arm]
                    factors, cpu, _ = receiver.timed(samples, 0, center)
                    selected = history[arm][panel].select(dict(
                        receiver_id=0, channel=0, actual_rf_hz=wave.EDGE_HZ[edge],
                        valid_start_counter=start * wave.RATE // 1000,
                        candidates=[receiver.criteria(*factor) for factor in factors],
                    ))
                    factor_bytes = b"".join(pack("<ii4d", *factor) for factor in factors)
                    results[arm] = dict(factors=factors, ordered_factor_sha256=digest(factor_bytes),
                                        continuation=selected, native_cpu_ns=cpu)
                measured.append(dict(test=test, panel=panel, edge=edge, start_ms=start, center_hz=center,
                                     iq_sha256=authority, arms=results))
    # Consult the source's relative timing marks after all native calls finish.
    with ZipFile(archive) as source:
        frame_times = source.read(f"{wave.BASENAME}/sliceInfo.json")
    authority = json.loads(source_audit.read_bytes())["ut_austin_raw_exemplar"]
    metadata_digest = authority["metadata_members_crc_verified"]["sliceInfo.json"]
    if digest(frame_times) != metadata_digest:
        raise ValueError("Archived relative timing metadata changed")
    marks = wave.ordered_frames({"sliceInfo.json": frame_times})
    for row in measured:
        start = row["start_ms"] / 1000
        target = None
        if row["panel"] == "physical":
            first = next(t for _, t in marks if start <= t and t + 1 / wave.FRAME_HZ <= start + .02)
            target = (first - start) * wave.RATE
        for arm in row["arms"]:
            arm["strongest"] = score(arm["factors"], target)
    return dict(binary_sha256=pins, archive_sha256=wave.ARCHIVE_SHA, rows=measured)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (trial, ("work", "builds", "archive", "assets")),
        (offsite, ("work", "frozen", "archive", "source_audit", "wide_reference", "assets")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for name in fields:
            command.add_argument(name, type=lambda value: Path(value).resolve())
    arguments = vars(parser.parse_args())
    handler = arguments.pop("handler")
    arguments.pop("action")
    print(json.dumps(handler(**arguments), indent=2, allow_nan=False))
