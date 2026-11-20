"""Estimate the receiver's position from one track file, TLE snapshot and offered regions."""

import argparse
import json
from pathlib import Path

from engine.receiver import solve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path, help="TLE file")
    parser.add_argument("--regions", required=True, type=Path,
                        help="JSON array of {id, center: [lat, lon]} or a study query object")
    parser.add_argument("--diagnostics", action="store_true",
                        help="include intermediate scores and the unpublished best estimate")
    args = parser.parse_args()
    offered = json.loads(args.regions.read_bytes())
    if isinstance(offered, dict):
        offered = offered["regions"]
    result = solve(json.loads(args.observation.read_bytes()), offered, args.catalog.read_bytes())
    if not args.diagnostics:
        result = {key: result[key] for key in ("status", "reason", "region_id", "latlon")}
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
