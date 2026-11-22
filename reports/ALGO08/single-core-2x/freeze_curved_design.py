"""Freeze the measured curved-design solver over the exact selected-score receiver."""

import argparse
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.experimental_publication import (
    CURVED_DESIGN_SHA256,
    CURVED_DESIGN_SOURCE,
    RELEASE,
)
from tools.pipeline_eval.qualification.freeze_publication import ENTRY

from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import MEASUREMENTS, write
from .sparse_fir_successor import RECEIVER, SOURCE, files

PARENT = "sha256:e819d432e87d84f9f03e6df8e147fc7d2894e776c1db9e23e9b84113cb1e9e71"
PARENT_RECEIPT = MEASUREMENTS / "fractional-absolute-selected-v3-freeze.json"
ENTRY_SHA256 = "6cd8b8c8ad4ff9eead52905e9e96385044303ad7da1e5738ed88443ad83bff4c"
SAVED_SOLVES = MEASUREMENTS / "solver-curved-design.json"
SAVED_SHA256 = "a513dd59857d600cc2a602dc6cf5e2b4da4cf25c2664a92dd01a1c3ae45abf8e"
VARIANT_SOURCES = {ENTRY: ENTRY_SHA256, CURVED_DESIGN_SOURCE: CURVED_DESIGN_SHA256}
ARMS = ("c0", "fitted_c")


def verify_saved_solves(evidence):
    if digest(evidence) != SAVED_SHA256:
        raise ValueError("Saved curved-design evidence differs from the reviewed comparison")
    cases = read(evidence)["cases"]
    if cases.keys() != {"DS30-0008", "south"}:
        raise ValueError("Expected both the dense physical and public southern saved solves")
    for case in cases.values():
        stock, direct = (case["runs"][mode] for mode in ("stock", "direct"))
        for run in (stock, direct):
            if (run["overlay_sha256"] != CURVED_DESIGN_SHA256
                    or run["results"]["status"] != "ok"
                    or not all(run["checks_against_margin_control"].values())):
                raise ValueError("Curved-design comparison differs from the reviewed solver")
        if (direct["results"]["arms"] != stock["results"]["arms"]
                or direct["results"]["owners"] != stock["results"]["owners"]
                or direct["science"] != stock["science"]
                or case["displacement_km_vs_deployed"] != {arm: 0. for arm in ARMS}
                or not direct["timings"]["direct_assembly_calls"]):
            raise ValueError("Saved comparison must preserve endpoints, owners, path and grid")


def relocate_libraries(parent, output, original):
    relocated = {}
    for name, pin in original.items():
        if isinstance(pin, dict) and pin.keys() == {"library", "sha256"}:
            library = Path(pin["library"]).resolve(strict=True)
            relative = library.relative_to(parent)
            if (digest(library) != pin["sha256"]
                    or original["sources"].get(str(relative)) != pin["sha256"]):
                raise ValueError(f"Inherited library differs from its reviewed pins: {name}")
            relocated[name] = pin | {"library": str(output / relative)}
    return relocated


def freeze(parent, output, receipt):
    parent, output, receipt = (path.resolve() for path in (parent, output, receipt))
    if (output.exists() or receipt.exists() or output.is_relative_to(parent)
            or receipt.is_relative_to(parent) or receipt.is_relative_to(output)):
        raise ValueError("Bundle and receipt must be fresh paths outside the parent and each other")
    require_spec(parent, PARENT)
    original = read(parent / "spec.json")
    published = read(PARENT_RECEIPT)
    if (published["specification"] != PARENT or published["spec"] != original
            or Path(original["detector"]) != parent / RECEIVER
            or digest(parent / RECEIVER) != original["detector_sha256"]
            or original["sources"].get(str(RECEIVER)) != original["detector_sha256"]):
        raise ValueError("Expected the selected-v3 frozen parent and its reviewed receiver")
    verify_saved_solves(SAVED_SOLVES)
    for source, expected in VARIANT_SOURCES.items():
        if digest(SOURCE / source) != expected:
            raise ValueError(f"Curved-design source differs from the reviewed add-on: {source}")

    from tools.pipeline_eval.variants.algo08_curved_design import SOURCE_PINS

    release_pins = {module.__name__.replace(".", "/") + ".py": pin
                    for module, pin in SOURCE_PINS.items()}
    if any(digest(RELEASE / "src" / source) != pin for source, pin in release_pins.items()):
        raise ValueError("Installed solver preparation differs from the measured released source")

    spec = original | relocate_libraries(parent, output, original) | {
        "detector": str(output / RECEIVER),
        "curved_design": True,
        "sources": original["sources"] | {str(name): pin for name, pin in VARIANT_SOURCES.items()},
    }
    fingerprint = canonical_digest(spec)
    before = files(parent)
    with TemporaryDirectory(prefix=".curved-design-", dir=output.parent) as directory:
        stage = Path(directory) / "bundle"
        shutil.copytree(parent, stage, ignore=shutil.ignore_patterns("__pycache__"))
        for source in VARIANT_SOURCES:
            shutil.copyfile(SOURCE / source, stage / source)
        (stage / "spec.json").unlink()
        write(stage / "spec.json", spec)
        require_spec(stage, fingerprint)
        after = files(stage)
        changed = {path for path, value in after.items() if before.get(path) != value}
        if changed != {Path("spec.json"), *VARIANT_SOURCES} or before.keys() - after.keys():
            raise ValueError("The curved-design freeze changed an unrelated parent file")
        stage.rename(output)
    write(receipt, dict(
        specification=fingerprint, parent_specification=PARENT, spec=spec,
        changed_files=sorted(map(str, changed)), release_solver_sources=release_pins,
        saved_evidence=dict(path=SAVED_SOLVES.name, sha256=SAVED_SHA256),
    ))
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("parent", "output", "receipt"):
        parser.add_argument(field, type=Path)
    freeze(**vars(parser.parse_args()))
