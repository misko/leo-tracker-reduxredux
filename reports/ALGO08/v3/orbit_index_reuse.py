"""Count prospective reuse of immutable orbit source bodies across recorded DS30 cutoffs."""

from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


def digest(data):
    return sha256(data).hexdigest()


def contents(snapshots, cutoff):
    ordered = {}
    for name, pin in sorted(snapshots.items()):
        stamp, suffix = name.split("-", 1)
        if not stamp.isdecimal() or int(stamp) > cutoff or suffix != f"{pin}.tle" or len(bytes.fromhex(pin)) != 32:
            raise ValueError("Orbit source must bind the exact earlier collection time and digest")
        ordered.setdefault(pin, None)
    return tuple(ordered)


def replay(scans, capacity, *, change_at_scan_end=False):
    if capacity <= 0:
        raise ValueError("Cache must have positive capacity")
    retained = OrderedDict()
    rows = []
    for cutoff, label, bodies in sorted(scans):
        if len(set(bodies)) != len(bodies):
            raise ValueError("Each recording must supply distinct orbit body identities")
        # The second policy fixes its reusable source table for the duration of
        # the scan. Temporary per-record work is additional to persistent capacity.
        hits = sum(pin in retained for pin in bodies) if change_at_scan_end else 0
        for pin in bodies:
            if pin in retained:
                if not change_at_scan_end:
                    hits += 1
                retained.move_to_end(pin)
            else:
                retained[pin] = None
                if len(retained) > capacity:
                    retained.popitem(last=False)
        rows.append(dict(case=label, cutoff=cutoff, bodies=len(bodies), hits=hits))
    if not rows or not all(r["bodies"] for r in rows):
        raise ValueError("Expected nonempty signed orbit evidence for each recording")
    uses = sum(r["bodies"] for r in rows)
    hits = sum(r["hits"] for r in rows)
    return dict(capacity_bodies=capacity, change_at_scan_end=change_at_scan_end, uses=uses, hits=hits, misses=uses-hits,
                fully_reused_scans=sum(r["hits"] == r["bodies"] for r in rows),
                median_hits_per_scan=median(r["hits"] for r in rows), rows=rows)


def census():
    from continued_cfo_small_raw import BULK, CASE, ROSTER
    from empty_bootstrap import checked

    cohort = []
    requests = []
    for path in CASE.binding.parent.glob("DS30-*.json"):
        data = path.read_bytes()
        binding = json.loads(data)
        case = binding["case"]
        cohort.append((case["recording"]["window_count"], case["id"], digest(data)))
        if case["id"] != path.stem:
            raise ValueError("Unexpected DS30 binding suffix")
        requests.append((case["id"], binding["orbit_cutoff_ns"], binding["orbit_count"], case["request"]))
    roster = digest(json.dumps(sorted(cohort), separators=(",", ":")).encode())
    if len(requests) != 455 or roster != ROSTER:
        raise ValueError("Expected the signed DS30 roster")
    scans, metadata_bytes = [], 0
    for label, cutoff, expected, request in requests:
        data = checked(BULK / request["path"], request["sha256"])
        snapshots = json.loads(data)["causal_snapshots"]
        if len(snapshots) != expected:
            raise ValueError("Orbit request count differs from the bound case")
        scans.append((cutoff, label, contents(snapshots, cutoff)))
        metadata_bytes += len(data)
    return dict(roster_sha256=roster, recordings=len(scans), request_bytes=metadata_bytes,
                distinct_bodies=len({b for _, _, bodies in scans for b in bodies}),
                capacities=[replay(scans, k, change_at_scan_end=defer)
                            for defer in (False, True) for k in (20, 32, 64)])


if __name__ == "__main__":
    print(json.dumps(census(), indent=2))
