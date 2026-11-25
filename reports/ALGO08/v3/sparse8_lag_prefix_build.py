"""Compile and train matching sparse8 timing objects without opening evaluation I/Q."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from . import sparse8_lag_prefix as edit
from . import sparse8_native_profile as lineage


INCLUDE = Path("tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.inc")
STEM = "timing_first_receiver"


def build(output):
    if len(os.sched_getaffinity(0)) != 1 or 2 in os.sched_getaffinity(0) or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use one nonbenchmark core at nice 15 for the synthetic build")
    recipe = json.loads(lineage.checked(lineage.BASE / "build-receipt.json", lineage.STOCK["build-receipt.json"]))
    command = recipe["relink"]
    for part in command:
        path = Path(part)
        if path.suffix == ".o":
            name = path.name
            pin = lineage.STOCK[name] if name == "two_carrier_receiver.o" else recipe["short_object_sha256"][name]
            lineage.checked(path, pin)
    archived = lineage.SPARSE / f"{STEM}.c"
    pinned_source = lineage.checked(archived, edit.TIMING_SHA256)
    lineage.checked(lineage.SPARSE / f"{STEM}.o", lineage.STOCK[f"{STEM}.o"])
    lineage.checked(lineage.SPARSE / "use.so", lineage.ORIGINAL)
    lineage.checked(lineage.RECIPE_SOURCE / INCLUDE, edit.SPECTRAL_SHA256)
    lineage.checked(lineage.RECIPE_SOURCE / INCLUDE.with_name("receiver_sparse_carriers.inc"), lineage.SPARSE_INCLUDE)
    trainer = lineage.TRAIN_ROOT / "reports/ALGO08/single-core-2x/receiver_mixer_profile_trial.py"
    lineage.checked(trainer, lineage.TRAINER)
    assets = lineage.RELEASE / "assets"
    for edge, pin in lineage.PILOTS.items():
        lineage.checked(assets / f"{edge}.f32", pin)
    build_dir = lineage.RECIPE_SOURCE / "native/algo08v2"
    env = os.environ | dict.fromkeys(lineage.THREADS, "1")
    env["PYTHONPATH"] = os.pathsep.join(map(str, (lineage.TRAIN_ROOT, lineage.TRAIN_ROOT / "src",
                                                  lineage.RELEASE / "src", lineage.RELEASE)))
    calls = []

    def run(argv, **options):
        argv = list(map(str, argv))
        calls.append(argv)
        return subprocess.run(argv, cwd=build_dir, check=True, **options)

    def link(destination, timing, flags=()):
        parts = [timing if Path(part).name == f"{STEM}.o" else part for part in command[3:-1]]
        run([command[0], *flags, *parts, destination])

    output = output.absolute()
    output.mkdir()
    installed = output / "installed.so"
    link(installed, lineage.SPARSE / f"{STEM}.o")
    lineage.checked(installed, lineage.ORIGINAL)
    control, candidate = output / "control", output / "candidate"
    control.mkdir()
    (control / f"{STEM}.c").write_bytes(pinned_source)
    edit.overlay(archived, lineage.RECIPE_SOURCE / INCLUDE, candidate)
    arms = {}
    for scope in (control, candidate):
        source, obj = scope / f"{STEM}.c", scope / f"{STEM}.o"
        feedback = scope / "feedback"
        feedback.mkdir()
        profile = feedback / str(obj.with_suffix(".gcda")).lstrip("/")
        build_flags = recipe["compile"][1:-4]
        generate = [f"-fprofile-generate={feedback}", "-fno-profile-values"]
        run([command[0], *generate, *build_flags, "-c", source, "-o", obj])
        link(scope / "generate.so", obj, generate)
        result = run([sys.executable, "-B", trainer, "train", scope / "generate.so", assets],
                     capture_output=True, env=env)
        records = json.loads(result.stdout)
        signature = lineage.digest(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())
        if signature != lineage.TRAIN_ROWS:
            raise ValueError(f"Synthetic training callback outcomes changed for {scope.name}")
        use = [f"-fprofile-use={feedback}", "-fno-profile-values"]
        run([command[0], *use, "-Werror=coverage-mismatch", "-Werror=missing-profile", *build_flags,
             "-c", source, "-o", obj])
        target = scope / "use.so"
        link(target, obj)
        arms[scope.name] = dict(training_sha256=signature, training_calls=len(records),
                                paths={name: str(path) for name, path in
                                       (("library", target), ("object", obj), ("feedback", profile))},
                                sha256={name: lineage.digest(path.read_bytes()) for name, path in
                                        (("library", target), ("object", obj), ("feedback", profile), ("source", source))})
    receipt = dict(arms=arms, archived_dso_sha256=lineage.ORIGINAL, trainer_sha256=lineage.TRAINER,
                   compiler=subprocess.check_output([command[0], "--version"], text=True).splitlines()[0],
                   affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0), commands=calls)
    (output / "build.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.output)
