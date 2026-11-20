"""Build and execute the static portable original candidate verifier."""

import argparse
import os
import subprocess
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output
from .portable_fine_results import FLAGS, TARGETS
from .portable_verifier_fixture import VISITS

KERNEL = ROOT / "native/adaptive/detector/kernel/private"
VARIANTS = ROOT / "tools/pipeline_eval/variants"
SOURCES = (
    Path(__file__).with_name("portable_verifier_cli.c"),
    *(
        VARIANTS / f"{name}.c"
        for name in (
            "portable_verifier",
            "portable_fine",
            "fine_search",
            "conditioned_cfo_bank",
            "refine_bank",
        )
    ),
    KERNEL / "fft_full.c",
)
BUILD_FLAGS = (*FLAGS, "-DLEO_PRESENCE_ITERATIVE_FFT=1", "-fno-math-errno")


def command(target):
    cc, arch, _, _ = TARGETS[target]
    if target == "x86":
        arch = ("-march=x86-64-v3",)
    return [cc, *BUILD_FLAGS, *arch, "-I", str(KERNEL / "native_presence"), *SOURCES, "-lm"]


def build(work, target):
    folder = work / "build" / target
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [*command(target), "-o", "portable-verifier"],
        check=True,
        cwd=folder,
        env=os.environ | {"TMPDIR": str(folder)},
        timeout=45,
    )


def execute(work, target, cpu):
    binary = work / "build" / target / "portable-verifier"
    _, _, emulator, _ = TARGETS[target]
    launch = ["taskset", "-c", str(cpu), *emulator, binary]
    subprocess.run([*launch, "--self-test"], check=True, timeout=20)
    for case in VISITS:
        folder = work / case
        golden = whole_iq.read(folder / "golden.json")
        capture = whole_iq.checked(folder / "capture.bin", golden["binary_sha256"])
        with (
            (folder / f"{target}-scores.bin").open("xb") as output,
            (folder / f"{target}-resources.json").open("xb") as resources,
        ):
            subprocess.run(
                [*launch, capture], check=True, stdout=output, stderr=resources, timeout=120
            )
        print(target, case, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "execute"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--cpu", type=int, default=17)
    args = parser.parse_args()
    if args.action == "build":
        build(args.work, args.target)
    else:
        execute(args.work, args.target, args.cpu)
