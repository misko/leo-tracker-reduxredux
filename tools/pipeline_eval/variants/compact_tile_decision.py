"""Filter a single installed compact receiver JSON result through its tile guard."""

import argparse
import json
import sys
from math import isfinite

from .compact_tile_interior import guard


def decide(data, *, enabled=False, tile=None):
    if not enabled:
        return data
    if tile is None:
        raise ValueError("the guarded decision requires the exact fitted tile")
    result = json.loads(data)
    if result["status"] == "ok":
        arms = result["arms"]
        if set(arms) != {"c0", "fitted_c"} or any(
            not isinstance(row.get("latlon"), list)
            or len(row["latlon"]) != 2
            or not all(isfinite(x) for x in row["latlon"])
            for row in arms.values()
        ):
            raise ValueError("a successful guarded decision requires two finite selected positions")
    decision = guard(result, tile)
    return data if decision is result else (json.dumps(decision, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interior-guard", action="store_true")
    parser.add_argument("--tile", nargs=2, type=float, metavar=("LAT", "LON"))
    parser.add_argument("--width-km", type=float, default=25.0)
    args = parser.parse_args()
    tile = None
    if args.interior_guard:
        if (
            args.tile is None
            or not all(isfinite(x) for x in (*args.tile, args.width_km))
            or (args.width_km <= 0 or abs(args.tile[0]) >= 90 or abs(args.tile[1]) > 180)
        ):
            parser.error("--interior-guard requires the solver's finite tile center and width")
        tile = dict(center=args.tile, width_km=args.width_km)
    sys.stdout.buffer.write(decide(sys.stdin.buffer.read(), enabled=args.interior_guard, tile=tile))


if __name__ == "__main__":
    main()
