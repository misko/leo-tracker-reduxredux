"""Compare two Hough implementations on bounded saved preparation workloads."""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

from leo.analysis import persistent_hop_trajectory
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.weighted_hough_lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--session", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.session) > 6:
        parser.error("bounded to six saved sessions")
    functions = {key: load(key, getattr(args, key)) for key in ("baseline", "candidate")}
    original = persistent_hop_trajectory.weighted_hough_lines
    rows = []
    try:
        for index, sid in enumerate(args.session):
            row = {"session": sid}
            digests = []
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            for variant in order:
                persistent_hop_trajectory.weighted_hough_lines = functions[variant]
                reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
                try:
                    cpu, wall = time.process_time(), time.perf_counter()
                    prepared = prepare_adaptive_tle_position_inputs(
                        sid, inputs=reader, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
                    )
                    row[variant] = {
                        "cpu_s": time.process_time() - cpu,
                        "wall_s": time.perf_counter() - wall,
                    }
                    digests.append(prepared.evidence_sha256)
                finally:
                    reader.close()
            row["exact_evidence_parity"] = digests[0] == digests[1]
            row["evidence_sha256"] = digests[0]
            rows.append(row)
            args.output.write_text(json.dumps(rows, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            if not row["exact_evidence_parity"]:
                raise RuntimeError("Hough input evidence changed")
    finally:
        persistent_hop_trajectory.weighted_hough_lines = original


if __name__ == "__main__":
    main()
