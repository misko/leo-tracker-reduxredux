"""Benchmark exact two-mode scout arithmetic on the saved combined receiver."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

import receiver_mixer_profile_trial as mixer_profile
from . import receiver_cfo_native_trial as native
from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import exports, run
from .receiver_frame_planes_composed import PLANES
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.experimental import receiver_build, receiver_spectral_vectors
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver


REFERENCE_SHA = "14b52e7e85b6fcf94c956acb3da579d711959c3313d1bc6b9522128c5f161e7c"
PROFILE = (("static void find_times(", "TIME_SEARCH"), ("static int find_carriers(", "CARRIER_SEARCH"))


def build(work, bench, assets):
    work.mkdir()
    combined = bench / "d97b-planes-and-fir"
    base = json.loads((combined / "build.json").read_bytes())
    restore.digest(combined / "receiver.so", REFERENCE_SHA)
    link = base["link"]
    for item in link:
        if item.endswith(".o"):
            path = Path(item)
            restore.digest(path, base["objects"][path.name])
    saved_timing = next(Path(item) for item in link if Path(item).name == "timing_first_receiver.o")
    old_source = saved_timing.with_suffix(".c")
    restore.digest(saved_timing, PLANES[saved_timing.name])
    restore.digest(old_source, PLANES[old_source.name])
    reference = work / "reference.so"
    run([*link[:-1], reference], cwd=restore.PINNED)
    restore.digest(reference, REFERENCE_SHA)
    stock = old_source.read_text()
    vector = receiver_spectral_vectors.overlay(stock)
    profile_command, trials = compile_variants(work, link, saved_timing, stock, vector, assets)
    candidate = work / "packed/use.so"
    if exports(candidate) != exports(reference):
        raise ValueError("Packing changed the public receiver symbols")
    return dict(
        reference_sha256=REFERENCE_SHA, stock_source_sha256=restore.digest(old_source),
        header_sha256=restore.digest(restore.HERE / "receiver_spectral_vectors.inc"),
        overlay_sha256=restore.digest(restore.HERE / "receiver_spectral_vectors.py"),
        profile_command=profile_command, builds=trials,
    )


def compile_variants(work, link, saved_timing, stock, vector, assets):
    recipe_file = restore.PINNED / "build.json"
    restore.digest(recipe_file, restore.RECIPE_SHA)
    flags, _ = restore.compiler_inputs(
        json.loads(recipe_file.read_bytes()), saved_timing.parent, saved_timing.parent,
    )
    profile_object = work / "receiver_profile.o"
    compiler = link[0]
    profile_command = run([
        compiler, *flags, "-D_POSIX_C_SOURCE=200809L", "-c",
        restore.HERE / "receiver_profile.c", "-o", profile_object,
    ], cwd=restore.PINNED)
    trials = {}
    for label, source, profiled in (("packed", vector, False),
                                    ("profile-reference", stock, True),
                                    ("profile-packed", vector, True)):
        target = work / label
        target.mkdir()
        profile_dir = target / "feedback"
        profile_dir.mkdir()
        timing = target / saved_timing.name
        text = target / saved_timing.with_suffix(".c").name
        text.write_text(receiver_build.profile_source(source, PROFILE) if profiled else source)
        recipe = [timing if item == str(saved_timing) else item for item in link[1:-2]]
        if profiled:
            recipe.append(profile_object)
        commands = []
        for mode in ("generate", "use"):
            library = target / f"{mode}.so"
            feedback = [f"-fprofile-{mode}={profile_dir}", "-fno-profile-values"]
            if mode == "use":
                feedback += ["-Werror=missing-profile", "-Werror=coverage-mismatch"]
            commands.append(run([
                compiler, *feedback, *flags, "-I", restore.PINNED / "tools/pipeline_eval/variants",
                "-I", restore.HERE, "-c", text, "-o", timing,
            ], cwd=restore.PINNED))
            commands.append(run([compiler, *feedback, *recipe, "-o", library], cwd=restore.PINNED))
            if mode == "generate":
                process = subprocess.run([sys.executable, mixer_profile.__file__, "train", library, assets],
                                         text=True, stdout=subprocess.PIPE, check=True)
        trials[label] = dict(library_sha256=restore.digest(library), timing_source_sha256=restore.digest(text),
                             timing_object_sha256=restore.digest(timing),
                             commands=commands, training=json.loads(process.stdout))
    return profile_command, trials


def measure(paths, groups, assets, *, profile=False):
    with ExitStack() as stack:
        radios = {}
        for edge in ("lower", "upper"):
            asset = assets / f"{edge}.f32"
            restore.digest(asset, PINS[asset.name])
            template = np.fromfile(asset, dtype="<f4")
            for label, path in paths.items():
                radio = Receiver(path, template)
                stack.callback(radio.close)
                radios[edge, label] = radio
        arms = tuple(paths)
        comparisons = (arms,)
        if profile:
            for label in arms:
                radios["lower", label].reset_profile()
        results = {label: native.measure(rows, radios, arms, comparisons, cycles=3 if profile else 6)
                   for label, rows in groups.items()}
        profiles = {label: radios["lower", label].profile() for label in arms} if profile else None
    return dict(samples=results, profiles=profiles)


def trial(work, bench, assets, weak, archive, source_audit, wide_reference):
    receipt = build(work, bench, assets)
    groups = native.inputs(weak, archive, source_audit, wide_reference)
    return dict(
        build=receipt,
        native=measure(dict(reference=work / "reference.so", packed=work / "packed/use.so"), groups, assets),
        stages=measure(dict(reference=work / "profile-reference/use.so",
                            packed=work / "profile-packed/use.so"),
                       {"ds26-weak": groups["ds26-weak"]}, assets, profile=True),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ("work", "bench", "assets", "weak", "archive", "source_audit", "wide_reference"):
        parser.add_argument(item, type=lambda value: Path(value).resolve())
    print(json.dumps(trial(**vars(parser.parse_args())), indent=2, allow_nan=False))
