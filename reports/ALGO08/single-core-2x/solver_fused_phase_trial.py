"""Replay the frozen collapsed-signed solver with a fused phase projection."""

import argparse
import os
import runpy
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch


SOURCE = Path(__file__).resolve()
OVERLAY = SOURCE.parents[3] / "tools/pipeline_eval/variants/algo08_fused_phase_projection.py"
HELPER = SOURCE.with_name("residual_attribution_trial.py")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SPEC_SHA256 = "sha256:99b46f7ffe4d9e2acb173364d54240c6cf8ca2deceb1d7715d389c03066659cf"
MODES = ("stock", "fused")


def worker(mode, native, spec, archive, offer, output):
    from tools.pipeline_eval.qualification import experimental_publication

    helper = runpy.run_path(str(HELPER))
    frozen_run = experimental_publication.run
    clock = Counter()
    stage = "non_grid"

    def measure_run(args, specification):
        # Start after the frozen worker installs its lazy import hook.
        from leo.presentation import localization_v3
        from tools import algo08_position

        sample = localization_v3.sample_position_grid
        bound = algo08_position.NativeBound.__call__
        measure = runpy.run_path(str(OVERLAY))["measured_phase_projection"]

        def measure_bound(self, *args, **kwargs):
            clock[f"{stage}_robust_calls"] += 1
            start = process_time_ns()
            try:
                return bound(self, *args, **kwargs)
            finally:
                clock[f"{stage}_robust_cpu_ns"] += process_time_ns() - start

        def grid(*args, **kwargs):
            nonlocal stage
            stage = "grid"
            start = process_time_ns()
            try:
                return sample(*args, **kwargs)
            finally:
                clock["complete_grid_cpu_ns"] = process_time_ns() - start
                stage = "non_grid"

        with (measure(enabled=mode == "fused", stage=lambda: stage) as counts,
              patch.object(algo08_position.NativeBound, "__call__", measure_bound),
              patch.object(localization_v3, "sample_position_grid", grid)):
            result = frozen_run(args, specification)
        clock.update(counts)
        return result

    with TemporaryDirectory() as directory:
        evidence_path = Path(directory) / "solver.json"
        with patch.object(experimental_publication, "run", measure_run):
            helper["worker"](native, spec, archive, offer, evidence_path, include_evidence=True)
        result = helper["read"](evidence_path)
    from leo.contracts.digests import canonical_digest

    evidence = result.pop("evidence")
    result["science"] = {
        name: canonical_digest({k: v for k, v in document.items()
                                if k not in ("binding", "elapsed_seconds")})
        for name, document in evidence.items()
    }
    result["grid_points"] = evidence["position_grid"]["evaluated_points"]
    helper["write"](output, dict(result, likelihood_timing=clock))


def saved_inputs(receipt_path, frozen, single_root, *, expected_spec=SPEC_SHA256):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

    helper = runpy.run_path(str(HELPER))
    read = helper["read"]
    publication = read(receipt_path)
    spec_path = frozen / "spec.json"
    spec = read(spec_path)
    if single_root is None:
        stock = publication["runs"]["candidate"]
        root = "candidate"
        original_spec = publication["candidate_specification_digest"]
        region = read(Path(publication["region"]))
    else:
        stock = publication["run"]
        root = single_root
        original_spec = publication["spec"]
        region = stock["receipt"]["region"]
    if canonical_digest(spec) != expected_spec or original_spec != expected_spec or "failure" in publication:
        raise ValueError("Expected a completed measurement from the frozen collapsed-signed build")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    archive = Path(publication["archive"]["root"])
    if archive_identity(archive) != publication["archive"]:
        raise ValueError("The historical archive differs from the saved publication")
    offer = Algo08Region.parse(region).document()
    if offer != stock["receipt"]["region"] or stock["receipt"]["decision"] != "complete":
        raise ValueError("Expected the original region and a complete published candidate")
    native = helper["saved_native"](receipt_path, root, stock)
    return publication, stock, spec_path, archive, offer, native


def run(receipt_path, frozen, output, *, single_root=None, fused_first=False):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    helper = runpy.run_path(str(HELPER))
    read, write = helper["read"], helper["write"]
    publication, stock, spec_path, archive, offer, native = saved_inputs(
        receipt_path, frozen, single_root)
    order = MODES[::-1] if fused_first else MODES
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(SOURCE), "worker"]
    results = {}
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        observations, region = scratch / "native.json", scratch / "offer.json"
        write(observations, native)
        write(region, offer)
        for mode in order:
            result = scratch / (mode + ".json")
            subprocess.run([*command, mode, *map(str, (observations, spec_path, archive, region, result))],
                           env=env, check=True, timeout=88)
            results[mode] = read(result)
    if archive_identity(archive) != publication["archive"]:
        raise ValueError("The causal archive changed during the comparison")
    original_digests = {"position_" + key: value for key, value in stock["scientific_digests"].items()}
    checks = {
        mode: dict(status=result["status"] == "ok", arms=result["arms"] == stock["arms"],
                   owners=result["owners"] == stock["owners"],
                   **{key: result["science"][key] == value for key, value in original_digests.items()})
        for mode, result in results.items()
    }
    matched = {key: results["fused"][key] == results["stock"][key]
               for key in ("status", "reason", "arms", "associated", "owners", "orbit_policy", "science")}
    write(output, dict(order=order, archive=publication["archive"], offer=offer, results=results,
                       publication_sha256=sha256(receipt_path.read_bytes()).hexdigest(),
                       native_sha256=canonical_digest(native), specification_digest=SPEC_SHA256,
                       overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest(),
                       published_checks=checks, matched=matched))
    if not all(all(mode.values()) for mode in checks.values()) or not all(matched.values()):
        raise ValueError(f"Frozen evidence comparison failed. See {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    trial = commands.add_parser("run")
    for name in ("receipt_path", "frozen", "output"):
        trial.add_argument(name, type=Path)
    trial.add_argument("--single-root")
    trial.add_argument("--fused-first", action="store_true")
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=MODES)
    for name in ("native", "spec", "archive", "offer", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)


if __name__ == "__main__":
    main()
