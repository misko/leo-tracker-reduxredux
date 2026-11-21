"""Native v5 position inference through the paired cavity decision on a single CPU."""

import hashlib
import json
import sys
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np

from tools.pipeline_eval.variants import v5_lean

BOUNDARY = "Native detector output, causal sky, initial association and paired cavity positions"


def cold_node(scan, node):
    from leo.analysis.localization_v3.discovery import zero_state

    return dict(
        seed=dict(rows=node["seed"]["rows"], state=zero_state(scan)), aliases=node["aliases"]
    )


def ranked_initial_nodes(scan):
    from leo.analysis.localization_v3.discovery import (
        explore,
        fresh_discovery,
        signature,
    )
    from leo.analysis.localization_v3.families import AnchoredFamilies
    from leo.analysis.localization_v3.position import NormalPosition

    sigma = scan.radio_sigma_hz
    seeds = fresh_discovery(scan, sigma, budget=4)
    best = min(seeds, key=lambda row: row["center_score"])
    radius = scan.search_region.half_width_km
    nodes = list(seeds)
    for point in product((-radius, radius), repeat=2):
        seed, _ = explore(
            scan, best["seed"]["state"], point, "receiver_smooth", compact_update=False
        )
        anchored = AnchoredFamilies(scan, seed, "receiver_smooth", False, point)
        nodes.append(dict(seed=seed, aliases=anchored.alias))
    unique = {}
    for node in nodes:
        unique.setdefault(signature(node), node)
    ranked = []
    for node in unique.values():
        rows = node["seed"]["rows"]
        cold = cold_node(scan, node)
        zero = np.zeros(len({r["candidate_index"] for r in rows}))
        model = NormalPosition(scan, cold, sigma, False, reference=zero)
        residual = model.residual(np.zeros(2))
        ranked.append((float(residual @ residual), cold))
    return [node for _, node in sorted(ranked, key=lambda entry: entry[0])]


def fit_initial_nodes(scan, cold_nodes):
    """Select the minimum refreshed c=0 loss and retain its track gate for both arms."""
    from leo.analysis.localization_v3.acceptance import actual_metrics
    from leo.analysis.localization_v3.position import refreshed

    sigma = scan.radio_sigma_hz
    winner = None
    for cold in cold_nodes:
        model, fit, _ = refreshed(scan, sigma, cold, "c0", rounds=5, iterations=48)
        if winner is None or fit["score"] < winner[0]["score"]:
            winner = fit, model, cold
    fit, model, cold = winner
    xy = fit["parameters"]
    result = dict(
        rows=model.rows, state=model.state(xy), aliases=model.alias, east_north_km=xy, fits=[fit]
    )
    metrics = actual_metrics(model, result, "c0", xy)
    choice = dict(hypothesis=0, node=cold, arms={"c0": {"metrics": metrics}})
    return {"choices": [choice], "selected_hypothesis": 0}, len(cold_nodes)


def initial_selection(scan):
    return fit_initial_nodes(scan, ranked_initial_nodes(scan)[:3])


def scan_context(prepared, region, noise_digest, bound, previous):
    from leo.analysis.localization_v3.scan import ScanLikelihood

    sky = prepared["sky"]
    receipt = sky[previous + "_receipt"]
    return ScanLikelihood(
        prepared["tracks"]["tracks"],
        sky["bank"],
        sky["nominal_elements"],
        origin_utc_ns=sky["metadata"]["origin_utc_ns"],
        regional_center=sky["metadata"]["regional_center"],
        noise=prepared["noise"],
        noise_sha256=noise_digest,
        search_region=region,
        bound=bound,
        previous_tle=sky[previous + "_tle"],
        previous_tle_sha256=receipt["catalogue_sha256"],
        previous_sources=receipt.get("sources"),
    )


def infer(prepared, region, bound, stage_s, *, select_initial=None, selected_evidence=None):
    from leo.analysis.localization_v3.conservative_recovery import conservative_recovery
    from leo.analysis.localization_v3.family_cavity import cavity_policy, nominate_families
    from leo.analysis.localization_v3.history_policy import history_policy
    from leo.analysis.localization_v3.signed_context import signed_context

    def withheld(reason):
        return dict(
            status="withheld",
            boundary=BOUNDARY,
            reason=reason,
            metrics={"stage_s": stage_s},
            arms={a: {"latlon": None} for a in v5_lean.ARMS},
        )

    if prepared["status"] != "inputs_prepared":
        return withheld(prepared["status"])
    observations = prepared["tracks"]["observations"]
    start = perf_counter()
    noise = hashlib.sha256(
        (json.dumps(prepared["noise"], sort_keys=True) + "\n").encode()
    ).hexdigest()
    first = scan_context(prepared, region, noise, bound, "previous")
    initial, branches = (select_initial or initial_selection)(first)
    del first
    stage_s["initial"] = perf_counter() - start
    start = perf_counter()
    scan = scan_context(prepared, region, noise, bound, "genuine_previous")
    conservative = conservative_recovery(scan, initial, observations)
    stage_s["conservative"] = perf_counter() - start
    if conservative["status"] != "complete":
        return withheld(conservative["status"])
    history = prepared["phase_history"]
    digest = hashlib.sha256((json.dumps(history, sort_keys=True) + "\n").encode()).hexdigest()
    forecast = dict(prepared["phase_forecast"], history_sha256=digest)
    if prepared["phase_forecast"].get("history_sha256", digest) != digest:
        raise ValueError("causal phase history has changed")
    common = dict(
        case="SCAN",
        cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"],
        history_sha256=digest,
    )
    start = perf_counter()
    family = history_policy(scan, conservative, history, forecast, **common)
    stage_s["family"] = perf_counter() - start
    if family["status"] != "accepted":
        return withheld(family["status"])
    start = perf_counter()
    signed = signed_context(scan, conservative, family, history, forecast, observations, **common)
    stage_s["signed"] = perf_counter() - start
    start = perf_counter()
    nominations = nominate_families(signed)
    if nominations["status"] != "complete":
        raise ValueError(f"cavity nomination failed: {nominations.get('error')}")
    offered = any(
        f["best"] is not None and f["predictive_gain"] > 0 for f in nominations["families"]
    )
    arms = signed["arms"]
    fit = None
    if offered:
        fit = cavity_policy(signed, nominations)
        if fit["status"] != "complete":
            raise ValueError(f"cavity fit failed: {fit.get('error')}")
        arms = fit["policy_arms"]
    stage_s["cavity"] = perf_counter() - start
    if selected_evidence is not None:
        selected_evidence(prepared, signed, fit)
    return dict(
        status="ok",
        boundary=BOUNDARY,
        arms={
            a: {"latlon": list(arms[a]["endpoint_latlon"]), "rf_rms_hz": float(arms[a]["RMS_hz"])}
            for a in v5_lean.ARMS
        },
        metrics=dict(
            stage_s=stage_s,
            initial_branches=branches,
            initial_arm_fits=branches,
            cavity_offered=offered,
            observations=len(observations),
            tracks=len(prepared["tracks"]["tracks"]),
        ),
    )


def worker(request_file, result_file, *, select_document=None, select_initial=None):
    original, request, job = v5_lean.bound_request(request_file)
    engine = original.ev.owned_import("leo.application.localization_v3_engine", request["source"])
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v4.backend import ProcessBound
    from leo.operations.localization_v3_job import read_bound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    backend = ProcessBound(request["native_manifest"], Path(job["output_root"]) / "receipts/native")
    document = read_bound(job["native_input"])
    if document["source"]["session_id"] != job["identity"]["session_id"]:
        raise ValueError("native observations belong to a different session")
    start = perf_counter()
    selected = {}
    if select_document is not None:
        document, selected = select_document(document)
    center = job["screen_center"]
    if select_document is not None and not document["source"]["probes"]:
        prepared = {"status": "no_scheduled_probes"}
    else:
        prepared = engine._prepared_values(
            engine.policy.prepare_native_scan(
                document,
                TleArchiveReader(Path(job["tle_root"])),
                TrackConfig(**read_bound(job["track_config"])["config"]),
                screen_latitude_deg=center[0],
                screen_longitude_deg=center[1],
            )
        )
    initial_options = {} if select_initial is None else {"select_initial": select_initial}
    result = infer(
        prepared,
        SearchRegion(tuple(job["search_center"])),
        backend,
        {"native_preparation": perf_counter() - start},
        **initial_options,
    )
    result["metrics"].update(selected)
    original.check_scientific_inputs(request)
    if original.ev.source_binding(v5_lean.SOURCE) != request["source"]:
        raise ValueError("frozen source changed during inference")
    original.write(result_file, result)


def run(case, work_dir):
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__))


if __name__ == "__main__":
    worker(*sys.argv[1:])
