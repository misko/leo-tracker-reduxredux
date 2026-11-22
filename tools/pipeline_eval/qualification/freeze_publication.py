"""Freeze an isolated research launcher on top of the pinned Gauss release."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .experimental_publication import (
    CAUSAL_MODES, DISCOVERY_MODES, INGRESS_MODES, RELEASE, RENDERING_MODES, SALVAGE_MODES, TABLE_MODES,
)


LAUNCHER = Path("reports/ALGO08/single-core-2x/run-candidate")
ENTRY = Path("tools/pipeline_eval/qualification/experimental_publication.py")
VARIANTS = Path("tools/pipeline_eval/variants")


def freeze(checkout, output, detector, expected_sha256, solver, ingress, release=RELEASE, *, schedule="all",
           rendering="individual", startup="stock", paired_sha256=None, endpoint_reuse=False):
    if rendering not in RENDERING_MODES:
        raise ValueError("Unknown publication renderer")
    if ingress not in INGRESS_MODES:
        raise ValueError("Unknown experimental I/Q reader")
    if type(endpoint_reuse) is not bool:
        raise ValueError("Expected a Boolean endpoint reuse selection")
    if (paired_sha256 is not None) != (ingress == "paired-sha256"):
        raise ValueError("Paired SHA-256 ingress requires exactly one reviewed library pin")
    if paired_sha256 is not None:
        library, library_sha256 = paired_sha256
        library_bytes = library.read_bytes()
        if hashlib.sha256(library_bytes).hexdigest() != library_sha256:
            raise ValueError("Paired SHA-256 library differs from its reviewed build")
    detector_bytes = detector.read_bytes()
    if hashlib.sha256(detector_bytes).hexdigest() != expected_sha256:
        raise ValueError("Detector differs from its reviewed build")
    sources = [LAUNCHER, ENTRY]
    if startup == "lazy-exports":
        sources.append(VARIANTS / "experimental/lean_startup.py")
    if solver in CAUSAL_MODES:
        sources.append(VARIANTS / "algo08_causal_reuse.py")
    if solver in SALVAGE_MODES:
        sources.append(VARIANTS / "algo08_salvage_statistics.py")
    if solver in DISCOVERY_MODES:
        sources.append(VARIANTS / "algo08_dense_discovery.py")
    if solver in TABLE_MODES:
        sources.extend(VARIANTS / name for name in ("algo08_causal_table.py", "algo08_cavity_projection.py",
                                                     "algo08_salvage_bound.py"))
    if solver == "track-moments":
        sources.append(VARIANTS / "algo08_track_moments.py")
    if endpoint_reuse:
        sources.append(VARIANTS / "algo08_endpoint_readout.py")
    if rendering in ("shared-orbits", "shared-pixels", "raster-layout"):
        sources.append(VARIANTS / "experimental/shared_orbit_figures.py")
    if rendering == "raster-layout":
        sources.append(VARIANTS / "experimental/raster_layout.py")
    if ingress != "stock":
        sources.append(VARIANTS / "experimental/receiver_ingress.py")
    if ingress == "paired-sha256":
        sources.extend(VARIANTS / "experimental" / name for name in
                       ("paired_sha256.c", "paired_sha256.py"))
    if schedule in ("alternate", "bursts"):
        sources.append(VARIANTS / "experimental/receiver_cadence.py")
    if schedule == "deferred":
        sources.extend(VARIANTS / "experimental" / name for name in
                       ("deferred_continuation.py", "deferred_receiver.py"))
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
    if paired_sha256 is not None:
        library = output / "paired-sha256.so"
        library.write_bytes(library_bytes)
        spec["paired_sha256"] = dict(library=str(library.resolve()), sha256=library_sha256)
        digests[library.name] = library_sha256
    if rendering != "individual":
        spec["rendering"] = rendering
    if startup != "stock":
        spec["startup"] = startup
    if endpoint_reuse:
        spec["endpoint_reuse"] = True
    (output / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("detector", type=Path)
    parser.add_argument("detector_sha256")
    parser.add_argument("--solver", choices=("stock", *CAUSAL_MODES), required=True)
    parser.add_argument("--ingress", choices=INGRESS_MODES, required=True)
    parser.add_argument("--paired-sha256", nargs=2, metavar=("LIBRARY", "SHA256"))
    parser.add_argument("--schedule", choices=("all", "bursts", "alternate", "deferred"), default="all")
    parser.add_argument("--rendering", choices=RENDERING_MODES, default="individual")
    parser.add_argument("--startup", choices=("stock", "lazy-exports"), default="stock")
    parser.add_argument("--endpoint-reuse", action="store_true")
    args = parser.parse_args()
    paired = None if args.paired_sha256 is None else (Path(args.paired_sha256[0]), args.paired_sha256[1])
    freeze(Path(__file__).resolve().parents[3], args.output, args.detector, args.detector_sha256,
           args.solver, args.ingress, schedule=args.schedule, rendering=args.rendering,
           startup=args.startup, paired_sha256=paired, endpoint_reuse=args.endpoint_reuse)
