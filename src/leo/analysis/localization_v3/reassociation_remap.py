"""Apply admitted whole-family identities to an isolated numerical context."""

from copy import copy, deepcopy

import numpy as np
from sgp4.api import Satrec

from leo.analysis.localization_v3.history_position import forecast_phase_mean
from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.reassociation_context import ARMS, build
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.sky.propagation import ElementSetCatalogue


def remap(context, hypothesis, ledger):
    result = dict(
        context, node=deepcopy(context["node"]), entries=deepcopy(context["entries"]), problems={}
    )
    scan = copy(context["scan"])
    result["scan"] = scan
    base = context["problems"]["fitted_c"][0]
    for number in sorted(set(hypothesis["mapping"].values())):
        if number in scan.norads:
            continue
        record = ledger[str(number)]
        catalogue = ElementSetCatalogue(
            (str(number),), (number,), (Satrec.twoline2rv(*record["lines"]),)
        )
        pos, vel, good = ecef_states(catalogue, scan.origin_utc_ns, scan.sky["time_s"])
        if not good.all():
            raise ValueError("causal candidate propagation failed")
        scan.norads = np.r_[scan.norads, number]
        scan.sky = dict(
            scan.sky,
            position_km=np.concatenate([scan.sky["position_km"], pos]),
            velocity_km_s=np.concatenate([scan.sky["velocity_km_s"], vel]),
            phase_sigma_s=np.r_[scan.sky["phase_sigma_s"], 1.0],
        )
        scan.elements = dict(
            scan.elements,
            **{
                str(number): dict(
                    lines=record["lines"],
                    provenance={k: v for k, v in record.items() if k != "lines"},
                )
            },
        )
        result["node"]["seed"]["state"]["phases"] = np.r_[
            result["node"]["seed"]["state"]["phases"], 0.0
        ]
    for row in result["node"]["seed"]["rows"]:
        key = row["component"]
        if key in hypothesis["mapping"]:
            number = hypothesis["mapping"][key]
            row.update(candidate_norad=number, candidate_index=list(scan.norads).index(number))
    for k, row in enumerate(base.rows):
        if row["component"] in hypothesis["aliases"]:
            result["node"]["aliases"][k] = hypothesis["aliases"][row["component"]]
    destinations = {}
    for row in base.rows:
        destinations.setdefault(row["candidate_norad"], set()).add(
            hypothesis["mapping"].get(row["component"], row["candidate_norad"])
        )
    for entry in result["entries"]:
        if entry["component"] in hypothesis["mapping"]:
            entry["norad"] = hypothesis["mapping"][entry["component"]]
            entry["candidate_index"] = list(scan.norads).index(entry["norad"])
        elif len(destinations.get(entry["norad"], set())) == 1:
            entry["norad"] = next(iter(destinations[entry["norad"]]))
            entry["candidate_index"] = list(scan.norads).index(entry["norad"])
    labels = sorted({row["candidate_index"] for row in result["node"]["seed"]["rows"]})
    old_means = dict(zip(base.labels, context["means"], strict=True))
    result["means"] = np.array([old_means.get(j, 0.0) for j in labels])
    for arm in ARMS:
        old, x = context["problems"][arm]
        refs = dict(zip(old.labels, old.reference, strict=True))
        ref = np.array(
            [refs.get(j, hypothesis["phases"].get(str(int(scan.norads[j])), 0.0)) for j in labels]
        )
        result["problems"][arm] = old, x
        result["problems"][arm] = build(result, arm, ref)[0], x
    base = result["problems"]["fitted_c"][0]
    _, receipt = phase_widths(scan, base.labels)
    forecast = forecast_phase_mean(receipt, result["model"]["shrinkage"])
    result["means"] = np.array([old_means.get(j, forecast[k]) for k, j in enumerate(base.labels)])
    for arm, (problem, x) in list(result["problems"].items()):
        result["problems"][arm] = build(result, arm, problem.reference)[0], x
    return result
