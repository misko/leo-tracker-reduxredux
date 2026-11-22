"""Freeze the opt-in longitude successor and replay one archived southern solve."""

import argparse
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore
from tools.pipeline_eval.qualification.experimental_publication import LONGITUDE_CHART_SOURCE
from tools.pipeline_eval.qualification.paired_publication import archive_identity, evidence

from .residual_attribution_trial import saved_native
from .screened_stock_salvage_trial import digest, read, require_spec
from .screened_tiled_graph_trial import evidence_digests, solve, write
from .sparse_fir_successor import LAUNCHER, RECEIVER, SOURCE, files

PARENT = "sha256:23fadeb79c76c343760dc3fb107f7dfb170b0ba4eec22a4dc3df244c2187cf24"
PARENT_RECEIPT = Path(__file__).parent / "measurements/spectral-vectors-terminal-veto-freeze.json"
PARENT_RECEIPT_SHA = "1f01c550b96d22c6181cc28d2d4c5533d72b761ac7fb0d1fcbf835b55d648b70"
PAIR = "321f55cfe47a98f31d250dacf53efed30307545298d7ec64b1a3ea88300cc010"
SOURCES = {
    LAUNCHER: "b49b395baf2b9b1c9fbb6d1ca8d46bf571854ac50948a5e571d76d335f1c1854",
    LONGITUDE_CHART_SOURCE: "7316b2e4c60fdc78b9f870b42904f3775986f49ea612c38e7b50720897b8ea4d",
}
CHANGED = {Path("spec.json"), *SOURCES}


def reviewed_parent(parent):
    require_spec(parent, PARENT)
    original = read(parent / "spec.json")
    if (
        digest(PARENT_RECEIPT) != PARENT_RECEIPT_SHA
        or read(PARENT_RECEIPT)["spec"] != original
        or original["regional_veto_terminal_only"] is not True
        or original["detector"] != str(parent / RECEIVER)
        or original["detector_sha256"] != original["sources"][str(RECEIVER)]
        or "wrapped_longitude" in original
        or str(LONGITUDE_CHART_SOURCE) in original["sources"]
    ):
        raise ValueError("Expected the reviewed spectral receiver and terminal guard parent")
    return original


def successor_spec(original, parent, bundle):
    pins = original["sources"] | {str(path): pin for path, pin in SOURCES.items()}
    spec = original | {
        "wrapped_longitude": True,
        "detector": str(bundle / RECEIVER),
        "sources": pins,
    }
    for name, pin in original.items():
        if isinstance(pin, dict) and set(pin) == {"library", "sha256"}:
            source = Path(pin["library"]).relative_to(parent)
            if original["sources"].get(str(source)) != pin["sha256"]:
                raise ValueError(f"Unexpected inherited library pin: {name}")
            spec[name] = pin | {"library": str(bundle / source)}
    return spec


def check_files(before, after):
    changed = {name for name, value in after.items() if before.get(name) != value}
    if changed != CHANGED or before.keys() - after.keys():
        raise ValueError("Longitude successor differs in unrelated files")


def freeze(parent, bundle, receipt):
    original = reviewed_parent(parent)
    if bundle.exists() or receipt.exists() or bundle.is_relative_to(parent):
        raise ValueError("Expected new successor and receipt paths outside the parent")
    if {path: digest(SOURCE / path) for path in SOURCES} != SOURCES:
        raise ValueError("Longitude successor source differs from its reviewed pin")
    spec = successor_spec(original, parent, bundle)
    identity, before = canonical_digest(spec), files(parent)
    with TemporaryDirectory(prefix=".longitude-freeze-", dir=bundle.parent) as temporary:
        stage = Path(temporary) / "bundle"
        shutil.copytree(parent, stage, ignore=shutil.ignore_patterns("__pycache__"))
        for path in SOURCES:
            destination = stage / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, destination)
        (stage / "spec.json").unlink()
        write(stage / "spec.json", spec)
        require_spec(stage, identity)
        check_files(before, files(stage))
        stage.rename(bundle)
    write(
        receipt,
        dict(
            specification=identity,
            parent_specification=PARENT,
            spec=spec,
            changed_files=sorted(map(str, CHANGED)),
            receiver_sha256=spec["detector_sha256"],
        ),
    )


def replay(parent, bundle, receipt, pair_path, output):
    original = reviewed_parent(parent)
    spec = successor_spec(original, parent, bundle)
    identity, frozen = canonical_digest(spec), read(receipt)
    require_spec(bundle, identity)
    check_files(files(parent), files(bundle))
    if (
        frozen["specification"] != identity
        or frozen["parent_specification"] != PARENT
        or frozen["spec"] != spec
        or digest(pair_path) != PAIR
        or output.exists()
    ):
        raise ValueError("Expected the longitude successor and archived southern publication")
    pair = read(pair_path)
    publication = pair["runs"]["candidate"]
    published = publication["receipt"]
    offer = published["region"]
    archive = Path(pair["archive"]["root"])
    if (
        pair["candidate_specification_digest"] != PARENT
        or pair["candidate_specification"] != original
        or published["decision"] != "complete"
        or archive_identity(archive) != pair["archive"]
    ):
        raise ValueError("Archived publication does not bind the reviewed parent and causal inputs")
    native = saved_native(pair_path, "candidate", publication)
    root = pair_path.parent / "candidate"
    verified = evidence(root, published, 0, read_only=True)
    for key in ("raw_authority", "arms", "owners", "reason", "artifacts", "scientific_digests"):
        if verified[key] != publication[key]:
            raise ValueError(f"Archived raw publication differs from the pair receipt: {key}")
    workspace = FastScanStore(root).automatic_workspace(published["run_id"], create=False)
    terminal = read(workspace / "terminal.json")

    result = solve(bundle, native, offer, archive, guard_evidence=True)
    science = evidence_digests(result)
    grids = {name: science[f"position_{name}"] for name in ("grid", "path")}
    if (
        result["status"] != terminal["decision"]
        or result["orbit_policy"] != terminal["orbit_policy"]
        or any(result[key] != publication[key] for key in ("arms", "reason", "owners"))
        or grids != publication["scientific_digests"]
        or archive_identity(archive) != pair["archive"]
    ):
        raise ValueError("Saved longitude solve differs from the archived raw publication")
    fields = (
        "status",
        "reason",
        "arms",
        "owners",
        "associated",
        "orbit_policy",
        "regional_bound_guard",
        "solver_cpu_s",
        "solver_wall_s",
    )
    write(
        output,
        dict(
            specification=identity,
            parent_specification=PARENT,
            pair_sha256=PAIR,
            published_terminal_sha256=published["terminal_sha256"],
            native_sha256=canonical_digest(native),
            freeze_receipt_sha256=digest(receipt),
            archive=pair["archive"],
            offer=offer,
            archived_science=grids,
            successor={key: result[key] for key in fields} | {"science": science},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "replay"))
    for name in ("parent", "bundle", "receipt", "pair_path", "output"):
        parser.add_argument(
            name,
            type=lambda value: Path(value).resolve(),
            nargs=("?" if name in ("pair_path", "output") else None),
        )
    args = parser.parse_args()
    fixed = (args.parent, args.bundle, args.receipt)
    if args.stage == "freeze":
        if args.pair_path is not None or args.output is not None:
            parser.error("The freeze uses only the parent, bundle and receipt paths")
        freeze(*fixed)
    elif args.pair_path is None or args.output is None:
        parser.error("The replay also requires the archived pair and a new output path")
    else:
        replay(*fixed, args.pair_path, args.output)
