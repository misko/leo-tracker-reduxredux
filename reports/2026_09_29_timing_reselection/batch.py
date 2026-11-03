import concurrent.futures
import json
import sys

from run import HERE, REPORTS, ROOT, module, read, sha

if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        paths = [
            ROOT / p for p in read(REPORTS / "2026_09_29_wide_start_audit/manifest.json")["hashes"]
        ]
        paths.extend(HERE.glob("*.py"))
        paths.append(HERE / "PROTOCOL.md")
        paths.extend(
            REPORTS / f"2026_09_29_wide_start_audit/{d}.json" for d in ("DS7", "DS8", "DS9")
        )
        with (HERE / "manifest.json").open("x") as out:
            json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), out, indent=2)
    else:
        batch = module("batch", REPORTS / "2026_09_29_information_selection/batch.py")
        batch.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(batch.worker, ("DS7", "DS8", "DS9")))
