"""Replace only the terminal-guard bundle's receiver with verified spectral vectors."""

import argparse
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest

from .receiver_cfo_wrap_build import FULL_RESTORATION_SHA
from .receiver_spectral_vectors_check import CANDIDATE_SHA, GROUPS
from .receiver_spectral_vectors_trial import REFERENCE_SHA
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import write
from .sparse_fir_successor import RECEIVER, SOURCE, files


PARENT_SHA = "sha256:977e7dd61c23622cc05365f0a7743a0042a7edd590d88173faeace8590ca8fe3"
SOURCES = {
    Path("tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.inc"):
        "779d863a56ce9cfd1fa0fed80ef31115a9040307ca06df68839c0db7be27eee8",
    Path("tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.py"):
        "c7b0c83c2a2b10d48ce3e4cb8cc750d0bdbf2b0f025e0a640ae0ee0b1d145203",
}
TIMING_OBJECT_SHA = "5ffc8eb34785b7d20535549da23ba521cf954f86b6cfabce96c0c71ac664292d"
TIMING_SOURCE_SHA = "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a"
REGRESSION = {
    2661: "ee619bf07c5eb176daddbe898be46765f7598170d1da7aa0d93bb2636dcc3303",
    3298: "3394d88612bed587864339f4b1298afd291aa20eca01a2fa01d5c9339623bd5c",
    3869: "4eb75ee03f52878d9b284eebadef6583e9639a94b651f03585ec231365d6c8ce",
}


def factor_parity(groups):
    for batch in groups.values():
        counts = batch["paired"]["reference_to_packed"]["counts"]
        if counts["lanes_changed"] or counts["continuation_changed"]:
            raise ValueError("Changed receiver evidence in the comparison receipt")


def verify_evidence(bench, candidate):
    paths = {kind: bench / name for kind, name in (
        ("native", "spectral-vectors-combined-v1.json"),
        ("generated", "spectral-vectors-generated.json"),
        ("regression", "spectral-vectors-regression.json"),
    )}
    docs = {name: read(path) for name, path in paths.items()}
    build = docs["native"]["build"]
    packed = build["builds"]["packed"]
    generated = docs["generated"]
    regression = docs["regression"]
    native = docs["native"]["native"]["samples"]
    if (digest(candidate) != CANDIDATE_SHA or packed["library_sha256"] != CANDIDATE_SHA
            or build["reference_sha256"] != REFERENCE_SHA
            or packed["timing_object_sha256"] != TIMING_OBJECT_SHA
            or digest(candidate.parent / "timing_first_receiver.o") != TIMING_OBJECT_SHA
            or packed["timing_source_sha256"] != TIMING_SOURCE_SHA
            or digest(candidate.parent / "timing_first_receiver.c") != TIMING_SOURCE_SHA
            or generated["reference_sha256"] != REFERENCE_SHA
            or generated["candidate_sha256"] != CANDIDATE_SHA
            or regression["restored_sha256"] != FULL_RESTORATION_SHA
            or regression["candidate_sha256"] != CANDIDATE_SHA):
        raise ValueError("Unexpected receiver or timing object lineage")
    if ({row["visit"]: row["factor_sha256"] for row in regression["rows"]} != REGRESSION
            or len(regression["rows"]) != 3):
        raise ValueError("The wrapped CFO regression receipt changed")
    if ({name: row["lane_configurations"] for name, row in native.items()} != {
        "ds26-weak": 36, "austin-physical-zero": 4, "austin-physical-offset": 4,
        "austin-null-zero": 4, "austin-null-offset": 4,
    } or {name: row["lane_configurations"] for name, row in generated["groups"].items()} != {
        name: 8 for name in GROUPS
    }):
        raise ValueError("Expected all archived and generated comparison groups")
    factor_parity(native)
    factor_parity(generated["groups"])
    return {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()}


def freeze(bench, parent, candidate, bundle, receipt):
    require_spec(parent, PARENT_SHA)
    original = read(parent / "spec.json")
    if original["detector_sha256"] != REFERENCE_SHA or digest(parent / RECEIVER) != REFERENCE_SHA:
        raise ValueError("The terminal guard parent carries a different receiver")
    evidence = verify_evidence(bench, candidate)
    for path, expected in SOURCES.items():
        if digest(SOURCE / path) != expected:
            raise ValueError(f"Spectral vector source differs from its pin: {path}")
    if bundle.exists() or receipt.exists():
        raise ValueError("Expected new successor and receipt paths")
    old_files = files(parent)
    pins = original["sources"] | {str(RECEIVER): CANDIDATE_SHA} | {
        str(path): value for path, value in SOURCES.items()
    }
    spec = original | {"detector": str(bundle / RECEIVER), "detector_sha256": CANDIDATE_SHA,
                       "sources": pins}
    for name, pin in original.items():
        if isinstance(pin, dict) and set(pin) == {"library", "sha256"}:
            relative = Path(pin["library"]).relative_to(parent)
            if digest(parent / relative) != pin["sha256"]:
                raise ValueError(f"Inherited library pin differs: {name}")
            spec[name] = pin | {"library": str(bundle / relative)}
    successor = canonical_digest(spec)
    with TemporaryDirectory(prefix=".spectral-freeze-", dir=bundle.parent) as temporary:
        stage = Path(temporary) / "bundle"
        shutil.copytree(parent, stage, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(candidate, stage / RECEIVER)
        for path in SOURCES:
            destination = stage / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, destination)
        (stage / "spec.json").unlink()
        write(stage / "spec.json", spec)
        require_spec(stage, successor)
        new_files = files(stage)
        changed = {path for path, value in new_files.items() if old_files.get(path) != value}
        if changed != {RECEIVER, Path("spec.json"), *SOURCES} or old_files.keys() - new_files.keys():
            raise ValueError("An unrelated parent file changed during the receiver freeze")
        stage.rename(bundle)
    write(receipt, dict(
        specification=successor, parent_specification=PARENT_SHA, changed_files=sorted(map(str, changed)),
        receiver_sha256=CANDIDATE_SHA, receiver_evidence=evidence, spec=spec,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bench", "parent", "candidate", "bundle", "receipt"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    freeze(**vars(parser.parse_args()))
