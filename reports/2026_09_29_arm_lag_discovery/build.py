"""Build host and Cortex-A9 lag-proposal cost probes with receipts."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "proposal_probe.c"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(name: str, compiler: str, flags: list[str]) -> None:
    folder = HERE / "builds" / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder / SOURCE.name).write_bytes(SOURCE.read_bytes())
    binary = folder / "proposal_probe"
    command = [compiler, "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror", "-fno-fast-math", *flags, str(SOURCE), "-lfftw3", "-lm", "-o", str(binary)]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    (folder / "build.json").write_text(
        json.dumps({"command": command, "source_sha256": sha(SOURCE), "binary_sha256": sha(binary), "compiler_stderr": completed.stderr}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v2")
    args = parser.parse_args()
    if not args.version.startswith("v") or not args.version[1:].isdigit():
        parser.error("version must look like v2")
    build(f"host-{args.version}", "gcc", [])
    build(f"arm-{args.version}", str(CROSS), ["-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard", "-DLEO_LAG_ARM_AFFINITY"])
