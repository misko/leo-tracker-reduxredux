"""Read-only, bounded prototype: exact stable top-k Hough peak selection.

Runs input preparation only; does not run a regional search or publish products.
The production implementation is unchanged. Use the deployed Python/PYTHONPATH.
"""

import inspect
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis import cfo_lines, persistent_hop_trajectory
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def stable_top(values, count):
    if count >= len(values):
        return np.argsort(values, kind="stable")
    threshold = np.partition(values, len(values) - count)[len(values) - count]
    above = np.flatnonzero(values > threshold)
    needed = count - len(above)
    boundary = np.flatnonzero(values == threshold)[-needed:] if needed else above[:0]
    selected = np.concatenate((above, boundary))
    return selected[np.lexsort((selected, values[selected]))]


def main():
    rng = np.random.default_rng(621)
    checks = 0
    for size in (1, 8, 100, 10000):
        for values in (np.zeros(size), rng.integers(0, 8, size), rng.normal(size=size)):
            for count in (1, min(7, size), size, size + 1):
                assert np.array_equal(
                    stable_top(values, count), np.argsort(values, kind="stable")[-count:]
                )
                checks += 1
    original = cfo_lines.weighted_hough_lines
    source = inspect.getsource(original)
    old = 'np.argsort(accumulator.ravel(), kind="stable")[-config.peak_candidates :]'
    assert source.count(old) == 1
    source = source.replace(old, "stable_top(accumulator.ravel(), config.peak_candidates)")
    namespace = dict(original.__globals__, stable_top=stable_top)
    exec(compile(source, "<hough-top-k-prototype>", "exec"), namespace)
    candidate = namespace[original.__name__]
    rows = []
    try:
        for sid, rate in (
            ("scan-fw-cc609ed603589e6e", 2500000),
            ("scan-fw-aadec7177d989684", 10000000),
        ):
            for repeat in range(2):
                row = dict(session=sid, rate=rate, repeat=repeat)
                digests = []
                order = ("baseline", "candidate") if repeat == 0 else ("candidate", "baseline")
                for variant in order:
                    persistent_hop_trajectory.weighted_hough_lines = (
                        original if variant == "baseline" else candidate
                    )
                    reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
                    try:
                        cpu, wall = time.process_time(), time.perf_counter()
                        result = prepare_adaptive_tle_position_inputs(
                            sid, inputs=reader, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
                        )
                        row[variant] = dict(
                            cpu_s=time.process_time() - cpu, wall_s=time.perf_counter() - wall
                        )
                        digests.append(result.evidence_sha256)
                    finally:
                        reader.close()
                row["exact_evidence_parity"] = digests[0] == digests[1]
                row["evidence_sha256"] = digests[0]
                assert row["exact_evidence_parity"]
                rows.append(row)
                print(json.dumps(row), flush=True)
    finally:
        persistent_hop_trajectory.weighted_hough_lines = original
    Path("/var/tmp/hough-top-k-results.json").write_text(
        json.dumps(dict(ordering_checks=checks, rows=rows), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
