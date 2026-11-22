"""Time and compare the complete collapsed-signed research grid pointwise."""

import argparse
import os
import runpy
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch


SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[3]
OVERLAY = ROOT / "tools/pipeline_eval/variants/algo08_posterior_handoff.py"
HELPER = SOURCE.with_name("residual_attribution_trial.py")
PREVIOUS = SOURCE.with_name("solver_fused_phase_trial.py")
ARMS = ("c0", "fitted_c")
MODES = ("stock", "handoff")
REPLAY_TOLERANCE = 1e-5


def worker(mode, native, spec, archive, offer, library, output):
    from tools.pipeline_eval.qualification import experimental_publication

    helper = runpy.run_path(str(HELPER))
    original = experimental_publication.run
    timings = {}
    active = False

    def measured_run(args, spec):
        from leo.presentation import localization_v3
        from tools import algo08_position

        sample = localization_v3.sample_position_grid
        handoff = runpy.run_path(str(OVERLAY))["grid_handoff"]

        def grid(*args, **kwargs):
            nonlocal active
            active = True
            start = process_time_ns()
            try:
                return sample(*args, **kwargs)
            finally:
                timings["full_grid_cpu_ns"] = process_time_ns() - start
                active = False

        with (handoff(algo08_position, library if mode == "handoff" else None,
                      lambda: active) as stats,
              patch.object(localization_v3, "sample_position_grid", grid)):
            result = original(args, spec)
        timings.update(stats)
        return result

    with TemporaryDirectory() as temp:
        packet = Path(temp) / "evidence.json"
        with patch.object(experimental_publication, "run", measured_run):
            helper["worker"](native, spec, archive, offer, packet, include_evidence=True)
        result = helper["read"](packet)
    helper["write"](output, dict(result, timings=timings))


def compare_grid(stock, candidate):
    ignored = ("binding", "elapsed_seconds", "points")

    def meta(grid):
        return {k: v for k, v in grid.items() if k not in ignored}

    if not stock["complete"] or not candidate["complete"] or meta(stock) != meta(candidate):
        raise ValueError("Expected both complete grids with the same sampling contract")

    def point_key(row):
        return row["east_km"], row["north_km"]

    def sampled_minimum(grid, arm):
        finite = [row for row in grid["points"] if row["scores"][arm] is not None]
        return point_key(min(finite, key=lambda row: row["scores"][arm]))

    deltas = {arm: [] for arm in ARMS}
    endpoints = {arm: tuple(stock["endpoints"][arm]) for arm in ARMS}
    for before, after in zip(stock["points"], candidate["points"], strict=True):
        if {k: v for k, v in before.items() if k != "scores"} != {
                k: v for k, v in after.items() if k != "scores"}:
            raise ValueError("Grid geometry or pointwise failures changed")
        for arm in ARMS:
            first, second = before["scores"][arm], after["scores"][arm]
            if (first is None) != (second is None):
                raise ValueError("Grid score availability changed")
            if first is not None:
                deltas[arm].append((point_key(before), abs(second - first)))
    return {
        arm: dict(points=len(deltas[arm]), changed=sum(delta > 0 for _, delta in deltas[arm]),
                  max_abs_delta=max(delta for _, delta in deltas[arm]),
                  endpoint_abs_delta=dict(deltas[arm])[endpoints[arm]],
                  sampled_argmin_equal=sampled_minimum(stock, arm) == sampled_minimum(candidate, arm))
        for arm in ARMS
    }


def run(receipt, frozen, library, output, *, single_root=None, handoff_first=False):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    inputs = runpy.run_path(str(PREVIOUS))
    helper = runpy.run_path(str(HELPER))
    read, write = helper["read"], helper["write"]
    publication, original, spec, archive, offer, native = inputs["saved_inputs"](
        receipt, frozen, single_root)
    release = inputs["RELEASE"]
    envir = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        envir.pop(key, None)
    envir.update(PYTHONPATH=f"{frozen}:{release / 'src'}:{release}", OPENBLAS_NUM_THREADS="1",
                 MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(release / "venv/bin/python"), "-BPs", str(SOURCE), "worker"]
    order = MODES[::-1] if handoff_first else MODES
    results = {}
    with TemporaryDirectory() as temp:
        folder = Path(temp)
        observations, region = folder / "detections.json", folder / "offer.json"
        write(observations, native)
        write(region, offer)
        for mode in order:
            result = folder / (mode + ".json")
            paths = (observations, spec, archive, region, library, result)
            subprocess.run([*command, mode, *map(str, paths)], env=envir, check=True, timeout=88)
            results[mode] = read(result)
    if archive_identity(archive) != publication["archive"]:
        raise ValueError("The causal archive changed during the comparison")
    grid = compare_grid(*(results[mode]["evidence"]["position_grid"] for mode in MODES))
    match = {key: results["stock"][key] == results["handoff"][key]
             for key in ("status", "reason", "arms", "owners", "associated", "orbit_policy")}
    for mode, result in results.items():
        result["digests"] = {
            key: canonical_digest({k: v for k, v in doc.items()
                                   if k not in ("binding", "elapsed_seconds")})
            for key, doc in result["evidence"].items()
        }
    stock, handed = (results[mode] for mode in MODES)
    based = dict(stock_grid=stock["digests"]["position_grid"] == original["scientific_digests"]["grid"],
                 paths=all(result["digests"]["position_path"] == original["scientific_digests"]["path"]
                           for result in results.values()),
                 owners=stock["owners"] == original["owners"], arms=stock["arms"] == original["arms"],
                 endpoint_replay=stock["digests"]["objective_replay"] == handed["digests"]["objective_replay"])
    write(output, dict(order=order, archive=publication["archive"], offer=offer, results=results,
                       publication_sha256=sha256(receipt.read_bytes()).hexdigest(),
                       native_sha256=canonical_digest(native), specification_digest=inputs["SPEC_SHA256"],
                       library_sha256=sha256(library.read_bytes()).hexdigest(),
                       overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest(),
                       native_header_sha256=sha256(OVERLAY.with_suffix(".h").read_bytes()).hexdigest(),
                       matched=match, published_checks=based, grid_audit=grid,
                       score_tolerance=REPLAY_TOLERANCE, research_grid=True))
    if (not all(match.values()) or not all(based.values())
            or any(r["max_abs_delta"] > REPLAY_TOLERANCE for r in grid.values())):
        raise ValueError(f"Research grid did not meet the declared comparison. See {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    trial = commands.add_parser("run")
    for name in ("receipt", "frozen", "library", "output"):
        trial.add_argument(name, type=Path)
    trial.add_argument("--single-root")
    trial.add_argument("--handoff-first", action="store_true")
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=MODES)
    for name in ("native", "spec", "archive", "offer", "library", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)


if __name__ == "__main__":
    main()
