"""Replay a numerical diagnostic or a paired fresh compact phase-cache control."""

import argparse
from pathlib import Path
from types import FunctionType

from ..__main__ import local_output, save_json
from . import cavity_lifetime_trial as parent
from .full_receiver_comparison import read, sha

OUT = parent.OUT.parent.parent / "streamlined/phase-cache"
PROFILE = Path(__file__).with_name("phase_cache_profile.py")


def execute(plan, directory, ident, entry, mode, methods):
    namespace = dict(parent.execute.__globals__, WORKER=entry, OUT=OUT, MODES=methods)
    run = FunctionType(parent.execute.__code__, namespace)
    return run(plan, directory, ident, mode)


def diagnostic(work):
    locked = read(parent.OUT / "plan.json")
    assert locked["source"] == parent.source()
    ident = "DS29-0316"
    plan = locked | dict(source=locked["source"] | {"cpu_by_id": {ident: 22}})
    data = dict(
        plan,
        profile=dict(
            id=ident,
            worker_sha256=sha(PROFILE),
            launcher_sha256=sha(Path(__file__)),
            protocol_sha256=sha(OUT / "PROFILE.md"),
            parent_plan_sha256=sha(parent.OUT / "plan.json"),
        ),
    )
    save_json(OUT / "plan.json", data)
    row = execute(plan, work, ident, PROFILE, "direct", {"direct": "phase-profile"})
    profile = work / ident / "profile.json"
    if profile.is_file():
        save_json(OUT / "profile.json", read(profile))
    save_json(OUT / "profile-run.json", row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    diagnostic(local_output(args.work))


if __name__ == "__main__":
    main()
