"""Read-only ALGO08 location-prior intervention, one process per condition."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from leo.contracts.position_grid import binding
from leo.contracts.position_path import validate
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position as deployed


STOCK_SEARCH = (37.906, -122.545)
STOCK_SCREEN = (37.5, -122.0)
FAR = (39.74, -104.99)
CASES = {
    "stock": (STOCK_SEARCH, STOCK_SCREEN),
    "overlap": ((37.906, -122.505), STOCK_SCREEN),
    "omit": ((38.506, -122.545), STOCK_SCREEN),
    "far": (FAR, FAR),
    "screen_only": (STOCK_SEARCH, FAR),
}


def replay(case, native_path, assets, archive, manifest):
    search, screen = CASES[case]
    raw = native_path.read_bytes()
    row = dict(case=case, search=search, screen=screen,
               input_file_sha256=hashlib.sha256(raw).hexdigest())
    region_type, prepare, packet = deployed.SearchRegion, deployed.prepare_native_scan, deployed.selected_packet

    def region(center, width_km):
        assert center == STOCK_SEARCH and width_km == 25
        return region_type(search, width_km)

    def preparation(*args, **kwargs):
        assert (kwargs["screen_latitude_deg"], kwargs["screen_longitude_deg"]) == STOCK_SCREEN
        data = prepare(*args, **dict(kwargs, screen_latitude_deg=screen[0], screen_longitude_deg=screen[1]))
        if data["status"] == "inputs_prepared":
            norads = sorted(int(n) for n in data["sky"]["bank"]["norad"])
            row.update(satellites=len(norads), catalogue_members_sha256=hashlib.sha256(
                json.dumps(norads).encode()).hexdigest(), tracks=len(data["tracks"]["tracks"]))
        return data

    def inspect_packet(*args):
        # Record presentation failures separately so the numerical decision is observable.
        try:
            p = packet(*args)
            row.update(grid_center=p["position_grid"]["region_center"],
                       path_center=p["position_path"]["region_center"])
            check = dict(manifest, arms=p["arms"])
            validate(dict(p["position_path"], binding=binding(check)), check)
            row["path_check"] = "passed"
            return p
        except Exception as exc:
            row["presentation_error"] = f"{type(exc).__name__}: {exc}"
            return None

    with (patch.object(deployed, "SearchRegion", region),
          patch.object(deployed, "prepare_native_scan", preparation),
          patch.object(deployed, "selected_packet", inspect_packet)):
        try:
            result, _, policy = deployed.solve(json.loads(raw), TleArchiveReader(archive), assets)
            row.update(status=result["status"], reason=result.get("reason"), arms=result["arms"], policy=policy)
        except Exception as exc:
            row.update(status="execution_error", reason=f"{type(exc).__name__}: {exc}")
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("detections", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--assets", type=Path, default=Path("/opt/leo-algo08/current/assets"))
    parser.add_argument("--archive", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    print(json.dumps(replay(args.case, args.detections, args.assets, args.archive,
                            json.loads(args.manifest.read_bytes())), allow_nan=False))
