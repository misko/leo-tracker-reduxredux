"""Offer one stock-discovered orbital alternative through the genuine merged cavity."""

import json
import os
import runpy
import sys
from pathlib import Path
from time import monotonic, process_time

H = runpy.run_path(str(Path(__file__).with_name("locked_assignments_worker.py")))
point_map, observe = H["point_map"], H["observe"]
ARMS = ("c0", "fitted_c")


def priors(nominations):
    rows = [
        dict(
            source=r["original_norad"],
            alternate=r["best"]["norad"],
            stock_predictive_gain=float(r["predictive_gain"]),
            held=r["held_observation_ids"],
            stock_points=r["held_points"],
        )
        for r in nominations["families"]
        if r["best"] is not None
    ]
    return sorted(rows, key=lambda r: (-r["stock_predictive_gain"], r["source"], r["alternate"]))


def select(hints, assignments, catalogue):
    for hint in hints:
        shared = assignments.keys() & set(hint["held"])
        owners = {assignments[oid]["norad"] for oid in shared}
        pair = {hint["source"], hint["alternate"]}
        if len(shared) >= 4 and len(owners) == 1 and owners <= pair and pair <= catalogue:
            (target,) = owners
            (other,) = pair - owners
            return dict(hint, target=target, challenger=other, matched_points=len(shared))
    return None


def challenger(engine, context, original, offered):
    import numpy as np
    from tools.pipeline_eval.variants.direct_lifetime_kernels import screen

    from tools.pipeline_eval.variants.v5_direct_lifetime import dispose_model

    scan = context["scan"]
    indices = {int(n): k for k, n in enumerate(scan.norads)}
    target, alternate = (indices[offered[k]] for k in ("target", "challenger"))
    family = next((r for r in original["families"] if r["original_index"] == target), None)
    if family is None:
        return None, "shared owner is not an active curved cavity family"
    candidate = next((r for r in family["candidates"] if r["candidate_index"] == alternate), None)
    if candidate is None:
        data = engine.family_data(context, target)
        try:
            chosen = [target, alternate]
            sky = dict(
                time_s=scan.sky["time_s"],
                position_km=scan.sky["position_km"][chosen],
                velocity_km_s=scan.sky["velocity_km_s"][chosen],
            )
            scores, aliases = screen(
                engine,
                sky,
                scan.search_region.latlon(context["x"]),
                context["all_means"][chosen],
                context["widths"][chosen],
                data,
            )
            if not np.isfinite(scores[1]):
                return None, "challenger misses original coarse elevation support"
            candidate = engine.candidate_prediction(context, data, alternate, aliases[1])
        finally:
            dispose_model(data["p"])
    if not candidate["qualified"]:
        return None, "challenger fails original fine phase or elevation gate"
    gain = float(family["original"]["score"] - candidate["score"])
    return dict(family, best=candidate, predictive_gain=gain), None


def assemble(root, flags, role, hints):
    # Establish isolation and single-thread native provider before the numerical imports.
    runpy.run_path(str(root))["activate"](root)
    from leo.analysis.localization_v3 import family_cavity as engine

    from tools.pipeline_eval.variants.orbit_projector import Projector
    from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings

    ordinary, accept = engine.nominate_families, engine.cavity_policy
    state = {}

    def nominate(context):
        raw = ordinary(context)
        if raw["status"] != "complete":
            state["status"] = "ordinary nomination failed"
            return raw
        if role == "stock":
            state["hints"] = priors(raw)
            return raw
        incumbent = any(r["best"] is not None and r["predictive_gain"] > 0 for r in raw["families"])
        state["ordinary_offer"] = incumbent
        if incumbent:
            state["status"] = "ordinary union already offers a cavity hypothesis"
            return raw
        state["ordinary_arms"] = {arm: H["point"](v) for arm, v in context["arms"].items()}
        signed = point_map(context, context["node"], context["entries"])
        assignments = signed["curved"] | signed["predictive"]
        chosen = select(hints, assignments, {int(n) for n in context["scan"].norads})
        if chosen is None:
            state["status"] = "no stock hint maps to a coherent union owner"
            return raw
        state["hint"] = {k: v for k, v in chosen.items() if k != "held"}
        began, cpu = monotonic(), process_time()
        extra, failure = challenger(engine, context, raw, chosen)
        state["extra_screen"] = dict(wall_s=monotonic() - began, cpu_s=process_time() - cpu)
        if extra is None:
            state["status"] = failure
            return raw
        state["union_predictive_gain"] = extra["predictive_gain"]
        state["union_held_points"] = extra["held_points"]
        state["proposal"] = extra
        if extra["predictive_gain"] <= 0:
            state["status"] = "challenger rejected by original union predictive gain"
            return raw
        state["status"] = "challenger offered to original acceptance"
        return dict(raw, families=[*raw["families"], extra])

    def policy(context, nominations):
        result = accept(context, nominations)
        if "proposal" in state and result["status"] == "complete" and not result["accepted"]:
            (rejected,) = result["trials"]
            state["rejected_arms"] = {arm: H["point"](v) for arm, v in rejected["arms"].items()}
            state["forced_pair_valid"] = rejected["paired_valid"]
            state["forced_constrained"] = rejected["constrained_refinement_attempted"]
        return result

    engine.nominate_families, engine.cavity_policy = nominate, policy
    try:
        data = observe(root, flags)
    finally:
        engine.nominate_families, engine.cavity_policy = ordinary, accept
    result = data["production"]
    output = dict(production=result)
    extra = state.pop("proposal", None)
    if role == "merged":
        output["accepted"] = data.get("adopted", False) and extra is not None
        output["trial_receipts"] = data.get("trials", [])
        if extra and extra["predictive_gain"] <= 0:
            context = data["context"]
            started, cpu = monotonic(), process_time()
            with numerical_bindings(Projector(root / "projector.so")):
                forced = engine.trial(context, [(extra, extra["best"])])
            output.update(
                forced={arm: H["point"](v) for arm, v in forced["arms"].items()},
                forced_pair_valid=forced["paired_valid"],
                forced_constrained=forced["constrained_refinement_attempted"],
                diagnostic_refit=dict(wall_s=monotonic() - started, cpu_s=process_time() - cpu),
            )
        elif extra and not output["accepted"]:
            # Capture original rejected refit, with no second forced evaluation.
            output["forced"] = state.pop("rejected_arms", None)
    output.update(state)
    return output


def run(root, folder, cpu, role, source, flags):
    path = H["group"]()
    start = H["resources"](path)
    if (
        start["memory.max"] != 512 * 2**20
        or start["memory.swap.max"]
        or os.sched_getaffinity(0) != {int(cpu)}
        or os.nice(0) != 10
    ):
        raise ValueError("unexpected CPU, priority, memory or swap cap")
    hints = json.loads(source.read_bytes())["hints"] if role == "merged" else []
    began, cpu_began = monotonic(), process_time()
    result = assemble(root, flags, role, hints)
    result["resources"] = dict(
        start=start,
        end=H["resources"](path),
        wall_s=monotonic() - began,
        cpu_s=process_time() - cpu_began,
    )
    H["save"](folder / "outcome.json", result)


if __name__ == "__main__":
    _, root, folder, cpu, role, source, *flags = sys.argv
    run(Path(root), Path(folder), cpu, role, Path(source), flags)
