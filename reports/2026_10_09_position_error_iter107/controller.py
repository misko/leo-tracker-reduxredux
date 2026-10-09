"""Reuse the frozen six-slice controller for a full-cohort member."""

import argparse
import importlib.util
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "controller105_for107", HERE.parent / "2026_10_09_position_error_iter105/controller.py"
)
CONTROLLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROLLER)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(name + "=1 required")
    print(CONTROLLER.run_member(args.label, here=HERE), flush=True)


if __name__ == "__main__":
    main()
