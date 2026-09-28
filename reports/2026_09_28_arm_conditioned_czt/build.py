"""Build a source-receipted conditioned-CZT experiment from the selected baseline."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = Path("/var/tmp/leo-host-coarse-scoped")
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
ARM_FFTWF = Path("/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, commands):
    subprocess.run(command, check=True, capture_output=True, text=True)
    commands.append([str(x) for x in command])


def build(output, arm=False, sanitize=False):
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(BASELINE / "src", output / "src")
    inputs = ["full_search.c", "full_search.h", "probe_main.c", "cohort_probe.c",
              "conditioned_czt.c", "conditioned_czt.h", "test_conditioned_czt.c",
              "test_conditioned_integration.c"]
    for name in inputs:
        shutil.copyfile(HERE / name, output / name)
    shutil.copyfile(BASELINE / "fft_full.c", output / "fft_full.c")
    compiler = str(CROSS) if arm else "gcc"
    flags = ["-DLEO_PRESENCE_FFTW=1", "-std=c11", "-O3", "-Wall", "-Wextra",
             "-fno-fast-math", "-DLEO_PRESENCE_COARSE_FP32",
             "-DLEO_FULL_CONDITIONED_SCREEN"]
    if arm:
        flags += ["-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard",
                  "-DLEO_FULL_ARM_AFFINITY"]
    if sanitize:
        if arm:
            raise ValueError("sanitizers are host-only")
        flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    include = ["-I", str(output / "src/native_presence"), "-I", str(output)]
    fftlibs = [str(ARM_FFTWF), "-lfftw3"] if arm else ["-lfftw3", "-lfftw3f"]
    commands = []
    common = [compiler, *flags, *include, str(output / "full_search.c"),
              str(output / "conditioned_czt.c")]
    for main, target in (("probe_main.c", "probe"), ("cohort_probe.c", "cohort")):
        run([*common, str(output / main), str(output / "fft_full.c"), *fftlibs,
             "-lm", "-o", str(output / target)], commands)
    unit_fftlibs = [str(ARM_FFTWF)] if arm else ["-lfftw3f"]
    run([compiler, *flags, "-I", str(output), str(output / "test_conditioned_czt.c"),
         str(output / "conditioned_czt.c"), *unit_fftlibs,
         "-lm", "-o", str(output / "test_conditioned_czt")], commands)
    run([compiler, *flags, *include, str(output / "test_conditioned_integration.c"),
         str(output / "conditioned_czt.c"), str(output / "fft_full.c"), *fftlibs,
         "-lm", "-o", str(output / "test_conditioned_integration")], commands)
    if not arm:
        subprocess.run([str(output / "test_conditioned_czt")], check=True)
        subprocess.run([str(output / "test_conditioned_integration")], check=True)
    source_files = sorted(p for p in output.rglob("*") if p.is_file() and p.suffix in {".c", ".h"})
    receipt = {
        "schema": "arm-conditioned-czt-build/v1", "arm": arm, "sanitize": sanitize,
        "baseline_build": str(BASELINE),
        "baseline_receipt_sha256": digest(BASELINE / "build.json"),
        "origin_sha256": {name: digest(BASELINE / name) for name in
            ("full_search.c", "full_search.h", "probe_main.c", "cohort_probe.c", "fft_full.c")},
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": {str(p.relative_to(output)): digest(p) for p in source_files},
        "binary_sha256": {name: digest(output / name) for name in
            ("probe", "cohort", "test_conditioned_czt", "test_conditioned_integration")},
        "precision": "FP32 FFTW CZT screen over every regular-grid bin; existing FP64 near-max verification and final GLRT",
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm, args.sanitize)
