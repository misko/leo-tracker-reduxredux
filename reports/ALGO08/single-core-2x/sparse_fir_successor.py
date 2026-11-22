"""Freeze and validate the sparse-ranking and tiled-FIR successor to ad417."""

import argparse
import runpy
import shutil
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.experimental_publication import RELEASE, SPARSE_RANK_SOURCES
from tools.pipeline_eval.qualification.paired_publication import archive_identity

from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import (
    HERE,
    KEYS,
    MEASUREMENTS,
    evidence_digests,
    read_compressed,
    solve,
    write,
)

PARENT = "sha256:ad417aaa51a49edf1a36aca571683bbc0479317c06b821030373656461a28acd"
OLDER = "sha256:e279026bc32ff63297cc9f5f92488bd72f29a0b7d680df83ef528a22dc481c06"
FIR = "cb57aa1e83463ccb7fe491115f961bb21f565736838eee110d7b398a974f1898"
SCAN = "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89"
SCAN_FILE = "src/leo/analysis/localization_v3/scan.py"
LAUNCHER = Path("tools/pipeline_eval/qualification/experimental_publication.py")
PROJECTOR = SPARSE_RANK_SOURCES[-1]
FIR_SOURCE = Path("tools/pipeline_eval/variants/experimental/receiver_fir_tile.c")
RECEIVER = Path("receiver.so")
SOURCE = HERE.parents[2]


def files(directory):
    return {path.relative_to(directory): digest(path) for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def options(specification):
    changed = {"detector", "detector_sha256", "sources", "sparse_rank_projection"}
    return {name: value["sha256"] if isinstance(value, dict) else value
            for name, value in specification.items() if name not in changed}


def freeze(bench, bundle, receipt):
    parent = bench / "integration-restored-scout-graph"
    require_spec(parent, PARENT)
    previous = read(parent / "spec.json")
    if previous != read(MEASUREMENTS / "restored-scout-graph-freeze.json")["spec"]:
        raise ValueError("Parent differs from the published freeze")
    tile = bench / "d97b-fir-tile-v1/tile.so"
    built = read(MEASUREMENTS / "receiver-fir-tile.json")["build"]
    if (digest(tile) != FIR or built["candidate_sha256"] != FIR
            or digest(SOURCE / FIR_SOURCE) != built["tile_source_sha256"]
            or digest(RELEASE / SCAN_FILE) != SCAN
            or digest(parent / RECEIVER) != previous["detector_sha256"]):
        raise ValueError("Released scan, reviewed FIR build or parent detector differs")

    files_before = files(parent)
    shutil.copytree(parent, bundle, ignore=shutil.ignore_patterns("__pycache__"))
    for path in (LAUNCHER, PROJECTOR, FIR_SOURCE):
        shutil.copyfile(SOURCE / path, bundle / path)
    shutil.copyfile(tile, bundle / RECEIVER)
    specification = previous | {
        "detector": str(bundle / RECEIVER), "detector_sha256": FIR,
        "sparse_rank_projection": SCAN,
        "sources": previous["sources"] | {
            str(file): digest(bundle / file)
            for file in (LAUNCHER, FIR_SOURCE, RECEIVER, *SPARSE_RANK_SOURCES)
        },
    }
    for name, pin in previous.items():
        if isinstance(pin, dict) and set(pin) == {"library", "sha256"}:
            library = Path(pin["library"]).relative_to(parent)
            specification[name] = pin | {"library": str(bundle / library)}
    (bundle / "spec.json").unlink()
    write(bundle / "spec.json", specification)
    identity = canonical_digest(specification)
    require_spec(bundle, identity)
    mutable = {LAUNCHER, PROJECTOR, FIR_SOURCE, RECEIVER, Path("spec.json")}
    new_files = files(bundle)
    changed = {file for file, pin in new_files.items() if files_before.get(file) != pin}
    if (changed != mutable or set(files_before) - set(new_files)
            or options(specification) != options(previous)):
        raise ValueError("Successor changed an unrelated frozen file or option")
    write(receipt, dict(specification=identity, parent_specification=PARENT, spec=specification,
                        release_scan_source=dict(path=str(RELEASE / SCAN_FILE), sha256=SCAN),
                        changed_files=sorted(map(str, changed)),
                        inherited_files=len(new_files) - len(mutable)))


def require_successor(bundle, frozen):
    require_spec(bundle, frozen["specification"])
    if (frozen["spec"] != read(bundle / "spec.json")
            or frozen["parent_specification"] != PARENT
            or frozen["spec"]["detector_sha256"] != FIR
            or frozen["spec"]["sparse_rank_projection"] != SCAN):
        raise ValueError("Expected the research-only sparse FIR successor")


def terminal(result, reference):
    science, expected = evidence_digests(result), evidence_digests(reference)
    if not science or science != expected:
        raise ValueError("Position path, grid or objective differs")
    if any(key not in result or key not in reference or result[key] != reference[key]
           for key in KEYS):
        raise ValueError("Decision, calibration arm, ownership or orbit policy differs")
    stats = result["sparse_rank_projection"]
    if len(stats) != 1 or not stats[0]:
        raise ValueError("Expected an executed sparse rank call")
    return {key: result[key] for key in (*KEYS, "solver_cpu_s", "solver_wall_s",
                                         "sparse_rank_projection")} | {"science": science}


def saved_solves(bench, bundle, frozen, receipt):
    require_successor(bundle, frozen)
    evidence = {}
    physical = bench / "restored-graph-profile-0008"
    reference = MEASUREMENTS / "restored-scout-0008-solver-profile.json"
    published = read(reference)
    native, offer = (read(physical / name) for name in ("native.json", "offer.json"))
    archive = Path(published["archive"]["root"])
    pair = bench.parent / "ds30-v2-stage-restored-scout-ad417a/DS30-0008/pair.json"
    control = read(physical / "terminal.json")
    if (published["specification"] != PARENT
            or canonical_digest(native) != published["native_sha256"]
            or offer != published["offer"] or digest(pair) != published["pair_sha256"]
            or archive_identity(archive) != published["archive"]
            or evidence_digests(control) != published["science"]
            or not all(control[key] == published[key] for key in ("arms", "owners", "associated"))
            or control["status"] != published["decision"]
            or control["reason"] != published["reason"]):
        raise ValueError("Physical saved detections, offer, archive or terminal reference differ")
    result = terminal(solve(bundle, native, offer, archive), control)
    if archive_identity(archive) != published["archive"]:
        raise ValueError("The physical archive changed during the solve")
    evidence["DS30-0008"] = result | dict(
        matched_fields=[*KEYS, *result["science"]], offer=offer,
        native_sha256=published["native_sha256"], archive=published["archive"],
        reference_sha256=digest(reference), reference_specification=PARENT,
    )

    india = bench / "screened-tiled-graph-saved/India.json"
    previous = read(india)
    graph = bench / "integration-screened-tiled-graph"
    require_spec(graph, OLDER)
    parent = bench / "integration-restored-scout-graph"
    if (files(graph / "tools") != files(parent / "tools")
            or options(read(graph / "spec.json")) != options(read(parent / "spec.json"))):
        raise ValueError("The archived India run has a different solver")
    transfer = runpy.run_path(str(HERE / "covariance_transfer_trial.py"))
    verify_archive = runpy.run_path(str(HERE / "complete_family_cavity_trial.py"))["verify_archive"]
    transfer_receipt = MEASUREMENTS / "covariance-geographic-transfer.json"
    plan, = (row for row in read(transfer_receipt)["rows"]
             if row["offer"] == previous["offer"]
             and row["document_sha256"] == previous["native_sha256"]
             and row["history_sha256"] == previous["archive_sha256"])
    site = bench / "portable-v5-geodiverse" / plan["case"]
    native, offer = site / "native.json", plan["offer"]
    if digest(native) != plan["document_sha256"] or read(site / "matched-tile.json") != offer:
        raise ValueError("India detections or offer differ")
    verify_archive(transfer, plan, site)
    result = terminal(solve(bundle, read(native), offer, site / "tle"), previous["native_graph"])
    verify_archive(transfer, plan, site)
    evidence["India"] = result | dict(
        matched_fields=[*KEYS, *result["science"]], offer=offer,
        native_sha256=plan["document_sha256"], archive_sha256=plan["history_sha256"],
        reference_sha256=digest(india), reference_specification=OLDER,
        reference_solver_identical_to_parent=True,
    )
    write(receipt, dict(specification=frozen["specification"], sites=evidence))


def receiver(bench, bundle, frozen, binding, receipt):
    import numpy as np

    from tools import algo08_scan

    from . import receiver_cfo_lineage_trial as lineage

    require_successor(bundle, frozen)
    wraps = MEASUREMENTS / "receiver-cfo-wrap-trace.json.gz"
    tile = MEASUREMENTS / "receiver-fir-tile.json"
    fixed, reviewed = read_compressed(wraps), read(tile)
    if (fixed["wrapped"]["library_sha256"] != reviewed["build"]["reference_sha256"]
            or reviewed["build"]["candidate_sha256"] != FIR
            or fixed["detections"] != lineage.DETECTION_PINS
            or any(row["changed"] or len(row["rows"]) != 4 for row in reviewed["Austin"].values())):
        raise ValueError("CFO or Austin receipts do not bind the reviewed FIR comparison")
    paired = bench.parent / "ds30-v2-stage-covariance-375895/DS30-0008"
    pair = read(paired / "pair.json")
    saved = {}
    for arm in lineage.DETECTION_PINS:
        document, = (paired / arm).glob("fast-scan-automatic-work/*/detections.json")
        saved[arm] = lineage.saved_rows(document, arm, pair)
    samples = lineage.load_samples(binding, Path("/srv/bulk"), pair, saved["baseline"])
    if set(samples) != {row["visit"] for row in fixed["rows"]}:
        raise ValueError("Expected the three archived refinement lanes")
    asset_bytes = lineage.pin(RELEASE / "assets/lower.f32", algo08_scan.PINS["lower.f32"])
    asset = np.frombuffer(asset_bytes, dtype="<f4")
    rows = []
    with ExitStack() as stack:
        candidate = lineage.Receiver(bundle / RECEIVER, asset)
        stack.callback(candidate.close)
        readout = lineage.PrimaryReadout(candidate, asset, stack)
        for expected in fixed["rows"]:
            visit = expected["visit"]
            source = samples[visit]
            metadata = {k: v for k, v in source.items() if k != "samples"}
            if any(expected[key] != value for key, value in metadata.items()):
                raise ValueError(f"Archived input differs at visit {visit}")
            iq, lane, center = (source[key] for key in ("samples", "lane", "center"))
            factors, cpu_ns, wall_ns = candidate.timed(iq, lane, center)
            scout = readout.scout_seed(iq, lane, center)
            for build in ("restored-delay-product", "wrapped-delay-refinement"):
                reference, = (r for r in expected["builds"] if r["build"] == build)
                if (scout != reference["scout"] or not all(
                    lineage.same_factor(left, right)
                    for left, right in zip(factors, reference["all_factors"], strict=True)
                )):
                    raise ValueError(f"Scout or exported factors differ from {build} at {visit}")
            primary, = (r for r in factors if r[0] == 0)
            deployed = saved["baseline"][visit, lane]["candidates"][0]
            if tuple(deployed[key] for key in lineage.FIELDS[:4]) != primary[:4]:
                raise ValueError(f"Deployed primary timing differs at {visit}")
            rows.append(metadata | dict(visit=visit, factors=factors, scout=scout,
                                         cpu_ns=cpu_ns, wall_ns=wall_ns))
    write(receipt, dict(
        specification=frozen["specification"], receiver_sha256=FIR, visits=rows,
        physical_reference_sha256=digest(wraps), physical_pair_sha256=digest(paired / "pair.json"),
        binding_sha256=digest(binding), pilot_sha256=sha256(asset_bytes).hexdigest(),
        austin_receipt_sha256=digest(tile),
        austin_exact_calls={name: len(row["rows"]) for name, row in reviewed["Austin"].items()},
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "solve", "receiver"))
    for arg in ("bench", "bundle", "freeze_receipt"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--binding", type=Path)
    args = parser.parse_args()
    if args.stage == "freeze":
        freeze(args.bench.resolve(), args.bundle.resolve(), args.freeze_receipt)
    elif args.output is None:
        parser.error("Expected an output receipt")
    elif args.stage == "solve":
        saved_solves(args.bench, args.bundle, read(args.freeze_receipt), args.output)
    elif args.binding is None:
        parser.error("receiver requires the archived binding")
    else:
        receiver(args.bench, args.bundle, read(args.freeze_receipt), args.binding, args.output)


if __name__ == "__main__":
    main()
