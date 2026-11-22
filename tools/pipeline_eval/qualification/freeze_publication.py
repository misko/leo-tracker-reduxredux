"""Freeze an isolated research launcher on top of the pinned Gauss release."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .experimental_publication import RELEASE


LAUNCHER = Path("reports/ALGO08/single-core-2x/run-candidate")
ENTRY = Path("tools/pipeline_eval/qualification/experimental_publication.py")
VARIANTS = Path("tools/pipeline_eval/variants")


def freeze(checkout, output, detector, expected_sha256, solver, ingress, release=RELEASE, *, schedule="all",
           rendering="individual"):
    detector_bytes = detector.read_bytes()
    if hashlib.sha256(detector_bytes).hexdigest() != expected_sha256:
        raise ValueError("Detector differs from its reviewed build")
    sources = [LAUNCHER, ENTRY]
    if solver in ("causal-reuse", "combined", "combined-shared-discovery", "shared-tables"):
        sources.append(VARIANTS / "algo08_causal_reuse.py")
    if solver in ("combined", "combined-shared-discovery", "shared-tables"):
        sources.append(VARIANTS / "algo08_salvage_statistics.py")
    if solver in ("combined-shared-discovery", "shared-tables"):
        sources.append(VARIANTS / "algo08_dense_discovery.py")
    if solver == "shared-tables":
        sources.extend(VARIANTS / name for name in ("algo08_causal_table.py", "algo08_cavity_projection.py",
                                                     "algo08_salvage_bound.py"))
    if rendering in ("shared-orbits", "shared-pixels"):
        sources.append(VARIANTS / "experimental/shared_orbit_figures.py")
    if ingress == "compressed-buffer":
        sources.append(VARIANTS / "experimental/receiver_ingress.py")
    if schedule in ("alternate", "bursts"):
        sources.append(VARIANTS / "experimental/receiver_cadence.py")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(release / "tools", output / "tools", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    digests = {}
    for name in sources:
        dest = output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checkout / name, dest)
        digests[str(name)] = hashlib.sha256(dest.read_bytes()).hexdigest()
    binary = output / "receiver.so"
    binary.write_bytes(detector_bytes)
    spec = dict(detector=str(binary.resolve()), detector_sha256=expected_sha256,
                solver=solver, ingress=ingress, schedule=schedule, sources=digests)
    if rendering != "individual":
        spec["rendering"] = rendering
    (output / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("detector", type=Path)
    parser.add_argument("detector_sha256")
    parser.add_argument("--solver", choices=("stock", "causal-reuse", "combined", "combined-shared-discovery", "shared-tables"), required=True)
    parser.add_argument("--ingress", choices=("stock", "compressed-buffer"), required=True)
    parser.add_argument("--schedule", choices=("all", "bursts", "alternate"), default="all")
    parser.add_argument("--rendering", choices=("individual", "shared-orbits", "shared-pixels"), default="individual")
    args = parser.parse_args()
    freeze(Path(__file__).resolve().parents[3], args.output, args.detector, args.detector_sha256,
           args.solver, args.ingress, schedule=args.schedule, rendering=args.rendering)
