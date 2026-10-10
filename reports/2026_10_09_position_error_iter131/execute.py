"""One separately frozen clean-admission successor slice, no hidden129 retry."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from inference_loader import InferenceLoader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    folder = ROOT / "reports/2026_10_09_position_error_iter129"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("execute129_for131", folder / "execute.py")
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("search", "native", "fixed"))
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--output", type=Path, default=HERE / "results/DS16-020")
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    parent.verify(plan)
    if len(plan["members"]) != 1 or plan["members"][0]["label"] != "DS16-020":
        raise ValueError("wrong successor cohort")
    member = plan["members"][0]
    entry, driver, adapter = parent.dependencies()
    backend_loader = entry.make_loader(ROOT, member["binding"])
    loader = InferenceLoader(ROOT, backend_loader.load_case)
    if args.phase == "search":
        result = parent.search_slice(plan, member, args.output / "search", loader, driver)
    else:
        result = parent.continue_slice(
            plan,
            member,
            args.phase,
            args.output / args.phase,
            args.output / "search",
            loader,
            driver,
            adapter,
        )
    print("DS16-020", args.phase, result["status"], flush=True)


if __name__ == "__main__":
    main()
