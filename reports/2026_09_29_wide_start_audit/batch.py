import concurrent.futures
import json
import sys

from run import HERE, REPORTS, ROOT, module, read, sha

if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prior = read(REPORTS / "2026_09_29_information_selection/manifest.json")
        paths = [ROOT / name for name in prior["hashes"]]
        paths.extend(HERE.glob("*.py"))
        paths.append(HERE / "PROTOCOL.md")
        with (HERE / "manifest.json").open("x") as out:
            json.dump(dict(hashes={str(p.relative_to(ROOT)): sha(p) for p in paths}), out, indent=2)
    else:
        batch = module("batch", REPORTS / "2026_09_29_information_selection/batch.py")
        batch.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(batch.worker, ("DS7", "DS8", "DS9")))
