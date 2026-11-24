"""Compare private native CI16 packing with the original level-1 capture."""

import argparse
import json
from pathlib import Path
import resource
import subprocess
from tempfile import TemporaryDirectory

from .ci16_packing import Packing, SOURCE
from .future_capture_storage import ORIGINAL, SHORT, StagedMember, clock, elapsed, trial
from .sparse_cold_input import verified


PACKED = "packed-ci16"
ORDERS = (("ordinary", "split-level-1", PACKED), (PACKED, "ordinary", "split-level-1"),
          ("split-level-1", PACKED, "ordinary"))
BUILD = ("cc", "-std=c11", "-O3", "-fPIC", "-shared", "-mssse3", "-Wall", "-Wextra", "-Werror")
DENSE_STAGE = Path("/dev/shm/leo-seekable-member-0008-case1")
DENSE_RECEIPT = "b1f310a05ade750be8e6dbf09f455baa27b71cb7dcd03334130a285a852d6cd6"
DENSE_STAGING = "e7f73261eee60c3f6277a820a7be0c3338e55daaae8b84843c21707831e44fb4"


def dense_member():
    previous = json.loads(verified(DENSE_STAGE / "result.json", DENSE_RECEIPT))
    staging = json.loads(verified(DENSE_STAGE / "staged.json", DENSE_STAGING))
    entry, original, runs = previous["source"], previous["original_member"], previous["receivers"]["mixed"]
    path = Path(entry["path"])
    fingerprints = {r["probes_sha256"] for r in runs}
    if (path.parent != DENSE_STAGE or staging["timing"]["input_blocks"] or not staging["no_blocking_payload_fallback"]
            or (original["chunk_index"], original["first_sequence"], original["window_count"]) != (0, 0, 64)
            or any(row["visits"] != {"full": 8, "short_primary": 56} or row["selected"] != 67 for row in runs)
            or len(fingerprints) != 1):
        raise ValueError("Independent sealed dense-member stage or receiver reference changed")
    return StagedMember("DS30-0008", path, entry["manifest_digest"], original["compressed_sha256"],
                        original["uncompressed_sha256"], original["index_sha256"], original["compressed_bytes"],
                        original["index_bytes"], 6_812, fingerprints.pop())


def run(root, *, member=ORIGINAL, short_binary=SHORT):
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
        trial(root, orders=ORDERS, codecs={PACKED: Packing(binary)}, legacy_mode=PACKED,
              member=member, short_binary=short_binary)
        from .full_short_cold import freeze

        freeze(root / "compiler.json", dict(command=[*BUILD, str(SOURCE), "-o", str(binary)], timing=compilation,
               version=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--case", choices=("DS30-0016", "DS30-0008"), default="DS30-0016")
    parser.add_argument("--short-library", type=Path, default=SHORT)
    options = parser.parse_args()
    run(options.root, member=ORIGINAL if options.case == "DS30-0016" else dense_member(), short_binary=options.short_library)
