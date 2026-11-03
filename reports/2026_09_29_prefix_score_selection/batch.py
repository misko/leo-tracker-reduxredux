import concurrent.futures
import hashlib
import json
import sys

from run import HERE, REPORTS, ROOT, module, partition, read


def prepare():
    pool = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    targets = read(REPORTS / "2026_09_29_out_of_pool/manifest.json")
    units = []
    for ds in ("DS7", "DS8", "DS9"):
        scans = next(s for s in pool["sets"] if s["dataset"] == ds and s["count"] == 24)["scans"]
        units.append(
            dict(dataset=ds, **partition(scans, [t for t in targets["sets"] if t["dataset"] == ds]))
        )
    previous = read(REPORTS / "2026_09_29_score_balanced_selection/manifest.json")
    paths = [ROOT / p for p in previous["hashes"]]
    paths.extend(HERE.glob("*.py"))
    paths.append(HERE / "PROTOCOL.md")
    paths.extend(
        [
            REPORTS / "2026_09_29_scan_disagreement/study.py",
            REPORTS / "2026_09_29_score_balanced_selection/score_selector.py",
        ]
    )
    for ds in ("DS7", "DS8", "DS9"):
        paths.append(REPORTS / f"2026_09_29_time_balanced_scans/grid_{ds}_contiguous_early.json")
    with (HERE / "manifest.json").open("x") as f:
        json.dump(
            dict(
                config=pool["config"],
                units=units,
                hashes={
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in paths
                },
            ),
            f,
            indent=2,
        )
    print([(u["dataset"], len(u["scans"]), len(u["targets"])) for u in units])


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        driver = module("batch_driver", REPORTS / "2026_09_29_information_selection/batch.py")
        driver.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(driver.worker, ("DS7", "DS8", "DS9")))
