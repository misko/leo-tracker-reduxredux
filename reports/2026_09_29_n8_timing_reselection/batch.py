import concurrent.futures
import json
import sys

from run import HERE, REPORTS, ROOT, module, read, sha

if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        paths = [
            ROOT / p
            for p in read(REPORTS / "2026_09_29_timing_reselection/manifest.json")["hashes"]
        ]
        paths.extend(HERE.glob("*.py"))
        paths.extend([HERE / "PROTOCOL.md", REPORTS / "2026_09_29_timing_reselection/run.py"])
        for ds in ("DS7", "DS8", "DS9"):
            for w in ("early", "middle", "late"):
                paths.append(
                    REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_{w}.json"
                )
        with (HERE / "manifest.json").open("x") as out:
            json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), out, indent=2)
    else:
        batch = module("batch", REPORTS / "2026_09_29_information_selection/batch.py")
        batch.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(batch.worker, ("DS7", "DS8", "DS9")))
