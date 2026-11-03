import concurrent.futures
import hashlib
import json
import sys

from run import HERE, PARENT, load


def prepare():
    root = HERE.parents[1]
    previous = json.loads((PARENT / "manifest.json").read_text())
    paths = [root / p for p in previous["hashes"]]
    paths.extend(HERE.glob("*.py"))
    paths.append(HERE / "PROTOCOL.md")
    paths.extend(
        [PARENT / "run.py", PARENT / "batch.py", PARENT / "summarize.py", PARENT / "selection.py"]
    )
    for ds in ("DS7", "DS8", "DS9"):
        paths.extend(
            [HERE.parent / f"2026_09_29_scan_disagreement/{ds}.json", PARENT / f"{ds}.json"]
        )
    with (HERE / "manifest.json").open("x") as f:
        json.dump(
            dict(
                hashes={
                    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in paths
                }
            ),
            f,
            indent=2,
        )


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        driver = load("batch_driver", PARENT / "batch.py")
        driver.HERE = HERE
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(driver.worker, ("DS7", "DS8", "DS9")))
