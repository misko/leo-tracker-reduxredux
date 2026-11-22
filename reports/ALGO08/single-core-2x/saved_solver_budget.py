"""Estimate a raw-publication CPU budget by replacing only a measured saved solve."""
import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.paired_publication import verify_sources
from .solver_fused_phase_trial import HELPER, RELEASE, saved_inputs


def budget(deployed_cpu, parent_cpu, old_solver, new_solver):
    if not all(math.isfinite(v) and v > 0 for v in (deployed_cpu, parent_cpu, old_solver, new_solver)):
        raise ValueError("All CPU timings must be positive and finite")
    if old_solver >= parent_cpu:
        raise ValueError("The saved solver must fit inside the measured full pipeline")
    outer = parent_cpu - old_solver
    return dict(estimated_outer_cpu_s=outer, solver_budget_for_2x_cpu_s=deployed_cpu / 2 - outer,
                estimated_total_cpu_s=outer + new_solver,
                estimated_seconds_above_half=outer + new_solver - deployed_cpu / 2)


def outer_options(spec):
    """Frozen I/Q ingress, acquisition and rendering checks shared by the two solves."""
    fields = ("detector_sha256", "rendering", "startup", "ingress", "schedule")
    keys = ("paired_sha256", "png_filter", "png_deflate")
    return ([spec.get(k) for k in fields], [spec.get(k, {}).get("sha256") for k in keys],
            {k: v for k, v in spec["sources"].items() if any(name in k for name in (
                "experimental/receiver_", "experimental/paired_sha256", "experimental/lossless_png",
                "experimental/raster_layout", "experimental/lean_startup", "experimental/shared_orbit_figures"))})


def run(pair_path, parent, successor, expected, comparison, case):
    stored = json.loads(comparison.read_bytes())
    historic = stored["cases"][case]
    pair, original, _, archive, offer, native = saved_inputs(
        pair_path, parent, None, expected_spec=stored["specifications"]["control"])
    if (sha256(pair_path.read_bytes()).hexdigest() != historic["pair_sha256"]
            or canonical_digest(native) != historic["native_sha256"]
            or offer != historic["offer"] or pair["archive"] != historic["archive"]):
        raise ValueError("Historical solver timing and raw pair use different inputs")
    prior = historic["runs"]["control"]
    if any(prior[k] != original[k] for k in ("arms", "owners", "scientific_digests")):
        raise ValueError("Historical saved solve differs from the original publication")
    config = successor / "spec.json"
    spec = json.loads(config.read_bytes())
    if canonical_digest(spec) != expected or outer_options(spec) != outer_options(pair["candidate_specification"]):
        raise ValueError("Expected the pinned successor and unchanged receiver and rendering configuration")
    verify_sources(successor / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        for name, doc in (("native", native), ("region", offer)):
            (scratch / name).write_text(json.dumps(doc, allow_nan=False))
        output = scratch / "solved"
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (successor, RELEASE / "src", RELEASE))),
                   OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
        subprocess.run([str(RELEASE / "venv/bin/python"), "-BPs", str(HELPER), "worker",
                        str(scratch / "native"), str(config), str(archive), str(scratch / "region"), str(output),
                        "--evidence"], env=env, check=True, timeout=180)
        result = json.loads(output.read_bytes())
    same_publication_work = result["status"] == "ok" and original["receipt"]["decision"] == "complete"
    deployed = pair["runs"]["baseline"]["cpu_s"]
    return dict(case=case, pair_sha256=historic["pair_sha256"], native_sha256=historic["native_sha256"],
                parent=stored["specifications"]["control"], successor=expected, archive=pair["archive"],
                region=offer, deployed_raw_cpu_s=deployed, parent_raw_cpu_s=original["cpu_s"],
                parent_solver_cpu_s=prior["cpu_s"], new_solve=result,
                cpu_estimate=budget(deployed, original["cpu_s"], prior["cpu_s"], result["solver_cpu_s"])
                if same_publication_work else None)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("pair", "parent", "successor", "historical_comparison"):
        cli.add_argument(name, type=Path)
    cli.add_argument("successor_digest")
    cli.add_argument("case")
    args = cli.parse_args()
    print(json.dumps(run(args.pair, args.parent, args.successor, args.successor_digest,
                         args.historical_comparison, args.case), indent=2, allow_nan=False))
