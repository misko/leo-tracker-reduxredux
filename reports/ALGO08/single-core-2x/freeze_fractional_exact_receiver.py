"""Freeze the spectral receiver with deployed absolute-phase scores for every factor."""

import argparse
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest

from .receiver_fractional_exact_trial import PARENT, PARENT_SHA, PHYSICAL_IQ, SPEC, TERMINAL_PAIR
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import write
from .sparse_fir_successor import RECEIVER, SOURCE, files
from tools.pipeline_eval.qualification.experimental_publication import FRACTIONAL_SELECTION_SOURCE


ALL_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
OBJECT_SHA = "4f0f48afe10f637be341add3763c42e57fcecdc7651260c3defcc19fc1104ca1"
GENERATED_SHA = "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707"
EXPERIMENT = Path("tools/pipeline_eval/variants/experimental")
SOURCES = {
    EXPERIMENT / "receiver_fractional_exact.inc": "7e6e4d0d0bd3074963a50340e645f66023c3a273ea2fc7cd6279496f2bef2a2b",
}
SELECTED_SHA = "a5862937b78f13d9788386d134cdbe427393dab678c858f27d4efeacdbf0efcb"
SELECTED_SOURCES = SOURCES | {
    EXPERIMENT / "receiver_fractional_exact.py": "6dce715c2c767194777a619321eb3c3d6041d27a06c10ade063baf49701b35c7",
    EXPERIMENT / "receiver_fractional_selected.inc": "87bb29f05393563ce953dafda4518af0529c4e94ef4e4e11c8ec43d448f9bfbb",
    FRACTIONAL_SELECTION_SOURCE: "c2e82ffd9a117e5f32b6e985ae8b8c337302a047fe4baa80d675f795f05e3fe3",
    Path("tools/pipeline_eval/qualification/experimental_publication.py"):
        "61e4611ccaa1370345394446ad5f4869e1fc2734a407f6f07e6db95e5fe68a2d",
}
SELECTED_OBJECTS = {
    "verifier_object_sha256": ("portable_verifier.o", "c9100e82cf8fa5b196a92a7c6ec92b71bafc1511190218b6f1bd7fd248765915"),
    "verifier_source_sha256": ("portable_verifier.c", "e70568f10c498f868db7b4b8652bba7747747b41023a053398da5cf40e5476d0"),
    "measurement_object_sha256": ("two_carrier_receiver.o", "e66c91a1efcda871668a07c36a2406b673d24187d439178a58e1f5c3d369e7bc"),
    "measurement_source_sha256": ("two_carrier_receiver.c", "113e0f21b35fe35c43973c824a0a82bca03d3bdebb234a2ed119404feb71943c"),
}


def evidence(work):
    paths = {key: work / filename for key, filename in (
        ("build", "build.json"), ("saved", "saved.json"), ("dense", "dense-archived.json"),
        ("physical", "physical.json"),
    )}
    build, saved, dense, physical = (read(path) for path in paths.values())
    if (build["parent_sha256"] != PARENT_SHA or build["exact_sha256"] != ALL_SHA
            or build["verifier_object_sha256"] != OBJECT_SHA
            or digest(work / "portable_verifier.o") != OBJECT_SHA
            or build["verifier_source_sha256"] != GENERATED_SHA
            or digest(work / "portable_verifier.c") != GENERATED_SHA
            or digest(work / "exact.so") != ALL_SHA
            or dense["archived_pair_sha256"] != TERMINAL_PAIR
            or physical["iq_sha256"] != PHYSICAL_IQ
            or physical["visits"] != 128 or physical["eligible"] != 116):
        raise ValueError("Exact score lineage or bounded comparison receipts differ")
    for receipt in (saved, dense, physical):
        if receipt["binaries"]["exact"] != ALL_SHA or receipt["binaries"]["parent"] != PARENT_SHA:
            raise ValueError("The compared libraries differ from the frozen detector pair")
    expected = {"ds26-weak": (36, 58), "austin-physical-zero": (4, 8),
                "austin-physical-offset": (4, 8), "austin-null-zero": (4, 0),
                "austin-null-offset": (4, 0), "DS30-0008-regressions": (3, 5)}
    groups = saved["samples"] | dense["samples"]
    if {key: (group["lane_configurations"], group["factor_count"]["deployed"])
            for key, group in groups.items()} != expected:
        raise ValueError("Expected the six saved evidence groups")
    for group in groups.values():
        if any(group["paired"]["deployed_to_exact"]["counts"].values()):
            raise ValueError("Exact verification differs on a saved receiver group")
    dense_rows = dense["samples"]["DS30-0008-regressions"]["rows"]
    if ({(int(row["key"]), row["receiver_id"]) for row in dense_rows} != {(2661, 1), (3298, 0), (3869, 0)}
            or any(row["archived_continuation_retention"]["baseline"]["candidate_rank"] != 0
                   for row in dense_rows)):
        raise ValueError("The archived dense continuation ranks differ")
    if len(physical["trials"]) != 4 or any(
        trial["counts"]["deployed_factors"] != 152 or len(trial["selection"]) != 53
        or any(trial["counts"][key] for key in (
            "exact_ordered_factor_different", "exact_selected_different", "continuation_different",
        )) for trial in physical["trials"]
    ):
        raise ValueError("Exact verification differs on chronological deployed factors")
    return {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()}


def freeze(bench, work, bundle, receipt, selected_build=None):
    parent = bench / PARENT
    require_spec(parent, SPEC)
    original = read(parent / "spec.json")
    if digest(parent / RECEIVER) != PARENT_SHA or original["detector_sha256"] != PARENT_SHA:
        raise ValueError("Expected the original spectral receiver")
    if bundle.exists() or receipt.exists() or bundle.is_relative_to(parent):
        raise ValueError("Expected new successor and receipt paths outside the parent")
    measurements = evidence(work)
    binary, pin, sources, selection = work / "exact.so", ALL_SHA, SOURCES, {}
    if selected_build is not None:
        selection = {"fractional_score_selection": True}
        binary, pin, sources = selected_build / "selected.so", SELECTED_SHA, SELECTED_SOURCES
        build_path = selected_build / "build.json"
        build = read(build_path)
        physical = read(work / "physical.json")
        if (build["exact_sha256"] != SELECTED_SHA or digest(binary) != SELECTED_SHA
                or build["parent_sha256"] != PARENT_SHA or physical["binaries"]["selected"] != SELECTED_SHA
                or any(build[key] != expected or digest(selected_build / file) != expected
                       for key, (file, expected) in SELECTED_OBJECTS.items())
                or any(trial["counts"]["repaired_selected_different"]
                       or trial["counts"]["selected_ordered_factor_different"]
                       or trial["counts"]["repairs"] != 53 for trial in physical["trials"])):
            raise ValueError("Selected score lineage or chronological scores differ")
        measurements["selected_build"] = dict(path=str(build_path), sha256=digest(build_path))
    for path, expected in sources.items():
        if digest(SOURCE / path) != expected:
            raise ValueError(f"Absolute-phase source differs from its pin: {path}")
    spec = original | {
        "detector": str(bundle / RECEIVER), "detector_sha256": pin,
        "sources": original["sources"] | {str(RECEIVER): pin}
        | {str(path): value for path, value in sources.items()},
    } | selection
    for name, inherited in original.items():
        if isinstance(inherited, dict) and set(inherited) == {"library", "sha256"}:
            path = Path(inherited["library"]).relative_to(parent)
            if digest(parent / path) != inherited["sha256"]:
                raise ValueError(f"Inherited library pin differs: {name}")
            spec[name] = inherited | {"library": str(bundle / path)}
    identity = canonical_digest(spec)
    before = files(parent)
    with TemporaryDirectory(prefix=".absolute-score-", dir=bundle.parent) as temporary:
        stage = Path(temporary) / "bundle"
        shutil.copytree(parent, stage, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(binary, stage / RECEIVER)
        for path in sources:
            shutil.copyfile(SOURCE / path, stage / path)
        (stage / "spec.json").unlink()
        write(stage / "spec.json", spec)
        require_spec(stage, identity)
        after = files(stage)
        changed = {path for path, value in after.items() if before.get(path) != value}
        if changed != {RECEIVER, Path("spec.json"), *sources} or before.keys() - after.keys():
            raise ValueError("An unrelated file changed during the exact receiver freeze")
        stage.rename(bundle)
    write(receipt, dict(specification=identity, parent_specification=SPEC, spec=spec,
                        receiver_sha256=pin, changed_files=sorted(map(str, changed)),
                        receiver_evidence=measurements))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bench", "work", "bundle", "receipt"):
        parser.add_argument(field, type=lambda value: Path(value).resolve())
    parser.add_argument("--selected-build", type=lambda value: Path(value).resolve())
    freeze(**vars(parser.parse_args()))
