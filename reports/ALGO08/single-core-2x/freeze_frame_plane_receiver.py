"""Replace only the verified receiver in the frozen sparse-ranking research build."""

import argparse
import shutil
from pathlib import Path

from leo.contracts.digests import canonical_digest

from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import write
from .sparse_fir_successor import RECEIVER, SOURCE, files

PARENT = "sha256:cc63459af6fb2c748c04fd0ea6810a5044ce77ef7c8286424717cddbfd6916a1"
PLANES = Path("tools/pipeline_eval/variants/experimental/receiver_frame_planes.inc")


def freeze(parent, candidate, expected, bundle, receipt):
    require_spec(parent, PARENT)
    original = read(parent / "spec.json")
    build = read(candidate.parent / "build.json")
    if (digest(candidate) != expected or digest(parent / RECEIVER) != original["detector_sha256"]
            or original["sources"][str(RECEIVER)] != original["detector_sha256"]
            or build["candidate_sha256"] != expected
            or build["tiled_fir"]["tile.so"] != original["detector_sha256"]
            or build["sources"][PLANES.name] != digest(SOURCE / PLANES)):
        raise ValueError("Unexpected receiver in build or parent")
    original_files = files(parent)
    shutil.copytree(parent, bundle, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(candidate, bundle / RECEIVER)
    shutil.copyfile(SOURCE / PLANES, bundle / PLANES)
    pins = {str(RECEIVER): expected, str(PLANES): digest(bundle / PLANES)}
    spec = dict(original, detector=str(bundle / RECEIVER), detector_sha256=expected,
                sources=original["sources"] | pins)
    for name, pin in original.items():
        if isinstance(pin, dict) and set(pin) == {"library", "sha256"}:
            destination = bundle / Path(pin["library"]).relative_to(parent)
            if digest(destination) != pin["sha256"]:
                raise ValueError(f"Changed shared library {name}")
            spec[name] = dict(pin, library=str(destination))
    (bundle / "spec.json").unlink()
    write(bundle / "spec.json", spec)
    identity = canonical_digest(spec)
    require_spec(bundle, identity)
    after = files(bundle)
    changed = {path for path in after if after[path] != original_files.get(path)}
    if changed != {PLANES, RECEIVER, Path("spec.json")} or original_files.keys() - after.keys():
        raise ValueError("Unrelated files changed in receiver freeze")
    write(receipt, dict(specification=identity, parent_specification=PARENT,
                        changed_files=sorted(map(str, changed)), receiver_sha256=expected,
                        frame_planes_source_sha256=pins[str(PLANES)], spec=spec))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("expected")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("receipt", type=Path)
    freeze(**vars(parser.parse_args()))
