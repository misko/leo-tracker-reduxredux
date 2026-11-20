"""Replay the sealed phase-support plan using a local, separate output directory."""

import argparse
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output
from . import phase_support_trial as trial

_frozen_setup = trial.setup


def setup(full, bundle):
    inputs, jobs, plan = _frozen_setup(full, bundle)
    for (query, _), _policy in jobs:
        recording = query["recording"]
        if recording not in inputs:
            inputs[recording] = trial.base.native._load_case(recording)
    return inputs, jobs, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--seconds", type=int, default=480)
    args = parser.parse_args()
    work = local_output(args.work)
    with patch.object(trial, "setup", setup):
        trial.run(work, args.full, args.seconds)
    trial.seal(work, work / "sealed")


if __name__ == "__main__":
    main()
