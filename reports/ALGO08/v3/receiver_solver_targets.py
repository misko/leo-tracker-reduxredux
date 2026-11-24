"""Compute the end-to-end target for two disjoint optimizations on the frozen 30 DS30 pairs."""

from gzip import decompress
from hashlib import sha256
import json
from math import fsum, isfinite
from pathlib import Path
from statistics import median


RECEIPT = Path(__file__).parent / "measurements" / "first30-after-intake.json.gz"
DIGEST = "5d7b3624bca9f1d808cb0bee044fcadb7c4593054da771d8c57dc0dd1456de3c"


def required_reduction(target_met):
    """Find the smallest fraction of a stage to remove that satisfies a monotone timing gate."""
    if target_met(0.):
        return 0.
    if not target_met(1.):
        return None
    lo, hi = 0., 1.
    for _ in range(54):
        mid = (lo + hi) / 2
        if target_met(mid):
            hi = mid
        else:
            lo = mid
    return hi


def targets(clocks, native_speedup):
    """Clock rows are installed total, candidate total, native callbacks, and chosen solver scope."""
    if not clocks or not isfinite(native_speedup) or native_speedup < 1:
        raise ValueError("Expected measured rows and a finite callback speedup of at least one")
    reduced = []
    for installed, current, native, solver in clocks:
        if (not all(isfinite(t) for t in (installed, current, native, solver)) or min(installed, current) <= 0
                or min(native, solver) < 0 or native + solver > current):
            raise ValueError("Expected disjoint stages within a positive recorded runtime")
        reduced.append((installed, current - native * (1 - 1 / native_speedup), solver))
    half_sum = .5 * fsum(a for a, _, _ in reduced)
    summed = required_reduction(lambda f: fsum(b - f * s for _, b, s in reduced) <= half_sum)
    paired = required_reduction(lambda f: median((b - f * s) / a for a, b, s in reduced) <= .5)
    return dict(summed=summed, paired_median=paired,
                both=max(summed, paired) if summed is not None and paired is not None else None)


def main():
    data = RECEIPT.read_bytes()
    if sha256(data).hexdigest() != DIGEST:
        raise ValueError("Expected the attested first-30 clock partition")
    cases = json.loads(decompress(data))["cases"]
    rows = {"whole_solver": [], "accepted_and_rejected_proposals": [], "accepted_proposals": []}
    for c in cases:
        phases = c["phases"]
        solver = phases["solver"]["elapsed_s"]
        base = (c["stock_wall_s"], c["actual_wall_s"], c["native_detector_s"])
        rows["whole_solver"].append((*base, phases["outer"]["elapsed_s"]["solve"]))
        rows["accepted_and_rejected_proposals"].append((*base, solver["accepted_proposal"] + solver["rejected_proposal"]))
        rows["accepted_proposals"].append((*base, solver["accepted_proposal"]))
    output = {name: {speed: targets(v, speed) for speed in (1., 1.25, 1.5, 2., 3.)} for name, v in rows.items()}
    print(json.dumps(dict(measured_pairs=len(cases), input_sha256=DIGEST, required_fraction_removed=output), indent=2))


if __name__ == "__main__":
    main()
