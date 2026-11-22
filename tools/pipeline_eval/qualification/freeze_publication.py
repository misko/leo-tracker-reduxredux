"""Freeze an isolated research launcher on top of the pinned Gauss release."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .experimental_publication import (
    CAUSAL_MODES, DISCOVERY_MODES, INGRESS_MODES, PNG_LIBRARIES, RELEASE, RENDERING_MODES,
    SALVAGE_MODES, TABLE_MODES,
)


LAUNCHER = Path("reports/ALGO08/single-core-2x/run-candidate")
ENTRY = Path("tools/pipeline_eval/qualification/experimental_publication.py")
VARIANTS = Path("tools/pipeline_eval/variants")


def freeze(checkout, output, detector, expected_sha256, solver, ingress, release=RELEASE, *, schedule="all",
           rendering="individual", startup="stock", paired_sha256=None, endpoint_reuse=False,
           png_filter=None, png_deflate=None, recovery_reuse=False):
    if rendering not in RENDERING_MODES:
        raise ValueError("Unknown publication renderer")
    png_pins = dict(png_filter=png_filter, png_deflate=png_deflate)
    if any((pin is not None) != (rendering == "lossless-raster") for pin in png_pins.values()):
        raise ValueError("Lossless raster rendering requires both reviewed PNG library pins")
    png_libraries = {}
    for name, pin in png_pins.items():
        if pin is not None:
            library, digest = pin
            content = library.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"{name} library differs from its reviewed build")
            png_libraries[name] = (content, digest)
    if ingress not in INGRESS_MODES:
        raise ValueError("Unknown experimental I/Q reader")
    if type(endpoint_reuse) is not bool:
        raise ValueError("Expected a Boolean endpoint reuse selection")
    if type(recovery_reuse) is not bool:
        raise ValueError("Expected a Boolean recovery reuse selection")
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
    if recovery_reuse:
        sources.append(VARIANTS / "algo08_recovery_reuse.py")
    if rendering != "individual":
        sources.append(VARIANTS / "experimental/shared_orbit_figures.py")
    if rendering in ("raster-layout", "lossless-raster"):
        sources.append(VARIANTS / "experimental/raster_layout.py")
    if rendering == "lossless-raster":
        sources.extend(VARIANTS / "experimental" / name for name in
                       ("lossless_png.py", "lossless_png.c"))
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
    for name, (content, digest) in png_libraries.items():
        library = output / PNG_LIBRARIES[name]
        library.write_bytes(content)
        spec[name] = dict(library=str(library.resolve()), sha256=digest)
        digests[library.name] = digest
    if startup != "stock":
        spec["startup"] = startup
    if endpoint_reuse:
        spec["endpoint_reuse"] = True
    if recovery_reuse:
        spec["recovery_reuse"] = True
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
    parser.add_argument("--png-filter", nargs=2, metavar=("LIBRARY", "SHA256"), type=str)
    parser.add_argument("--png-deflate", nargs=2, metavar=("LIBRARY", "SHA256"), type=str)
    parser.add_argument("--startup", choices=("stock", "lazy-exports"), default="stock")
    parser.add_argument("--endpoint-reuse", action="store_true")
    parser.add_argument("--recovery-reuse", action="store_true")
    args = parser.parse_args()
    paired = None if args.paired_sha256 is None else (Path(args.paired_sha256[0]), args.paired_sha256[1])
    png = {name: (Path(pin[0]), pin[1]) for name in PNG_LIBRARIES
           if (pin := getattr(args, name)) is not None}
    freeze(Path(__file__).resolve().parents[3], args.output, args.detector, args.detector_sha256,
           args.solver, args.ingress, schedule=args.schedule, rendering=args.rendering,
           startup=args.startup, paired_sha256=paired, endpoint_reuse=args.endpoint_reuse,
           recovery_reuse=args.recovery_reuse, **png)
