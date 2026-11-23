"""Run one blinded-output comparison on the resident public North recording."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from north_held_anchor_pair import (HERE, PINS, STOCK, checked, environment, host, measure, preflight,
                                    publication_evidence, read, write)
from north_held_anchor_report import compare_stock, score
from north_combined import assignments


EXPECTED = "sha256:0ab06052211e6f60d7a705147d24b5e85f9366078026196e228f4be0161bdf63"
EXPECTED_RECIPE = "sha256:788cb632287f05f2e316842e5692bd8d3b18ed0f5ddaeac5e9b070bb235e9cc2"


def run(directory):
    directory.mkdir()
    env = environment(directory)
    python = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python")
    entry = HERE / "unified_short_bootstrap.py"
    args = preflight(directory)
    args["order"] = ["candidate", "stock"]
    common = ["--recording", args["recording"], "--region", args["region_file"], "--archive", args["archive"]["root"]]
    libraries = [item for flag, (path, pin) in PINS.items() for item in (flag, checked(path, pin))]
    commands = {"candidate": [python, "-BPs", entry, *common, *libraries, "--prove-empty-graph", "--one-pass-web-png",
                              "--exact-graph-reuse", "--short-lane-mask", "target", "--output", directory / "candidate"],
                "stock": [STOCK, *common, "--bulk-root", directory / "stock"]}
    write(directory / "binding.json", dict(assignment=args, machine=host(), expected_packet=EXPECTED,
          recipe=EXPECTED_RECIPE, commands={k: list(map(str, v)) for k, v in commands.items()},
          source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in
                         (entry, Path(__file__), HERE/"stereo_lane_receiver.py", HERE/"stereo_lane_schedule.py")}))
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    (directory / "stock").mkdir()
    for arm, command in commands.items():
        pages = preflight(directory)["planning_cache"]
        write(directory / f"{arm}-cache.json", pages)
        clock = measure(command, env, directory / arm)
        write(directory / f"{arm}-clock.json", clock)
        if clock["exit_code"]:
            raise RuntimeError(f"The {arm} command exited {clock['exit_code']}. See {arm}.stderr")


def seal(directory):
    from leo.contracts.digests import canonical_digest

    binding = read(directory / "binding.json")
    assignment = binding["assignment"]
    pair, _ = assignments()
    results = {}
    for arm in ("candidate", "stock"):
        output = directory / arm
        receipt = json.loads(output.with_suffix(".stdout").read_text().splitlines()[-1])
        clock = read(directory / f"{arm}-clock.json")
        if clock["exit_code"] or receipt["region"] != assignment["offered_region"]:
            raise ValueError("Unexpected process or offered region")
        if receipt["decision"] == "complete":
            result = publication_evidence(output, receipt, clock, assignment)
            if arm == "stock":
                compare_stock(receipt, result, pair["runs"]["candidate"])
            del result["native"]
        else:
            result = dict(native_sha256=canonical_digest(read(next(output.glob("fast-scan-automatic-work/*/detections.json")))))
        result.update(clock=clock, decision=receipt["decision"], cache=read(directory / f"{arm}-cache.json"))
        if arm == "candidate":
            raw = read(output / "unified-short-bootstrap.json")
            receiver = raw["receiver_audit"]
            actual = receiver["native"]
            if (raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or raw["receipt"] != receipt
                    or actual["native_calls"] != {"full": 304, "short_primary": 1312}
                    or sum(actual["omitted_by_radio"].values()) != 784 or receiver["selected"] != 713
                    or raw["detector_recipe_sha256"] != EXPECTED_RECIPE or canonical_digest(raw["receiver_recipe"]) != EXPECTED_RECIPE
                    or raw["native_sha256"] != EXPECTED or result["native_sha256"] != EXPECTED):
                raise ValueError("Live receiver does not reproduce the frozen offline target")
            result["acquisition"] = dict(counts=actual, time=raw["phases"]["authenticated_raw_acquisition"])
        results[arm] = result
    order = sorted(results, key=lambda name: results[name]["clock"]["started_unix_ns"])
    if order != ["candidate", "stock"]:
        raise ValueError("Unexpected run order for the original-I/Q control")
    write(directory / "sealed.json", dict(binding_sha256=sha256((directory/"binding.json").read_bytes()).hexdigest(),
                                          actual_run_order=order, results=results))
    if all(row["decision"] == "complete" for row in results.values()):
        score(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "seal"))
    parser.add_argument("directory", type=Path)
    options = parser.parse_args()
    (run if options.action == "run" else seal)(options.directory)
