"""Trace the stock and collapsed fits, and test the stock finish on saved detections."""

import argparse
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from residual_attribution_trial import ARMS, read, write


def checkout_module(relative):
    # The trial and its validators live outside the frozen numerical path.
    checkout = Path(__file__).resolve().parents[3]
    source = checkout / relative
    spec = spec_from_file_location(source.stem, source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_rows(node):
    rows = [row for row in node["seed"]["rows"] if row["active_curvature"]]
    return [(row["component"], row["candidate_index"], row["candidate_norad"], alias)
            for row, alias in zip(rows, node["aliases"], strict=True)]


def fit_trace(record, half_width):
    if record is None:
        return None
    endpoint = record["endpoint_east_north_km"]
    return dict(
        endpoint=endpoint, west_clearance_km=float(half_width + endpoint[0]),
        objective=record.get("negative_twice_elbo"),
        phase_reference=record["phase_reference"], rounds=[
            dict(start=item["fit"]["history"][0]["parameters"],
                 ending=item["fit"]["parameters"], squared_residual=item["fit"]["score"],
                 phase_change_s=item["phase_change_s"],
                 stopped=item["fit"]["stopped"])
            for item in record["history"]
        ],
    )


def pair_trace(pair, region):
    return {arm: fit_trace(pair.get(arm), region.half_width_km) for arm in ARMS}


def selected_inputs(signed, fit):
    if fit is None:
        return signed
    if fit["accepted"]:
        selected = fit["selected"]
        node, means, entries = (selected[key] for key in ("node", "means", "entries"))
    else:
        node, means, entries = (fit["baseline_" + key] for key in ("node", "means", "entries"))
    return dict(scan=signed["scan"], node=node, means=means, entries=entries,
                keep=fit["original_mask"], powers=fit["powers"], model=fit["model"],
                arms=fit["policy_arms"])


def model_trace(inputs):
    return dict(rows=selected_rows(inputs["node"]),
                **{key: inputs[key] for key in ("keep", "powers", "means", "entries", "model")},
                arms=pair_trace(inputs["arms"], inputs["scan"].search_region))


@contextmanager
def traced_fits(notes, *, collapsed_mode):
    from leo.analysis.localization_v3 import conservative_recovery, history_policy, signed_context
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    def instrument(operation, readout):
        @wraps(operation)
        def inspect(*args, **kwargs):
            began = process_time()
            result = operation(*args, **kwargs)
            clocks = notes.setdefault("stage_cpu_s", {})
            clocks[readout.__name__] = clocks.get(readout.__name__, 0.0) + process_time() - began
            readout(args, result)
            return result

        return inspect

    def initial(args, output):
        answer, branch_count = output
        choice = answer["choices"][answer["selected_hypothesis"]]
        notes["initial"] = dict(rows=selected_rows(choice["node"]), branches=branch_count)

    def conservative(args, output):
        if output["status"] != "complete":
            return
        notes["conservative"] = dict(
            rows=selected_rows(output["final_node"]), keep=output["final_mask"],
            arms={arm: {"endpoint": row["record"]["fit"]["parameters"],
                        "phase_reference": row["record"]["phase_reference"]}
                  for arm, row in output["arms"].items()},
        )

    def history(args, output):
        if output["status"] != "accepted":
            return
        scan = args[0]
        notes["family"] = dict(
            curved=pair_trace(output["curved_arms"], scan.search_region),
            predictive=pair_trace(output["linear_arms"], scan.search_region),
            accepted=output["linear_paired_valid"], confidence=output["confidence"],
        )

    def signed(args, output):
        _, _, _, raw, forecast, _ = args
        notes["signed"] = {key: output["signed"][key] for key in ("accepted", "selection")}
        notes["signed"]["causal"] = dict(
            origin_utc_ns=raw["origin_utc_ns"], cutoff_utc_ns=raw["cutoff_utc_ns"],
            history_sha256=forecast["history_sha256"], strictly_pre_RF=forecast["strictly_pre_RF"],
            GPS_or_radio_used=forecast["GPS_or_radio_used"],
            temporal_split_boundary_ns=forecast["temporal_split_boundary_ns"],
            last_target_ns=max((row["validation_time_ns"] for row in forecast["transitions"]),
                               default=None),
            last_source_ns=max((row["collected_utc_ns"] for row in raw["sources"]), default=None),
            sources=len(raw["sources"]),
        )

    def nominate(args, output):
        if output is not None:
            node, point, phase, reference, _, metrics = output
            notes["collapsed_nomination"] = dict(rows=selected_rows(node), endpoint=point,
                                                 phase=phase, phase_reference=reference,
                                                 chosen_rank=metrics["chosen_rank"])

    def collapsed(args, output):
        scan, _, mask, arm, powers, means, model, point, reference = args
        notes.setdefault("collapsed_curved", []).append(dict(
            arm=arm, keep=mask, powers=powers, means=means, model=model,
            initial_position=point, initial_phase=reference,
            fit=fit_trace(output[0], scan.search_region.half_width_km),
        ))

    def regional_guard(args, output):
        notes["guard_probe_points"] = len(output["points"])

    bindings = [
        (v5_core, "initial_selection", initial),
        (conservative_recovery, "conservative_recovery", conservative),
        (history_policy, "history_policy", history),
        (signed_context, "signed_context", signed),
        (regional_bound_guard, "causal_probes", regional_guard),
    ]
    if collapsed_mode:
        from tools.pipeline_eval.variants import algo08_collapsed

        bindings.extend((
            (algo08_collapsed, "nominate", nominate),
            (algo08_collapsed, "refit", collapsed),
        ))
    with ExitStack() as stack:
        for module, name, fn in bindings:
            original = getattr(module, name)
            stack.enter_context(patch.object(module, name, instrument(original, fn)))
        yield


def signed_mean_witness(actual, control):
    """Exchange only the phase centers in the same cold predictive refit."""
    import numpy as np
    from leo.analysis.localization_v3.event_position import (
        attach_event_predictive, cached, make_event_problem, refit,
    )

    result = model_trace(actual)
    keys = ("rows", "keep", "powers", "model", "entries")
    from leo.application.localization_v3_engine import _json_value

    def plain(x):
        return json.loads(json.dumps(x, default=_json_value, allow_nan=False))

    matches = {key: plain(result[key]) == control[key] for key in keys}
    ordinary, signed = np.asarray(actual["means"]), np.asarray(control["means"])
    difference = np.flatnonzero(ordinary != signed).tolist()
    if not all(matches.values()) or not difference:
        return dict(matched=matches, changed_means=difference, substituted=None)
    scan, node, keep, powers, model, entries = (
        actual[key] for key in ("scan", "node", "keep", "powers", "model", "entries")
    )
    fitted = {arm: refit(scan, node, keep, arm, powers, signed, model, [], entries) for arm in ARMS}
    samples = {}
    for arm in ARMS:
        ref = np.asarray(control["arms"][arm]["endpoint"])
        inward = ref.copy()
        inward[0] += 0.001  # Same step as the stock bounded finite difference.
        points = dict(control=ref, collapsed=actual["arms"][arm]["endpoint_east_north_km"],
                      one_metre_east_of_control=inward)
        samples[arm] = {}
        for name, means, record in (("ordinary", ordinary, actual["arms"][arm]),
                                    ("signed", signed, fitted[arm])):
            model_arm = make_event_problem(scan, node, keep, arm, record["phase_reference"],
                                           powers, means, model, [])
            attach_event_predictive(model_arm, entries, powers)
            cached(model_arm)
            rows = {}
            for label, point in points.items():
                residual = model_arm.residual(point)
                rows[label] = dict(point=point, squared_residual=float(residual @ residual),
                                   negative_twice_elbo=model_arm.calculate(point)["negative_twice_elbo"])
            samples[arm][name] = rows
    return dict(matched=matches, changed_means=difference,
                substituted=pair_trace(fitted, scan.search_region), bound_scores=samples)


def main(args):
    from tools.pipeline_eval.qualification import experimental_publication

    specification = read(args.spec)
    if specification.get("startup") == "lazy-exports":
        from tools.pipeline_eval.variants.experimental.lean_startup import install

        install()
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    publication = checkout_module("tools/pipeline_eval/qualification/paired_publication.py")

    if canonical_digest(specification) != args.spec_sha256:
        raise ValueError("Spec does not match the declared frozen build")
    collapsed_mode = args.mode in ("collapsed", "signed-finish")
    selected_mode = "collapsed-repair" if collapsed_mode else "shared-tables"
    if specification["solver"] != selected_mode:
        raise ValueError("Unexpected frozen solver")
    publication.verify_sources(args.spec.parent / "reports/ALGO08/single-core-2x/run-candidate",
                               specification["sources"])
    archive_pin = publication.archive_identity(args.archive)
    if archive_pin["snapshots_sha256"] != args.archive_sha256:
        raise ValueError("Archive does not match the declared causal inventory")
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256:
        raise ValueError("Detections do not match the declared saved input")
    native = json.loads(raw)
    solver_only = {k: v for k, v in specification.items()
                   if k not in ("png_filter", "png_deflate", "paired_sha256")}
    solver_only.update(schedule="all", rendering="individual", ingress="stock", startup="stock")
    notes, original = {}, algo08_position.selected_packet
    chosen = None

    def selected(prepared, signed, fit):
        nonlocal chosen
        output = original(prepared, signed, fit)
        chosen = selected_inputs(signed, fit)
        notes["selected"] = model_trace(chosen)
        return output

    def from_saved(recording, _root, assets, archive, offer):
        if recording != args.native:
            raise ValueError("Expected the saved-detection dispatch")
        with ExitStack() as stack:
            if args.mode == "hybrid":
                selector = checkout_module("tools/pipeline_eval/variants/algo08_stock_finish.py")
                notes["screen"] = stack.enter_context(selector.screened_nomination())
            if args.mode == "signed-finish":
                selector = checkout_module(
                    "tools/pipeline_eval/variants/algo08_collapsed_signed_finish.py",
                )
                stack.enter_context(selector.signed_finish())
            stack.enter_context(patch.object(algo08_position, "selected_packet", selected))
            stack.enter_context(traced_fits(notes, collapsed_mode=collapsed_mode))
            began_cpu, began_wall = process_time(), perf_counter()
            decision, packet, orbit_policy = algo08_position.solve(
                native, TleArchiveReader(archive), assets, offer,
            )
            cpu, wall = process_time() - began_cpu, perf_counter() - began_wall
        if args.control_trace is not None:
            from tools.pipeline_eval.variants.orbit_projector import Projector
            from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings

            old = read(args.control_trace)
            if (old["mode"] != "control" or old["native_sha256"] != args.native_sha256
                    or old["archive"] != archive_pin
                    or old["region"] != offer.document()):
                raise ValueError("Control trace has a different measurement or search binding")
            with numerical_bindings(Projector(assets / "projector.so")):
                notes["signed_mean_witness"] = signed_mean_witness(chosen, old["trace"]["selected"])
        result = dict(mode=args.mode, native_sha256=args.native_sha256,
                      specification_sha256=args.spec_sha256, region=offer.document(),
                      archive=archive_pin,
                      cpu_s=cpu, wall_s=wall, orbit_policy=orbit_policy, decision=decision,
                      trace=notes)
        if packet is not None:
            result["evidence"] = {key: packet[key] for key in (
                "arms", "objective_replay", "position_path", "position_grid",
            )}
        return result

    with TemporaryDirectory() as temporary, patch.object(algo08_scan, "analyze", from_saved):
        entry = SimpleNamespace(bulk_root=Path(temporary), recording=args.native,
                                archive=args.archive, region=args.offer)
        result = experimental_publication.run(entry, solver_only)
    if publication.archive_identity(args.archive) != archive_pin:
        raise ValueError("Causal archive changed during solve")
    write(args.output, json.loads(json.dumps(result, default=_json_value, allow_nan=False)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "hybrid", "collapsed", "signed-finish"))
    for field in ("native", "spec", "archive", "offer", "output"):
        parser.add_argument(field, type=Path)
    for field in ("native_sha256", "spec_sha256", "archive_sha256"):
        parser.add_argument(field)
    parser.add_argument("--control-trace", type=Path)
    main(parser.parse_args())
