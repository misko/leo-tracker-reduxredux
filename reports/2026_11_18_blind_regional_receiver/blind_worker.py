"""Evaluate exactly one offered set against one anonymous observation."""

import hashlib
import json
import math
import resource
import sys
from pathlib import Path
from time import perf_counter


def decode_checked(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"fingerprint mismatch for {path.name}")
    return data.decode()


def perturb(observation, mode):
    if mode not in {"plus", "minus"}:
        return observation
    sign = 1 if mode == "plus" else -1
    tracks = []
    for i, track in enumerate(observation["tracks"]):
        # A constant per fixed-RF track plus an integer alias-branch change.
        rf_term = 100_000.0 * (track["rf_hz"] / 1e9 - 11.5)
        alias = ((i % 5) - 2) * (2_500_000 / 11)
        values = [value + sign * (rf_term + alias) for value in track["values"]]
        tracks.append(dict(track, values=values))
    return dict(observation, tracks=tracks)


def validate_result(result, regions):
    ids = {r["id"] for r in regions}
    status = result["status"]
    if status not in {"fix", "withheld"} or not result["reason"]:
        raise ValueError("invalid publication status")
    if status == "withheld" and (result["latlon"] is not None or result["region_id"] is not None):
        raise ValueError("coordinates or region published on a withheld query")
    for region_key, point_key in [("region_id", "latlon"), ("best_region", "best_latlon")]:
        region, point = result[region_key], result[point_key]
        if region is not None and region not in ids:
            raise ValueError("unoffered region")
        if point is not None and (len(point) != 2 or not all(map(math.isfinite, point))
                                  or abs(point[0]) > 90 or abs(point[1]) > 180):
            raise ValueError("invalid coordinate")
    if status == "fix" and (result["region_id"] is None or result["latlon"] is None):
        raise ValueError("missing fix")


def main():
    sys.path[:0] = ["/code", "/science", "/packages"]
    from engine.receiver import solve

    if any(Path(directory).exists() for directory in ["/home", "/srv"]):
        raise RuntimeError("unexpected filesystem mount")
    if sys.argv[1:] == ["probe"]:
        count = len(list(Path("/input").iterdir()))
        print(json.dumps({"runtime": sys.version.split()[0], "query_files": count}))
        return

    mode, = sys.argv[1:]
    if mode not in {"primary", "plus", "minus", "reverse"}:
        raise ValueError("unknown experiment arm")
    root = Path("/input")
    if {p.name for p in root.iterdir()} != {"query.json", "observation.json", "orbits.tle"}:
        raise RuntimeError("unexpected query scope")
    query = json.loads((root / "query.json").read_bytes())
    observation = json.loads(decode_checked(root / "observation.json", query["observation"]))
    orbits = decode_checked(root / "orbits.tle", query["catalog"])
    if observation["catalog_timestamp_ns"] > observation["cutoff_utc_ns"]:
        raise ValueError("future catalog file")
    regions = list(query["regions"])
    if mode == "reverse":
        regions.reverse()
    observation = perturb(observation, mode)
    started = perf_counter()
    result = solve(observation, regions, orbits)
    elapsed = perf_counter() - started
    validate_result(result, regions)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(id=query["id"], wall_s=elapsed, peak_rss_kib=usage.ru_maxrss,
                  process_cpu_s=usage.ru_utime + usage.ru_stime)
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
