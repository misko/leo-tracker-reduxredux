"""Use a byte lookup for TLE checksums in the otherwise complete numerical v5 fit."""

import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_lean

BOUNDARY = "Stored GLRT detections through full numerical v5 with bytewise TLE checksums"
_weights = bytearray(256)
_weights[ord("0") : ord("9") + 1] = range(10)
_weights[ord("-")] = 1
ASCII_WEIGHTS = bytes(_weights)
del _weights


def checksum(line):
    prefix = line[:68]
    if prefix.isascii():
        return sum(prefix.encode("ascii").translate(ASCII_WEIGHTS)) % 10
    return sum(int(c) if c.isdigit() else int(c == "-") for c in prefix) % 10


def run(case, work_dir):
    result = v5_lean.run_bound_worker(case, work_dir, Path(__file__))
    result["boundary"] = BOUNDARY
    return result


if __name__ == "__main__":
    from leo.sky import propagation

    with patch.object(propagation, "element_line_checksum", checksum):
        v5_lean._worker(*sys.argv[1:])
