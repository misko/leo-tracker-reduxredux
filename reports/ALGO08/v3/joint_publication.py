"""Run the repaired joint solver through the v3 publication stack in a fresh research root."""

import argparse
from collections import Counter
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


def full_catalogue_route(installed, reader, attempts):
    from functools import partial
    from runpy import run_path
    from blind_joint_finish import cold_candidate
    from certified_salvage import propose
    from lighter_joint_estimator import update
    from tools.pipeline_eval.variants import v5_core

    rank_file = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants/algo08_blind_rank.py"
    share_geometry = run_path(str(rank_file))["shared_rank_preparation"]

    def cold(prepared, region, bound):
        ordinary_rank = v5_core.ranked_initial_nodes

        def rank(scan):
            with share_geometry(scan):
                return ordinary_rank(scan)

        with patch.object(v5_core, "ranked_initial_nodes", rank):
            return cold_candidate(prepared, region, bound)

    return make_route(installed, reader, attempts, repair=True, signed_finish=True,
                      joint_proposal=partial(propose, certified=True, cold_start=cold), signed_updater=update)


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


def run(args, *, detector_override=None, detector_description=None, track_config=None, prepare_detector=None):
    if bool(args.saved) != bool(args.saved_digest):
        raise ValueError("A saved detection packet needs its canonical digest")
    if args.saved and (detector_override is not None or prepare_detector is not None):
        raise ValueError("A detector substitution requires the full raw input path")
    if detector_override is not None and prepare_detector is not None:
        raise ValueError("Choose a prepared detector or a detector factory")
    stock_control = getattr(args, "stock_control", False)
    full_catalogue = getattr(args, "full_catalogue", False)
    signed_finish = getattr(args, "signed_finish", False) or full_catalogue
    if stock_control and signed_finish:
        raise ValueError("Choose either installed stock or the signed research finish")
    publication, spec = configuration()
    if prepare_detector is not None:
        detector_override = prepare_detector()
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core

    args.output.mkdir(exist_ok=False)
    original = algo08_scan.analyze
    attempts = []
    saved = json.loads(args.saved.read_bytes()) if args.saved else None
    saved_handoffs, solves, selected_rows = [], [], {}
    observer = getattr(args, "observe_prepared", None)
    preparations = []

    def analyze(*values, **kwargs):
        stock_solve = algo08_scan.solve

        def solve(native, reader, assets, region):
            cpu, wall = process_time(), perf_counter()
            infer = v5_core.infer
            route = infer
            if full_catalogue:
                route = full_catalogue_route(infer, reader, attempts)
            elif not stock_control:
                route = make_route(infer, reader, attempts, repair=True, signed_finish=signed_finish)

            def observed(prepared, *values, **options):
                preparations.append(observer(prepared))
                return route(prepared, *values, **options)

            with ExitStack() as stack:
                if track_config is not None:
                    factory = algo08_position.TrackConfig
                    stack.enter_context(patch.object(algo08_position, "TrackConfig",
                                                     lambda **cfg: track_config(factory(**cfg))))
                if observer is not None or not stock_control:
                    stack.enter_context(patch.object(v5_core, "infer", observed if observer is not None else route))
                decision, packet, policy = stock_solve(native, reader, assets, region)
            solves.append(dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall, orbit_policy=policy))
            if observer is not None:
                solves[-1].update(preparation=preparations, inference_metrics=decision.get("metrics"))
            if packet is not None:
                selected_rows.update({arm: [[row["observation_id"], row["norad"], row["role"]] for row in rows]
                                      for arm, rows in packet["rows"].items()})
                solves[-1].update(grid_points=packet["position_grid"]["evaluated_points"],
                                  grid_complete=packet["position_grid"]["complete"],
                                  objective_replay=packet["objective_replay"])
            return decision, packet, policy

        with ExitStack() as stack:
            stack.enter_context(patch.object(algo08_scan, "solve", solve))
            if detector_override is not None:
                stack.enter_context(patch.object(algo08_scan, "detector", detector_override))
            if saved is not None:
                def acquire(session, inventory_digest, _inventory, _assets):
                    found = verified_saved(saved, args.saved_digest, session, inventory_digest, spec["detector_sha256"])
                    saved_handoffs.append(inventory_digest)
                    return found
                stack.enter_context(patch.object(algo08_scan, "acquire", acquire))
            return original(*values, **kwargs)

    clocks = (process_time(), perf_counter())
    with patch.object(algo08_scan, "analyze", analyze):
        receipt = publication.run(SimpleNamespace(recording=args.recording, archive=args.archive, region=args.region,
                                                 bulk_root=args.output), spec)
    cpu, wall = process_time() - clocks[0], perf_counter() - clocks[1]
    if len(solves) != 1 or len(attempts) != (0 if stock_control else 1):
        raise ValueError("Expected exactly one solver invocation through the requested route")
    if saved is not None and len(saved_handoffs) != 1:
        raise ValueError("Expected one verified saved detection handoff")
    source = Path(__file__).resolve().parent
    pins = {name: sha256((source / name).read_bytes()).hexdigest() for name in (
        "joint_publication.py", "blind_joint_finish.py", "blind_joint_route.py", "blind_joint_repair.py", "blind_joint_signed.py")}
    if full_catalogue:
        for name in ("certified_salvage.py", "lighter_joint_estimator.py", "../../../tools/pipeline_eval/variants/algo08_blind_rank.py"):
            pins[name] = sha256((source / name).read_bytes()).hexdigest()
    from leo.application.localization_v3_engine import _json_value

    input_kind = "saved detector" if saved is not None else "raw recording"
    if detector_override is not None:
        input_kind = detector_description or "verified raw recording with archived receiver rows"
    result = dict(input=input_kind, saved_digest=args.saved_digest,
                  reference="installed v3" if stock_control else "installed v3 with research joint repair",
                  source_sha256=pins, route="stock" if stock_control else attempts[0]["decision"],
                  signed_finish=signed_finish, stock_control=stock_control, machine=machine(),
                  publication_cpu_s=cpu, publication_elapsed_s=wall, solve=solves[0],
                  selected_roles={arm: dict(Counter(row[2] for row in rows)) for arm, rows in selected_rows.items()},
                  saved_handoff_manifest=saved_handoffs[0] if saved_handoffs else None, receipt=receipt,
                  route_details=attempts[0] if attempts else None)
    if args.verify_images:
        result["evidence"] = artifacts(args.output, receipt)
        if saved is not None:
            result["selected_rows"] = selected_rows
    if full_catalogue:
        result["full_catalogue"] = True
    with (args.output / "joint-research-receipt.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False, default=_json_value)
        stream.write("\n")


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "output"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--saved", type=Path)
    cli.add_argument("--saved-digest")
    cli.add_argument("--verify-images", action="store_true")
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--stock-control", action="store_true")
    mode.add_argument("--signed-finish", action="store_true")
    mode.add_argument("--full-catalogue", action="store_true")
    run(cli.parse_args(argv))


if __name__ == "__main__":
    main()
