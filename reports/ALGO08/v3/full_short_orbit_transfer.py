"""Test the live quadratic solver on the first archived v3 interpolation exit."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import runpy
import subprocess
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import BENCH, PAYLOAD, RELEASE, machine, read, write


HERE = Path(__file__).resolve().parent
PAIR = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications/DS30-0022/pair.json")
PAIR_SHA = "1984f1a54654b2ac9798599dd13a3de29506ce104650ef9237bdede5d413f0a4"
GUARD = HERE.parents[2] / "tools/pipeline_eval/variants/v5_orbit_domain.py"
GUARD_SHA = "14be68cd3af6906dbe0df64841e6a756e93caf234ad11b553bd1d8937fc2e18f"


def task_request():
    if sha256(PAIR.read_bytes()).hexdigest() != PAIR_SHA:
        raise ValueError("Archived pair assignment changed")
    pair = read(PAIR)
    frozen = BENCH / "integration-exact-curved-lookahead"
    original = runpy.run_path(str(HERE.parent / "single-core-2x/solver_orbit_support_trial.py"))
    archive, region = Path(pair["archive"]["root"]), Path(pair["region"])
    _, _, binding = original["verify"](frozen, PAIR, read(frozen / "spec.json"), archive, region)
    if not binding["identical_probe_rows"]:
        raise ValueError("Historical v3 packet differs from the corresponding v2 observations")
    native, = (PAIR.parent / "candidate/fast-scan-automatic-work").glob("*/detections.json")
    return dict(recording=pair["recording"], archive=str(archive), region=str(region), native=str(native),
                binding=binding, pair_sha256=PAIR_SHA)


def child(root, mode):
    import joint_publication as publication
    from full_short_raw import graph_config

    req = read(root / "request.json")
    args = SimpleNamespace(recording=Path(req["recording"]), archive=Path(req["archive"]), region=Path(req["region"]),
                           output=root / mode, saved=Path(req["native"]), saved_digest=req["binding"]["source_digest"],
                           optimized_full_catalogue=True, verify_images=True)
    entries = []
    original = publication.configuration
    with ExitStack() as stack:
        def config():
            result = original()
            if mode == "guard":
                from tools import algo08_position
                if sha256(GUARD.read_bytes()).hexdigest() != GUARD_SHA:
                    raise ValueError("Unexpected orbit support implementation")
                support = runpy.run_path(str(GUARD))["corner_support"]

                @contextmanager
                def observed():
                    with support() as counters:
                        entries.append(counters)
                        yield

                stack.enter_context(patch.object(algo08_position, "corner_support", observed))
            return result

        stack.enter_context(patch.object(publication, "configuration", config))
        try:
            publication.run(args, track_config=graph_config, early_regional=True, keep_selected_rows=True)
        finally:
            write(root / f"{mode}-support.json", entries)


def launch(root, mode):
    release_paths = (HERE, PAYLOAD, RELEASE / "src", RELEASE, HERE.parents[2])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, release_paths)))
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = perf_counter()
    result = subprocess.run([RELEASE / "venv/bin/python", "-BPs", __file__, mode, root], env=env,
                            capture_output=True, text=True, timeout=180)
    wall = perf_counter() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    status = dict(exit_code=result.returncode, elapsed_s=wall, cpu_s=after.ru_utime-before.ru_utime+after.ru_stime-before.ru_stime,
                  stderr=result.stderr, stdout=result.stdout)
    write(root / f"{mode}-process.json", status)
    return status


def is_interpolation_failure(result):
    return (result["exit_code"] != 0 and
            result["stderr"].rstrip().endswith("ValueError: orbit phase interpolation never extrapolates"))


def run(root):
    host = machine()
    if host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"] or set(host["threads"].values()) != {"1"}:
        raise ValueError("Use the shared low-priority Gauss slot")
    root.mkdir(exist_ok=False)
    write(root / "request.json", task_request())
    write(root / "host.json", host)
    direct = launch(root, "current")
    if is_interpolation_failure(direct):
        launch(root, "guard")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("run", "current", "guard"))
    cli.add_argument("output", type=Path)
    options = cli.parse_args()
    if options.mode == "run":
        run(options.output)
    else:
        child(options.output, options.mode)
