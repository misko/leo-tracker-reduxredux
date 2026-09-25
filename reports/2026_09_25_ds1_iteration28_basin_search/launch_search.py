#!/usr/bin/env python3
"""Require the sealed fresh-anchor gate, then launch the unchanged search runner."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run.py"
EQUIVALENCE = HERE / "equivalence.json"


def main() -> None:
    spec = importlib.util.spec_from_file_location("i28_launch_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise ImportError(RUNNER)
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    record = runner.verified_json(EQUIVALENCE)
    if (
        record.get("schema") != "ds1-iteration28-anchor-equivalence/v1"
        or record.get("gate", {}).get("passed") is not True
        or record.get("bindings", {}).get("plan") != runner.digest(runner.PLAN)
        or record.get("bindings", {}).get("runner") != runner.digest(RUNNER)
        or record.get("truth_used") is not False
        or record.get("held_used") is not False
    ):
        raise ValueError("sealed fresh-anchor equivalence gate is required")
    environment = dict(os.environ)
    for name in (
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OMP_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        environment[name] = "1"
    os.execve(
        sys.executable,
        [sys.executable, str(RUNNER), "--stage", "search", "--workers", "4"],
        environment,
    )


if __name__ == "__main__":
    main()
