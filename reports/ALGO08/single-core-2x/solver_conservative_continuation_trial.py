"""Compare cold and cross-arm warm conservative fitting on verified saved detections."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np
from PIL import Image

from leo.analysis.localization_v3.retained_position import PositionNormal
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_standard_analysis import render
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_conservative_continuation, algo08_recovery_reuse
from solver_trial import measure


def fixed_reference_scores(snapshot, control, trial):
    scan, node, mask, widths = snapshot
    points = {"stock": control["endpoint_km"], "continued": trial["endpoint_km"]}
    references = {"continued": trial["final_phase_s"]}
    if "final_phase_s" in control:
        references["stock"] = control["final_phase_s"]
    losses = {}
    for name, reference in references.items():
        model = PositionNormal(scan, node, scan.radio_sigma_hz, True,
                               reference=np.asarray(reference), keep=mask)
        model.phase_sigma = widths
        losses[name] = {key: float(model.calculate(np.asarray(point))["negative_twice_elbo"])
                        for key, point in points.items()}
    return losses


def matched_witnesses(gates, snapshots, stock):
    original = {(gate["stage"], call["active_fit_sha256"]): call
                for gate in stock["gates"] for call in gate["calls"] if call["arm"] == "fitted_c"}
    ordered = ((gate["stage"], call) for gate in gates for call in gate["calls"])
    result = []
    for (stage, call), snapshot in zip(ordered, snapshots, strict=True):
        if call["mode"] != "continued":
            continue
        key = stage, call["active_fit_sha256"]
        if key in original:
            result.append(dict(stage=stage, active_points=call["active_points"],
                               negative_twice_elbo=fixed_reference_scores(snapshot, original[key], call)))
    return result


def run(mode, native, archive, assets, offer, *, native_digest, against_stock=None):
    packet = None
    selected = algo08_position.selected_packet

    def selected_packet(*args):
        nonlocal packet
        packet = selected(*args)
        return packet

    snapshots = []

    def audit(scan, node, mask, arm, record):
        checked = algo08_conservative_continuation.replay_endpoint(scan, node, mask, arm, record)
        if against_stock is not None:
            snapshots.append((scan, node, mask.copy(), record["phase_widths_s"].copy()))
        return checked

    with (
        algo08_recovery_reuse.stable_recovery() as recovery,
        algo08_conservative_continuation.measured_continuation(enabled=mode == "continued", audit=audit) as gates,
        patch.object(algo08_position, "selected_packet", selected_packet),
    ):
        result = measure("combined", native, archive, assets, offer)
    witnesses = []
    if against_stock is not None:
        stock = json.loads(against_stock.read_bytes())
        if (stock["mode"] != "stock" or stock["region"] != offer.document()
                or stock["native_sha256"].removeprefix("sha256:") != native_digest.removeprefix("sha256:")):
            raise ValueError("The exact fixed-reference audit needs the matched stock receipt")
        witnesses = matched_witnesses(gates, snapshots, stock)
    figures, grid, figure_cpu = {}, None, 0.
    if packet is not None:
        began = process_time()
        plots = render(packet, title="ALGO08 conservative fit trial", evaluation_reference=None)
        figure_cpu = process_time() - began
        if tuple(plots) != PLOTS:
            raise ValueError("The normal selected packet must render all eight figures")
        for name, data in plots.items():
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    raise ValueError("The standard renderer must produce PNG evidence")
                image.load()
            figures[name] = sha256(data).hexdigest()
        numerical = packet["position_grid"]
        grid = dict(complete=numerical["complete"], evaluated_points=numerical["evaluated_points"],
                    sha256=canonical_digest({k: v for k, v in numerical.items() if k != "elapsed_seconds"}))

    decision = result["decision"]
    stages = decision["metrics"]["stage_s"]
    return dict(mode=mode, cpu_s=result["cpu_s"], wall_s=result["wall_s"],
                solver_stage_wall_s=stages, recovery=recovery, gates=gates, fixed_reference_witnesses=witnesses,
                decision=decision["status"], reason=decision.get("reason"),
                cavity_offered=decision["metrics"].get("cavity_offered"),
                arms=decision["arms"], grid=grid, png_sha256=figures, figure_cpu_s=figure_cpu,
                publication=None if packet is None else dict(arms=packet["arms"],
                    objective_replay=packet["objective_replay"],
                    position_path_sha256=canonical_digest(packet["position_path"])),
                orbit_policy=result["orbit_policy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("stock", "continued"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--against-stock", type=Path)
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Saved detections differ from the declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    result = run(args.mode, json.loads(raw), TleArchiveReader(args.archive), args.assets, offer,
                 native_digest=args.native_sha256, against_stock=args.against_stock)
    print(json.dumps(dict(result, native_sha256=args.native_sha256, region=offer.document()),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
