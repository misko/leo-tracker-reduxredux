"""Compare the fixed-alias layout with frozen shared-tables on one saved pair."""

import argparse
import json
import os
import runpy
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SOURCE = Path(__file__).resolve()
OVERLAY = SOURCE.parents[3] / "tools/pipeline_eval/variants/algo08_fixed_alias_layout.py"
HELPER = SOURCE.with_name("residual_attribution_trial.py")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
SPEC_SHA256 = "sha256:65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6"
MODES = ("stock", "direct")


def worker(mode, native, spec, archive, offer, output):
    from tools.pipeline_eval.qualification import experimental_publication

    helper = runpy.run_path(str(HELPER))
    frozen_run = experimental_publication.run
    counts = {}

    def measure_run(args, specification):
        # The saved-input worker installs the frozen startup hook first.
        measure = runpy.run_path(str(OVERLAY))["measured_fixed_alias_layout"]
        with measure(enabled=mode == "direct") as recorded:
            result = frozen_run(args, specification)
        counts.update(recorded)
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
    helper["write"](output, dict(result, constructor=counts))


def run(pair_path, frozen, output, *, direct_first):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity, verify_sources

    helper = runpy.run_path(str(HELPER))
    read, write = helper["read"], helper["write"]
    pair = read(pair_path)
    spec_path = frozen / "spec.json"
    spec = read(spec_path)
    if (canonical_digest(spec) != SPEC_SHA256 or spec != pair["candidate_specification"]
            or pair["candidate_specification_digest"] != SPEC_SHA256 or "failure" in pair):
        raise ValueError("Expected a completed result from the reviewed shared-tables release")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    archive = Path(pair["archive"]["root"])
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("The verified causal archive differs from the saved pair")
    receipt = pair["runs"]["candidate"]
    offer = Algo08Region.parse(read(Path(pair["region"]))).document()
    if offer != receipt["receipt"]["region"] or receipt["receipt"]["decision"] != "complete":
        raise ValueError("Expected the original offer and a complete published candidate")
    native = helper["saved_native"](pair_path, "candidate", receipt)

    order = MODES[::-1] if direct_first else MODES
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(SOURCE), "worker"]
    results = {}
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        observations, region = scratch / "native.json", scratch / "offer.json"
        write(observations, native)
        write(region, offer)
        for mode in order:
            result = scratch / (mode + ".json")
            paths = (observations, spec_path, archive, region, result)
            subprocess.run([*command, mode, *map(str, paths)], env=env, check=True, timeout=88)
            results[mode] = read(result)
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("The causal archive changed during the comparison")
    control_digest = dict(position_grid=receipt["scientific_digests"]["grid"],
                          position_path=receipt["scientific_digests"]["path"])
    checks = {
        mode: dict(status=result["status"] == "ok", arms=result["arms"] == receipt["arms"],
                   owners=result["owners"] == receipt["owners"],
                   **{k: result["science"][k] == v for k, v in control_digest.items()})
        for mode, result in results.items()
    }
    matched = {key: results["direct"][key] == results["stock"][key]
               for key in ("status", "reason", "arms", "associated", "owners", "orbit_policy", "science")}
    write(output, dict(order=order, archive=pair["archive"], offer=offer, results=results,
                       pair_sha256=sha256(pair_path.read_bytes()).hexdigest(),
                       native_sha256=canonical_digest(native), specification_digest=SPEC_SHA256,
                       overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest(),
                       published_checks=checks, matched=matched))
    if not results["direct"]["constructor"]["direct_layouts"]:
        raise ValueError(f"Replay did not exercise the direct layout. See {output}")
    if not all(all(mode.values()) for mode in checks.values()) or not all(matched.values()):
        raise ValueError(f"Exact evidence comparison failed. See {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    trial = commands.add_parser("run")
    for name in ("pair_path", "frozen", "output"):
        trial.add_argument(name, type=Path)
    trial.add_argument("--direct-first", action="store_true")
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=MODES)
    for name in ("native", "spec", "archive", "offer", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("action")](**args)


if __name__ == "__main__":
    main()
