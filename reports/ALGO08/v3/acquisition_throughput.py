"""Calculate the full-acquisition throughput needed for both paired time gates."""

import argparse
import json
from pathlib import Path
from statistics import median

from retained_wait import read_rows


def gates(rows, rate, fraction, *, startup_s=0.):
    """Rate is effective compressed MB per second through sealed detections."""
    before, after = [], []
    for r in rows:
        acquisition, solve, tail = r["stages"]
        total = acquisition + solve + tail
        new = startup_s + r["compressed_MB"]/rate + fraction * solve + tail if acquisition else total
        before.append(total)
        after.append(new)
    return median(a/b for a, b in zip(after, before, strict=True)), sum(after)/sum(before)


def minimum_rate(rows, fraction, gate, *, startup_s=0.):
    if gates(rows, float("inf"), fraction, startup_s=startup_s)[gate] >= .5:
        return None
    lo, hi = 0., 1.
    while gates(rows, hi, fraction, startup_s=startup_s)[gate] > .5:
        hi *= 2
    for _ in range(48):
        mid = (lo+hi)/2
        if gates(rows, mid, fraction, startup_s=startup_s)[gate] > .5:
            lo = mid
        else:
            hi = mid
    return hi


def inventory_sizes(rows, publications):
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader
    from tools.algo08_scan import ALGO08V2

    for r in rows:
        root = publications / r["case"]
        pair = json.loads((root / "pair.json").read_bytes())
        run = pair["runs"]["candidate"]
        if (pair["candidate_specification_digest"] != "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
                or abs(sum(r["stages"]) - run["elapsed_s"]) > 1e-6 or abs(r["cpu_s"] - run["cpu_s"]) > 1e-6):
            raise ValueError("Clock or v3 specification changed")
        receipt = run["receipt"]
        inventory = json.loads((root / "candidate/fast-scan-inputs" / (receipt["session_id"]+".json")).read_bytes())
        digest = canonical_digest(inventory)
        if receipt["session_id"] != "fast-" + digest[7:39]:
            raise ValueError("Inventory does not generate the measured recording session")
        if receipt["decision"] == "complete":
            expected = "algo08-v2-" + canonical_digest([ALGO08V2, digest, receipt["region"], None])[7:39]
            if receipt["run_id"] != expected:
                raise ValueError("Published run and region differ")
        size = files = windows = 0
        for segment in inventory["segments"]:
            reader = ShortWindowReader(Path(segment["path"]))
            if reader.manifest_sha256 != segment["manifest_digest"] or reader.manifest.window_count != segment["windows"]:
                raise ValueError("Saved recording manifest changed")
            size += sum(c.compressed_bytes for c in reader.manifest.chunks)
            windows += reader.manifest.window_count
            files += len(reader.manifest.chunks)
        if windows != inventory["window_count"] or windows != receipt["window_count"]:
            raise ValueError("Incomplete recording inventory")
        r.update(compressed_MB=size/1e6, windows=windows, members=files, inventory_sha256=digest)


def analyze(publications):
    rows = read_rows()
    inventory_sizes(rows, publications)
    ref = Path(__file__).resolve().parent / "measurements/sparse-cold-input.json"
    source = json.loads(ref.read_bytes())
    rates = [arm["effective_compressed_MB_per_s"] for pair in source["runs"] for arm in pair]
    fraction = 25.661 / 60.966
    result = {}
    for key, group in (("all", rows), ("warm", [r for r in rows if (r["initial_residency"] or 0) > .95]),
                       ("cold", [r for r in rows if r["initial_residency"] is not None and r["initial_residency"] < .2])):
        sizes = [r["compressed_MB"] for r in group]
        result[key] = dict(count=len(group), compressed_MB_range=[min(sizes),max(sizes)], median_compressed_MB=median(sizes),
                           needed_median_MB_s=minimum_rate(group, fraction, 0), needed_sum_MB_s=minimum_rate(group, fraction, 1),
                           projected_gates_at_slowest_prefix=gates(group, min(rates), fraction),
                           projected_gates_at_fastest_prefix=gates(group, max(rates), fraction))
    return dict(rows=rows, groups=result, prefix_effective_MB_s=rates, solve_fraction=fraction)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("publications", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    data = analyze(a.publications)
    with a.output.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write("\n")
