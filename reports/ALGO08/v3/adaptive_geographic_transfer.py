"""Apply the frozen grid layout to four previously sealed 20/8 ms maps."""

import gzip
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from reports.ALGO08.v3.adaptive_grid_screen import screen


HERE = Path(__file__).resolve().parent


def audit(root, receipt, digest):
    grid = FastStandardAnalysisStore(root).position_grid(receipt["run_id"])
    scientific = {k: v for k, v in grid.items() if k not in ("elapsed_seconds", "binding")}
    if (canonical_digest(scientific) != digest or grid["binding"]["terminal_sha256"] != receipt["terminal_sha256"]
            or not grid["complete"] or (grid["coarse_size"], grid["local_size"]) != (9, 7)):
        raise ValueError("Geographic transfer requires the original complete, bound map")
    result = screen(grid)
    return {k: v for k, v in result.items() if k != "selected_xy"}


def run():
    def read(name):
        with gzip.open(HERE / "measurements" / (name + ".json.gz"), "rt") as handle:
            return json.load(handle)

    north = read("eight-ms-native-live")
    south = read("eight-ms-south-transfer")["documents"]
    results = {}
    for offer, key, child, owner in (("containing", "scientific_seal", "containing", "raw"),
                                      ("100m-omitted", "omitted_score", "omitted", "published")):
        item = north[key]
        results["North " + offer] = audit(Path("/dev/shm/leo-v3-eight-ms-native-north02") / child,
                                           item[owner]["receipt"], item["science"]["grid_and_path"]["grid"])
    for offer, key, child, owner in (("containing", "seal.json", "containing", "raw"),
                                      ("100m-omitted", "omitted-seal.json", "near-omitted", "saved")):
        item = south[key]
        results["South " + offer] = audit(Path("/dev/shm/leo-v3-eight-ms-south-result01") / child,
                                           item[owner]["receipt"], item["observation"]["evidence"]["scientific_digests"]["grid"])
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
