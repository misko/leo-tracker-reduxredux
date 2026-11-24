"""Compare private native CI16 packing with the original level-1 capture."""

import argparse
from pathlib import Path
import resource
import subprocess
from tempfile import TemporaryDirectory

from .ci16_packing import Packing, SOURCE
from .future_capture_storage import clock, elapsed, trial


PACKED = "packed-ci16"
ORDERS = (("ordinary", "split-level-1", PACKED), (PACKED, "ordinary", "split-level-1"),
          ("split-level-1", PACKED, "ordinary"))
BUILD = ("cc", "-std=c11", "-O3", "-fPIC", "-shared", "-mssse3", "-Wall", "-Wextra", "-Werror")


def run(root):
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a fresh local tmpfs output")
    with TemporaryDirectory(dir=root.parent, prefix="leo-ci16-pack-build-") as temp:
        binary = Path(temp) / "packing.so"
        before = clock()
        child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        subprocess.run([*BUILD, str(SOURCE), "-o", str(binary)], check=True)
        compilation = elapsed(before)
        child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        compilation["compiler_cpu_s"] = (
            child_after.ru_utime - child_before.ru_utime + child_after.ru_stime - child_before.ru_stime)
        trial(root, orders=ORDERS, codecs={PACKED: Packing(binary)}, legacy_mode=PACKED)
        from .full_short_cold import freeze

        freeze(root / "compiler.json", dict(command=[*BUILD, str(SOURCE), "-o", str(binary)], timing=compilation,
               version=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
