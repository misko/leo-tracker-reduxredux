#!/usr/bin/env python3
"""Build the bounded one-feature proposal ablations for host and ARM."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources"
ARM_CC = "/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc"
ARM_INCLUDE = "/var/tmp/leo-fftw-float-20260912/install/include"
ARM_FFTW = "/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def invoke(command):
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return {"command": command, "stdout": completed.stdout, "stderr": completed.stderr}


def build(target):
    output = ROOT / "builds" / target
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    arm = target == "arm"
    compiler = ARM_CC if arm else "gcc"
    flags = ["-std=c11", "-O3", "-Wall", "-Wextra", "-Werror", "-fno-fast-math"]
    if arm:
        flags += ["-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard", "-DLEO_LAG_ARM_AFFINITY", "-DLEO_PROPOSAL_NEON_FOLD", f"-I{ARM_INCLUDE}"]
    library = [ARM_FFTW] if arm else ["-lfftw3f"]
    commands = []
    binaries = {}
    for source, name in (("proposal_feature_ablation.c", "proposal_feature_ablation"), ("control_proposal_probe.c", "control_proposal_probe")):
        destination = output / name
        command = [compiler, *flags, str(SOURCE / source), *library, "-lm", "-o", str(destination)]
        commands.append(invoke(command))
        binaries[name] = sha(destination)
    receipt = {
        "schema": "arm-proposal-feature-ablation-build/v1",
        "target": target,
        "implementation": ("NEON exact fold and radix combined-percentile ranking" if arm else "scalar host reference with radix combined-percentile ranking") + "; one selected feature omitted before reference, fold, correlation, and ranking",
        "executed_on_target": False,
        "commands": commands,
        "binaries": binaries,
        "sources": {source.name: sha(source) for source in sorted(SOURCE.glob("*.c"))},
    }
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return {"receipt": str((output / "build-receipt.json").relative_to(ROOT)), "sha256": sha(output / "build-receipt.json")}


def main():
    records = {target: build(target) for target in ("host", "arm")}
    test = subprocess.run(["python3", str(ROOT / "test_feature_ablation.py")], text=True, capture_output=True, check=True)
    receipt = {"schema": "arm-proposal-feature-ablation-matrix/v1", "builds": records,
               "host_test": {"stdout": test.stdout, "stderr": test.stderr}}
    (ROOT / "build-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
