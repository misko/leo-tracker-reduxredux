"""Build host and Cortex-A9 FP32 proposal probes with reproducible receipts."""

import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "proposal_probe.c"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
ARM_FFTW = Path("/var/tmp/leo-fftw-float-20260912/install")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(name: str, command: list[str], libraries: list[str]) -> None:
    folder = HERE / "builds" / name
    folder.mkdir(parents=True, exist_ok=False)
    snapshot = folder / SOURCE.name
    snapshot.write_bytes(SOURCE.read_bytes())
    binary = folder / "proposal_probe"
    full_command = command + [str(snapshot), *libraries, "-lm", "-o", str(binary)]
    completed = subprocess.run(full_command, check=True, text=True, capture_output=True)
    receipt = {
        "command": full_command,
        "source_sha256": sha(snapshot),
        "binary_sha256": sha(binary),
        "compiler_version": subprocess.run([command[0], "--version"], check=True, text=True, capture_output=True).stdout.splitlines()[0],
        "compiler_stderr": completed.stderr,
    }
    (folder / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    common = ["-std=c11", "-O3", "-Wall", "-Wextra", "-Werror", "-fno-fast-math"]
    build("host-v1", ["gcc", *common], ["-lfftw3f"])
    build(
        "arm-v1",
        [str(CROSS), *common, "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard", "-DLEO_LAG_ARM_AFFINITY", f"-I{ARM_FFTW / 'include'}"],
        [str(ARM_FFTW / "lib/libfftw3f.a")],
    )
