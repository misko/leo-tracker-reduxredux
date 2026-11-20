"""Observe authentic winning configurations and run their fixed-assignment refits."""

import argparse
import copy
import io
import json
import os
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path
from time import monotonic, process_time

helpers = runpy.run_path(str(Path(__file__).with_name("locked_assignments.py")))
point_map, matching = (helpers[name] for name in ("point_map", "matching"))
probe = runpy.run_path(str(Path(__file__).with_name("ranked_fit_probe.py")))
group, resources = (probe[name] for name in ("group", "resources"))
ARMS = ("c0", "fitted_c")
BOUNDARY = "Phase-release fixed-assignment continuous position refit"


def observe(root, flags):
    watch = {
        ("signed_context.py", "signed_context"): "signed",
        ("history_policy.py", "history_policy"): "history",
        ("family_cavity.py", "cavity_policy"): "cavity",
        ("conservative_recovery.py", "conservative_recovery"): "conservative",
    }
    monitoring = sys.monitoring
    events = monitoring.events
    seen, data = {}, {}

    def enter(code, _offset):
        file = Path(code.co_filename)
        name = watch.get((file.name, code.co_name))
        if name and file.is_relative_to(root):
            seen[code] = name
            monitoring.set_local_events(4, code, events.PY_RETURN)
        return monitoring.DISABLE

    def leave(code, _offset, result):
        name = seen[code]
        if name == "signed":
            data["context"] = result
        elif name == "cavity":
            data["adopted"] = bool(result["accepted"])
            data["selected"] = result["selected"]
            data["trials"] = [
                dict(
                    replacements=row["replacements"],
                    paired_valid=row["paired_valid"],
                    constrained=row["constrained_refinement_attempted"],
                )
                for row in result["trials"]
            ]
        elif name == "history":
            data["history_linear"] = bool(result.get("linear_paired_valid"))
        else:
            # Observe assignments after conservative recovery without retaining its model.
            if result["status"] == "complete":
                scan = sys._getframe(1).f_locals["scan"]
                data["conservative"] = point_map(
                    {"scan": scan, "keep": result["final_mask"]}, result["final_node"], []
                )

    monitoring.use_tool_id(4, "authentic assigned points")
    monitoring.register_callback(4, events.PY_START, enter)
    monitoring.register_callback(4, events.PY_RETURN, leave)
    monitoring.set_events(4, events.PY_START)
    sys.argv = [str(root), *flags]
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            runpy.run_path(str(root), run_name="__main__")
    finally:
        monitoring.set_events(4, 0)
        for code in seen:
            monitoring.set_local_events(4, code, 0)
        monitoring.free_tool_id(4)
    prediction = json.loads(buffer.getvalue())
    data["production"] = prediction
    return data


def point(arm):
    return dict(
        latlon=list(arm["endpoint_latlon"]),
        rf_rms_hz=float(arm["RMS_hz"]),
        frequency_objective=float(arm["negative_twice_elbo"]),
    )


def configuration(data):
    context = data["context"]
    if data.get("adopted"):
        selected = data["selected"]
        return "cavity", selected["node"], selected["entries"], selected["means"], selected["arms"]
    if context["signed"]["accepted"]:
        method = "event"
    else:
        method = "linear" if data["history_linear"] else "curved"
    return method, context["node"], context["entries"], context["means"], context["arms"]


def run_fit(context, node, entries, means, keep, role, *, full=False):
    from leo.analysis.localization_v3 import (
        event_position,
        family_cavity,
        history_position,
        predictive_linear,
    )

    scan, powers, model = (context[k] for k in ("scan", "powers", "model"))
    if full and role == "cavity":
        return family_cavity.fit_configuration(dict(context, keep=keep), node, entries, means)[
            "arms"
        ]
    pair = {}
    for arm in ARMS:
        if role in ("event", "cavity"):
            fitted = event_position.refit(scan, node, keep, arm, powers, means, model, [], entries)
        elif role == "linear" and entries:
            fitted = predictive_linear.refit(scan, node, keep, powers, means, model, arm, entries)
        else:
            fitted = history_position.refit(
                scan, node, keep, arm, powers, means, model["multiplier"], model["nu"]
            )
        pair[arm] = fitted
    return pair


def residuals(context, node, entries, means, keep, role, arm, record):
    import numpy as np
    from leo.analysis.localization_v3 import event_position, history_position, predictive_linear
    from leo.analysis.localization_v3.cavity_prediction import legacy_phase_reference

    from tools.pipeline_eval.variants.v5_direct_lifetime import dispose_model

    scan, powers, model = (context[k] for k in ("scan", "powers", "model"))

    def base(reference):
        return history_position.make_problem(
            scan, node, keep, arm, reference, powers, means, model["multiplier"], model["nu"]
        )

    reference = np.asarray(record["phase_reference"])
    if role in ("event", "cavity"):
        p = event_position.make_event_problem(
            scan, node, keep, arm, reference, powers, means, model, []
        )
        event_position.attach_event_predictive(p, entries, powers)
    elif role == "linear" and entries:
        p = base(reference)
        predictive_linear.attach_predictive_linear(p, entries, powers)
    else:

        def posterior(ref, x):
            model_at_round = base(ref)
            state = model_at_round.state(x)["phases"][model_at_round.labels]
            dispose_model(model_at_round)
            return state

        reference = legacy_phase_reference(record["history"], np.zeros(len(means)), posterior)
        p = base(reference)
    x = np.asarray(record["endpoint_east_north_km"])
    computed = p.calculate(x)
    value = computed["conditional_residual_hz"]
    if np.sqrt(np.mean(value[keep] ** 2)) != record["RMS_hz"]:
        raise ValueError("posterior replay failed its exact conditional RMS check")
    dispose_model(p)
    return value


def refits(data, receipt, union, root):
    import numpy as np
    from leo.analysis.localization_v3.history_policy import pair_passes

    from leo.analysis.research.retained_track_likelihood import PERIOD
    from tools.pipeline_eval.variants.orbit_projector import Projector
    from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings
    from tools.pipeline_eval.variants.v5_direct_lifetime import reclaim

    context = data["context"]
    role, node, entries, means, original = configuration(data)
    scan = context["scan"]
    catalogue = {int(norad): j for j, norad in enumerate(scan.norads)}
    stock = receipt["final"]["curved"]
    common, shifts, counts = matching(stock, union["final"]["curved"], catalogue.keys(), PERIOD)
    keep = np.zeros_like(context["keep"])
    keep[[stock[oid]["index"] for oid in common]] = True
    held = context["keep"] & ~keep
    changed = copy.deepcopy(node)
    for row in changed["seed"]["rows"]:
        if row["component"] in shifts:
            norad = shifts[row["component"]]["union"]
            row.update(candidate_index=catalogue[norad], candidate_norad=norad)
    changed_labels = sorted(
        {row["candidate_index"] for row in changed["seed"]["rows"] if row["active_curvature"]}
    )
    changed_means = context["all_means"][changed_labels]
    reference_labels = sorted(
        {row["candidate_index"] for row in node["seed"]["rows"] if row["active_curvature"]}
    )
    # Preserve the exact chosen stock means on original coordinates through the cross.
    saved_means = dict(zip(reference_labels, means, strict=True))
    for k, label in enumerate(changed_labels):
        changed_means[k] = saved_means.get(label, changed_means[k])
    locked_entries = (
        entries if set(e["candidate_index"] for e in entries) <= set(changed_labels) else []
    )
    measures, cells = {}, {}
    projector = Projector(root / "projector.so")
    with numerical_bindings(projector):
        started, cpu = monotonic(), process_time()
        replay = run_fit(context, node, entries, means, context["keep"], role, full=True)
        control = {a: point(replay[a]) for a in ARMS}
        measures["replay"] = dict(wall_s=monotonic() - started, cpu_s=process_time() - cpu)
        control_match = control == {a: point(original[a]) for a in ARMS}
        if keep.any():
            for name, current, prior in (
                ("stock_identity", node, means),
                ("union_identity", changed, changed_means),
            ):
                reclaim()
                began, begin_cpu = monotonic(), process_time()
                pair = run_fit(context, current, locked_entries, prior, keep, role)
                valid = pair_passes(
                    pair,
                    include_linear=bool(locked_entries),
                    half_width_km=scan.search_region.half_width_km,
                )
                arms = {}
                for arm, record in pair.items():
                    res = residuals(
                        context, current, locked_entries, prior, keep, role, arm, record
                    )
                    current_point = point(record)
                    arms[arm] = dict(
                        latlon=current_point["latlon"] if valid else None,
                        forced_latlon=current_point["latlon"] if not valid else None,
                        rf_rms_hz=current_point["rf_rms_hz"],
                        withheld_stock_rms_hz=float(np.sqrt(np.mean(res[held] ** 2)))
                        if held.any()
                        else None,
                        failed_curved_gates=sum(
                            not row["compatible"] for row in record["gates"]["tracks"]
                        ),
                        frequency_objective=current_point["frequency_objective"],
                    )
                cells[name] = dict(
                    status="ok" if valid else "withheld",
                    boundary=BOUNDARY,
                    arms=arms,
                    metrics=dict(
                        common_curved=int(keep.sum()),
                        omitted_stock_curved=int(held.sum()),
                        predictive_stock=sum(e["points"] for e in locked_entries),
                    ),
                )
                if not valid:
                    cells[name]["reason"] = "Matched fixed hypothesis failed original paired gates"
                measures[name] = dict(wall_s=monotonic() - began, cpu_s=process_time() - begin_cpu)
    return dict(
        stock_replay=control,
        stock_replay_exact=control_match,
        measures=measures,
        fits=cells,
        counts=counts,
        shifts=shifts,
        original_stock_predictive_points=sum(e["points"] for e in entries),
        matched_predictive_points=sum(e["points"] for e in locked_entries),
    )


def save(path, payload):
    with path.open("x") as file:
        json.dump(payload, file, allow_nan=False)


def worker(root, out, cpu, role, union_path, flags):
    cgroup = group()
    cap = resources(cgroup)
    if cap["memory.max"] != 512 * 2**20 or cap["memory.swap.max"] or cap["memory.swap.current"]:
        raise ValueError("worker requires real 512 MiB zero-swap service")
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) != 10:
        raise ValueError("worker requires its recorded CPU affinity and priority")
    start, cpu_start = monotonic(), process_time()
    data = observe(root, flags)
    result = data["production"]
    receipt = dict(production=result, cpu_s=process_time() - cpu_start, wall_s=monotonic() - start)
    if result["status"] == "ok":
        method, node, entries, _, _ = configuration(data)
        context = data["context"]
        receipt.update(
            role=method,
            cavity_offered=result["metrics"]["cavity_offered"],
            cavity_adopted=data.get("adopted", False),
            cavity_trials=data.get("trials", []),
            signed={arm: point(r) for arm, r in context["arms"].items()},
            final=point_map(context, node, entries),
            conservative=data["conservative"],
        )
    save(out / "capture.json", receipt)
    if role == "stock" and result["status"] == "ok":
        with union_path.open() as f:
            union = json.load(f)
        save(out / "refits.json", refits(data, receipt, union, root))
    save(
        out / "resources.json",
        dict(
            start=cap,
            end=resources(cgroup),
            cpu_s=process_time() - cpu_start,
            wall_s=monotonic() - start,
            cpu=cpu,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("cpu", type=int)
    parser.add_argument("role", choices=("stock", "union"))
    parser.add_argument("union", type=Path)
    parser.add_argument("flags", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    worker(args.root, args.out, args.cpu, args.role, args.union, args.flags)
