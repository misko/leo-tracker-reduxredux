"""Run fresh source-locked compact endpoint reuse pairs through the normal entry."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import compact_endpoint
from . import cavity_reuse_trial as fixture
from . import solver_reuse_build as build
from .full_receiver_comparison import sha

REPORT = fixture.REPORT.parents[1] / "original-support/solver-reuse"
MODES = ("stock", "endpoint")
METHODS = dict(stock="v5_phase_release_exact_control", endpoint="v5_accepted_endpoint")
SCHEDULE = {
    "DS26-0026": (22, MODES),
    "DS29-0174": (23, MODES[::-1]),
    "DS26-0138": (22, MODES[::-1]),
    "DS29-0357": (23, MODES),
}
LIMIT = 180


def lock(work):
    work.mkdir()
    releases = {}
    for mode in MODES:
        root = work / mode
        files = build.install(root, enabled=mode == "endpoint")
        releases[mode] = dict(
            files=files,
            libraries={n: sha(root / n) for n in fixture.LIBRARIES},
            manifest_sha256=sha(root / "native/manifest.json"),
            public_entry_sha256=sha(root / "__main__.py"),
            package_init_sha256=sha(root / "tools/__init__.py"),
        )
    if releases["stock"]["libraries"] != releases["endpoint"]["libraries"]:
        raise ValueError("paired receiver numerical binaries differ")
    origins = (
        Path(__file__),
        Path(build.__file__),
        Path(compact_endpoint.__file__),
        Path(fixture.__file__),
        Path(fixture.observer.__file__),
        REPORT / "PROTOCOL.md",
    )
    plan = dict(
        cases=list(SCHEDULE),
        cohort="capture-era",
        schedule=SCHEDULE,
        bindings={ident: fixture.qualify_input(ident, "capture-era")[2] for ident in SCHEDULE},
        releases=releases,
        methods=METHODS,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        limit_s=LIMIT,
        nice=10,
        sources={str(p.relative_to(ROOT)): sha(p) for p in origins},
    )
    save_json(work / "plan.json", plan)
    write(REPORT / "source-lock.json", (work / "plan.json").read_bytes())
    return plan


def launch(work):
    plan = lock(work)
    print("frozen", sha(work / "plan.json"), flush=True)

    def lane(cpu):
        for ident, (pin, _) in SCHEDULE.items():
            if pin == cpu:
                fixture.run(work, plan, ident)

    with patch.multiple(fixture, METHODS=METHODS, LIMIT=LIMIT), ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, (22, 23)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    launch(parser.parse_args().work)
