"""Time two exact-likelihood grid kernels on the same fixed selected solution."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import event_position
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation import localization_v3 as presentation
from tools import algo08_position
from tools.pipeline_eval.variants.algo08_grid_triangular import triangular_prediction
from solver_trial import measure


ARMS = ("c0", "fitted_c")
SCIENCE = ("arms", "objective_replay", "position_path")


def arm_dependencies(context):
    control, fitted = (context["problems"][arm][0] for arm in ARMS)
    common_rows = (np.array_equal(control.flat_times, fitted.flat_times)
                   and np.array_equal(control.flat_labels, fitted.flat_labels)
                   and control.labels == fitted.labels)
    reference_delta = None
    if common_rows:
        reference_delta = np.abs(control.reference - fitted.reference)[fitted.flat_labels]
    return dict(
        rows={arm: int(context["problems"][arm][0].keep.sum()) for arm in ARMS},
        common_time_label_rows=bool(common_rows),
        equal_reference_rows=None if reference_delta is None else int(np.count_nonzero(reference_delta == 0)),
        total_reference_rows=None if reference_delta is None else len(reference_delta),
        max_phase_reference_delta_s=None if reference_delta is None else float(max(reference_delta, default=0.)),
        nonzero_fitted_rf_rows=int(np.count_nonzero(fitted.hardware[fitted.keep, -1])),
        predictive_tracks=len(context["entries"]),
    )


def compare_grids(before, after):
    control, trial = before["position_grid"], after["position_grid"]
    if not control["complete"] or not trial["complete"]:
        raise ValueError("Both arms must evaluate their complete ordered grid")
    skip = {"elapsed_seconds", "points"}
    same_metadata = all(control[k] == trial[k] for k in control.keys() - skip)
    if not same_metadata or any(before[k] != after[k] for k in SCIENCE):
        raise ValueError("Kernel trial changed the fixed fit, path or grid metadata")
    errors = {arm: [] for arm in ARMS}
    for first, second in zip(control["points"], trial["points"], strict=True):
        if any(first[k] != second[k] for k in first.keys() - {"scores"}):
            raise ValueError("The evaluated coordinates or exact failure rows differ")
        for arm in ARMS:
            x, y = first["scores"][arm], second["scores"][arm]
            if (x is None) != (y is None):
                raise ValueError("A previously scored grid location changed validity")
            if x is not None:
                errors[arm].append(abs(x - y))
    return {arm: dict(scored=len(err), changed=sum(delta != 0 for delta in err),
                      max_absolute_score_delta=max(err, default=None)) for arm, err in errors.items()}


def run(native, archive, assets, region, candidate_first):
    base_packet, base_prepare = algo08_position.selected_packet, algo08_position.prepare_packet
    stock_grid, stock_prediction = presentation.sample_position_grid, event_position.predictive_residual
    results, packets = {}, {}
    order = ("triangular", "stock") if candidate_first else ("stock", "triangular")

    def selected_packet(*args):
        for mode in order:
            operation = triangular_prediction if mode == "triangular" else stock_prediction
            counters = dict(predictive_calls=0, predictive_cpu_ns=0)

            def prepare(context, *args, **kwargs):
                if mode == order[0]:
                    results["arm_dependencies"] = arm_dependencies(context)
                return base_prepare(context, *args, **kwargs)

            def prediction(*args, **kwargs):
                start = process_time_ns()
                try:
                    return operation(*args, **kwargs)
                finally:
                    counters["predictive_calls"] += 1
                    counters["predictive_cpu_ns"] += process_time_ns() - start

            def grid(*args, **kwargs):
                start = process_time_ns()
                with patch.object(event_position, "predictive_residual", prediction):
                    result = stock_grid(*args, **kwargs)
                counters["grid_cpu_ns"] = process_time_ns() - start
                counters["evaluated_points"] = result["evaluated_points"]
                return result

            start = process_time_ns()
            with patch.object(presentation, "sample_position_grid", grid), patch.object(
                algo08_position, "prepare_packet", prepare,
            ):
                packets[mode] = base_packet(*args)
            counters["packet_cpu_ns"] = process_time_ns() - start
            results[mode] = counters
        return packets["stock"]

    with patch.object(algo08_position, "selected_packet", selected_packet):
        result = measure("combined", native, archive, assets, region)
    stats = compare_grids(packets["stock"], packets["triangular"])
    return dict(grid=results, score_differential=stats, order=order,
                solver_prefix_cpu_s=result["cpu_s"] - result["stages"]["selected_packet"]["cpu_s"],
                decision=result["decision"]["status"], arms=result["decision"]["arms"],
                owners={arm: result["evidence"]["arms"][arm]["owner_sha256"] for arm in ARMS},
                owner_counts={arm: result["evidence"]["arms"][arm]["associated_points"] for arm in ARMS})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--candidate-first", action="store_true")
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Saved detections differ from their declared digest")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    result = run(json.loads(raw), TleArchiveReader(args.archive), args.assets, region, args.candidate_first)
    print(json.dumps(dict(result, native_sha256=args.native_sha256, region=region.document()),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
