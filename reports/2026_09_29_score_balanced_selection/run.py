"""Reuse the previous matched fitting/evaluation driver with an explicit selector."""

import importlib.util
import json
import sys
from pathlib import Path

from score_selector import choose

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "2026_09_29_information_selection"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main(ds):
    sys.path.insert(0, str(PARENT))
    driver = load("information_driver", PARENT / "run.py")
    data = json.loads((HERE.parent / f"2026_09_29_scan_disagreement/{ds}.json").read_text())
    assert len(data["rows"]) == 24 and all(r["qualified"] for r in data["rows"])
    old = json.loads((HERE.parent / f"2026_09_29_scan_budget/{ds}_n24_0.json").read_text())
    assert [r["session_id"] for r in data["rows"]] == old["sessions"]
    h = [r["profiled_hessian"] for r in data["rows"]]
    g = [r["profiled_gradient"] for r in data["rows"]]
    driver.HERE = HERE
    driver.greedy = lambda information, count: choose(information, h, g, count)
    driver.main(ds)


if __name__ == "__main__":
    main(sys.argv[1])
