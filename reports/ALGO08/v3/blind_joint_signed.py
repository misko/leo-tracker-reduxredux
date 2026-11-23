"""Original causal signed endpoint update on fixed blind curved and predictive support."""

from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3 import event_position
from leo.analysis.localization_v3.history_policy import pair_passes, validate_history
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.analysis.localization_v3.signed_phase import adjust_means, qualify

from blind_joint_finish import ARMS, digest, elapsed, readout


def fitted_pair(candidate, means):
    return {arm: event_position.refit(
        candidate["scan"], candidate["node"], candidate["keep"], arm,
        candidate["powers"], means, candidate["model"], [], candidate["entries"],
    ) for arm in ARMS}


def update(prepared, ordinary, measured, *, fit_pair=None):
    scan, model = ordinary["scan"], ordinary["model"]
    cpu, wall = process_time(), perf_counter()
    raw, forecast = prepared["phase_history"], prepared["phase_forecast"]
    history_sha = digest(raw)
    cutoff = prepared["sky"]["metadata"]["cutoff_utc_ns"]
    if forecast.get("history_sha256", history_sha) != history_sha:
        raise ValueError("phase history and prediction digest differ")
    recognized, _ = validate_history(raw, dict(forecast, history_sha256=history_sha), case="SCAN",
                                     origin_utc_ns=scan.origin_utc_ns, cutoff_utc_ns=cutoff,
                                     raw_sha256=history_sha)
    if recognized != model or any(r["validation_time_ns"] > cutoff for r in forecast["transitions"]):
        raise ValueError("unqualified incumbent or post-scan signed transition")
    selection = qualify(forecast["transitions"], forecast["temporal_split_boundary_ns"],
                        forecast["prefix_distribution"], model)
    detail = dict(selection=selection, history_sha256=history_sha, status="unqualified")
    measured.update(signed=detail, signed_qualify_clocks=elapsed(cpu, wall))
    if not selection["qualified"]:
        return ordinary
    cpu, wall = process_time(), perf_counter()
    labels = sorted({row["candidate_index"] for row in ordinary["node"]["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    means = adjust_means(ordinary["means"], receipts, model, selection)
    measured["signed_prior_clocks"] = elapsed(cpu, wall)
    detail.update(status="rejected", means_s=means, ordinary_means_s=ordinary["means"])
    cpu, wall = process_time(), perf_counter()
    try:
        fitted = (fitted_pair if fit_pair is None else fit_pair)(ordinary, means)
    except (AssertionError, ValueError, np.linalg.LinAlgError) as exc:
        detail["reason"] = f"{type(exc).__name__}: {exc}"
        return ordinary
    finally:
        measured["signed_refit_clocks"] = elapsed(cpu, wall)
    detail["finish"] = {arm: readout({**row, "history": [dict(step, movement_km=None)
                                                       for step in row["history"]]}) for arm, row in fitted.items()}
    if not pair_passes(fitted, include_linear=True, half_width_km=scan.search_region.half_width_km):
        detail["reason"] = "original_signed_pair_gate"
        return ordinary
    detail["status"] = "accepted"
    return dict(ordinary, arms=fitted, means=means)


def endpoints(arms):
    return {arm: np.asarray(row["endpoint_east_north_km"]) for arm, row in arms.items()}


def describe(candidate):
    scan, node = candidate["scan"], candidate["node"]
    source = {track["key"]: track for track in scan.tracks}
    roles, weights = {}, {}
    last = 0
    rows = node["seed"]["rows"]
    for row, alias, power in zip(rows, node["aliases"], candidate["powers"], strict=True):
        name = row["component"]
        ids = source[name]["observation_ids"]
        keep = candidate["keep"][last:last + len(ids)]
        last += len(ids)
        if np.any(keep):
            weights[name] = float(power)
            roles[name] = dict(norad=int(row["candidate_norad"]), alias=int(alias),
                               ids=[oid for oid, use in zip(ids, keep, strict=True) if use])
    if last != len(candidate["keep"]):
        raise ValueError("The captured support does not match its curved mask")
    norads = [int(scan.norads[j]) for j in sorted({row["candidate_index"] for row in rows})]
    return dict(curved=roles, weights=weights, predictive={e["component"]: dict(norad=e["norad"], alias=e["alias"],
                ids=e["observation_ids"], cross_receiver=e["cross_receiver_curved_support"]) for e in candidate["entries"]},
                model=candidate["model"], means_s=dict(zip(norads, candidate["means"], strict=True)),
                arms={arm: dict(endpoint_east_north_km=data["endpoint_east_north_km"],
                                  phase_reference_s=dict(zip(norads, data["phase_reference"], strict=True)),
                                  optimizer_endpoints=[step["fit"]["parameters"] for step in data["history"]])
                      for arm, data in candidate["arms"].items()})


def northern_trace(ordinary, signed, stock_context, stock_arms):
    stock = dict(stock_context, arms=stock_arms)
    cold = dict(ordinary, arms=fitted_pair(ordinary, ordinary["means"]))
    routes = dict(warm_ordinary=ordinary, cold_ordinary=cold, cold_signed=signed, stock=stock)
    evidence = {name: describe(candidate) for name, candidate in routes.items()}
    tested = {}
    for arm in ARMS:
        coordinates = {name: endpoints(candidate["arms"])[arm] for name, candidate in routes.items()}
        stock_point = coordinates["stock"].copy()
        edge = float(ordinary["scan"].search_region.half_width_km)
        dimension = int(np.argmax(abs(stock_point)))
        if abs(abs(stock_point[dimension]) - edge) <= 1e-8:
            stock_point[dimension] -= np.sign(stock_point[dimension]) * .001
            coordinates["stock_inward_1m"] = stock_point
        readback = {}
        for name, candidate in routes.items():
            model = event_position.make_event_problem(candidate["scan"], candidate["node"], candidate["keep"],
                                                       arm, candidate["arms"][arm]["phase_reference"],
                                                       candidate["powers"], candidate["means"], candidate["model"], [])
            event_position.attach_event_predictive(model, candidate["entries"], candidate["powers"])
            readback[name] = {}
            for location, point in coordinates.items():
                residual = model.residual(point)
                readback[name][location] = float(residual @ residual)
        tested[arm] = dict(coordinates=coordinates, fixed_reference_objectives=readback)
    return dict(support=evidence, objective_samples=tested)
