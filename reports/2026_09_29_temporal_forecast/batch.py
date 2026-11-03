import concurrent.futures
import json
import sys

from run import HERE, REPORTS, ROOT, check_partition, module, read, sha


def prepare():
    old = read(REPORTS / "2026_09_29_information_selection/manifest.json")
    paths = [ROOT / p for p in old["hashes"]]
    paths.extend(HERE.glob("*.py"))
    paths.append(HERE / "PROTOCOL.md")
    pool = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    for ds in ("DS7", "DS8", "DS9"):
        check_partition(
            next(s for s in pool["sets"] if s["dataset"] == ds and s["count"] == 24)["scans"]
        )
        for window in ("early", "middle"):
            paths.append(
                REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{window}.json"
            )
    with (HERE / "manifest.json").open("x") as f:
        json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), f, indent=2)


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        batch = module("batch", REPORTS / "2026_09_29_information_selection/batch.py")
        batch.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(batch.worker, ("DS7", "DS8", "DS9")))
