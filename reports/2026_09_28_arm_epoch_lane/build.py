"""Build the report-local four-epoch/one-CFO coarse experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_ARM = Path("/var/tmp/leo-arm-conditioned-czt-v3")
BASE_HOST = Path("/var/tmp/leo-host-conditioned-czt-v2")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, arm: bool) -> None:
    baseline = BASE_ARM if arm else BASE_HOST
    shutil.copytree(baseline, output)
    native = output / "src/native_presence"
    shutil.copytree(native, output / "original_native")
    shutil.copyfile(HERE / "coarse_fp32_epoch.h", native / "coarse_fp32.h")
    shutil.copyfile(HERE / "coarse_epoch.h", native / "coarse_epoch.h")
    for name in ("coarse_epoch.c", "coarse_epoch.h", "test_coarse_epoch.c",
                 "test_coarse_grid.c", "test_grid_parity.py"):
        shutil.copyfile(HERE / name, output / name)

    old_receipt = json.loads((baseline / "build.json").read_text())
    first = old_receipt["commands"][0]
    compiler = first[0]
    first_include = first.index("-I")
    flags = first[1:first_include]
    commands = []
    for command in old_receipt["commands"][:2]:
        rebuilt = [str(output / Path(x).relative_to(baseline))
                   if x.startswith(str(baseline) + "/") else x for x in command]
        rebuilt.insert(rebuilt.index("-lfftw3"), str(output / "coarse_epoch.c"))
        subprocess.run(rebuilt, check=True, capture_output=True, text=True)
        commands.append(rebuilt)

    unit = [compiler, *flags, "-I", str(output), str(output / "coarse_epoch.c"),
            str(output / "test_coarse_epoch.c"), "-lm", "-o",
            str(output / "test_coarse_epoch")]
    subprocess.run(unit, check=True, capture_output=True, text=True)
    commands.append(unit)
    if not arm:
        subprocess.run([str(output / "test_coarse_epoch")], check=True)

    grid_targets = []
    for include, extra, target in (
        (output / "original_native", [], "test_grid_original"),
        (native, [str(output / "coarse_epoch.c")], "test_grid_epoch"),
    ):
        command = [compiler, *flags, "-Wno-unused-parameter",
                   "-Wno-unused-function", "-I", str(include),
                   str(include / "presence.c"), *extra,
                   str(output / "test_coarse_grid.c"), str(output / "fft_full.c"),
                   "-lfftw3", "-lm", "-o", str(output / target)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
        grid_targets.append(target)
    if not arm:
        subprocess.run(["python3", str(output / "test_grid_parity.py"),
                        *(str(output / x) for x in grid_targets)], check=True)

    sources = {str(path.relative_to(output)): sha(path)
               for path in sorted(output.rglob("*"))
               if path.is_file() and path.suffix in (".c", ".h", ".inc")}
    receipt = {
        "schema": "arm-epoch-lane-build/v1",
        "arm": arm,
        "baseline_build": str(baseline),
        "baseline_receipt_sha256": sha(baseline / "build.json"),
        "kernel": "4 adjacent epoch lanes x 1 CFO; 2 accumulator vectors",
        "coarse_compiler_scope": "no-prefetch-loop-arrays",
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": sources,
        "binary_sha256": {name: sha(output / name) for name in
                          ("probe", "cohort", "test_coarse_epoch", *grid_targets)},
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm)
