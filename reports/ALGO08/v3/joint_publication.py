"""Run the repaired joint solver through the v3 publication stack in a fresh research root."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import configuration, machine
from blind_joint_route import make_route


def verified_saved(native, expected, session, inventory_digest, receiver):
    from leo.contracts.digests import canonical_digest

    if (canonical_digest(native) != expected or native["source"]["session_id"] != session
            or native["source"]["input_manifest_sha256"] != inventory_digest
            or native["provenance"]["detector_sha256"] != "sha256:" + receiver):
        raise ValueError("Saved detector packet does not bind the requested input and receiver")
    return native


def artifacts(root, receipt):
    from PIL import Image
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    store = FastStandardAnalysisStore(root)
    run_id = receipt["run_id"]
    detail = store.detail(run_id)
    if detail["terminal_sha256"] != receipt["terminal_sha256"] or detail["state"] != receipt["decision"]:
        raise ValueError("Standard publication differs from the solver receipt")
    images = {}
    for obj in detail["artifacts"]:
        name = obj["name"]
        data = store.artifact(run_id, name, obj["sha256"])
        with Image.open(BytesIO(data)) as png:
            png.load()
            images[name] = dict(size=png.size, sha256=obj["sha256"],
                                rgba_sha256=sha256(png.convert("RGBA").tobytes()).hexdigest())
    if detail["state"] == "complete":
        if tuple(images) != tuple(PLOTS):
            raise ValueError("A completed fix must publish all eight figures")
        from leo.contracts.digests import canonical_digest
        return dict(images=images, path=canonical_digest(store.position_path(run_id)),
                    grid=canonical_digest(store.position_grid(run_id)))
    if detail["state"] != "withheld" or images:
        raise ValueError("Expected a withheld terminal without figures")
    return dict(images=images)


def run(args):
    if bool(args.saved) != bool(args.saved_digest):
        raise ValueError("A saved detection packet needs its canonical digest")
    publication, spec = configuration()
    from tools import algo08_scan
    from tools.pipeline_eval.variants import v5_core

    args.output.mkdir(exist_ok=False)
    original = algo08_scan.analyze
    attempts = []
    saved = json.loads(args.saved.read_bytes()) if args.saved else None

    def analyze(*values, **kwargs):
        stock_solve = algo08_scan.solve

        def solve(native, reader, assets, region):
            route = make_route(v5_core.infer, reader, attempts, repair=True)
            with patch.object(v5_core, "infer", route):
                return stock_solve(native, reader, assets, region)

        with ExitStack() as stack:
            stack.enter_context(patch.object(algo08_scan, "solve", solve))
            if saved is not None:
                def acquire(session, inventory_digest, _inventory, _assets):
                    return verified_saved(saved, args.saved_digest, session, inventory_digest, spec["detector_sha256"])
                stack.enter_context(patch.object(algo08_scan, "acquire", acquire))
            return original(*values, **kwargs)

    clocks = (process_time(), perf_counter())
    with patch.object(algo08_scan, "analyze", analyze):
        receipt = publication.run(SimpleNamespace(recording=args.recording, archive=args.archive, region=args.region,
                                                 bulk_root=args.output), spec)
    cpu, wall = process_time() - clocks[0], perf_counter() - clocks[1]
    if len(attempts) != 1:
        raise ValueError("Expected exactly one execution of the research solver")
    source = Path(__file__).resolve().parent
    pins = {name: sha256((source / name).read_bytes()).hexdigest() for name in (
        "joint_publication.py", "blind_joint_finish.py", "blind_joint_route.py", "blind_joint_repair.py")}
    result = dict(input="saved detector" if saved is not None else "raw recording", saved_digest=args.saved_digest,
                  reference="installed v3 with research joint repair", source_sha256=pins, route=attempts[0]["decision"],
                  machine=machine(), publication_cpu_s=cpu, publication_elapsed_s=wall, receipt=receipt)
    if args.verify_images:
        result["evidence"] = artifacts(args.output, receipt)
    (args.output / "joint-research-receipt.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "output"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--saved", type=Path)
    cli.add_argument("--saved-digest")
    cli.add_argument("--verify-images", action="store_true")
    run(cli.parse_args())
