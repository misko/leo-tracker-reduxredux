"""Seed the repaired joint solver with a blind mixture point and a fresh full assignment."""

from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3 import discovery, position
from leo.analysis.localization_v3.families import AnchoredFamilies
from leo.analysis.research.retained_track_likelihood import PERIOD
from tools.pipeline_eval.variants import v5_core

from mixture_finish import digest
from mixture_position import propose
from mixture_trial import elapsed


def receiver_state(scan, coefficients):
    units = np.asarray(coefficients, dtype=float)
    if units.shape != (8,) or not np.isfinite(units).all() or np.any(np.abs(units) > 1.):
        raise ValueError("Expected eight bounded fixed-zero mixture receiver coordinates")
    state = discovery.zero_state(scan)
    state["beta"][:4] = units[:4] * (PERIOD / 2)
    state["beta"][4:] = units[4:] * 750.
    return state


def cold_start(prepared, region, bound):
    cpu, wall = process_time(), perf_counter()
    proposal = propose(prepared, region, arms=("c0",))
    if proposal["status"] != "complete":
        raise ValueError(f"Mixture start unavailable: {proposal['status']}")
    arm = proposal["arms"]["c0"]
    proposed = np.asarray(arm["east_north_km"], dtype=float)
    mixture_clocks = elapsed(cpu, wall)

    cpu, wall = process_time(), perf_counter()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    state = receiver_state(scan, arm["receiver_prior_units"])
    seed, hypotheses = discovery.explore(scan, state, proposed, "receiver_smooth", compact_update=False)
    aliases = AnchoredFamilies(scan, seed, "receiver_smooth", False, proposed).alias
    node = dict(seed=seed, aliases=aliases)
    rebuilt_clocks = elapsed(cpu, wall)

    cpu, wall = process_time(), perf_counter()
    labels = sorted({row["candidate_index"] for row in seed["rows"]})
    reference = np.clip(seed["state"]["phases"][labels], -15., 15.)
    model = position.NormalPosition(scan, node, scan.radio_sigma_hz, False, reference=reference)
    fit = position.fit(model, proposed, iterations=48)
    point = np.asarray(fit["parameters"])
    if not np.isfinite(fit["score"]) or not np.isfinite(point).all():
        raise ValueError("No finite full-curve fit from the mixture start")
    posterior = np.clip(model.state(point)["phases"][labels], -15., 15.)
    clocks = elapsed(cpu, wall)
    return node, point, dict(zip(labels, posterior, strict=True)), dict(
        scores=[float(fit["score"])], branch=1, east_north_km=point, latlon=region.latlon(point),
        catalogue=len(scan.norads), nomination_tracks=len(seed["rows"]), nominated_families=len(labels),
        nomination_hypotheses=hypotheses["candidate_hypotheses"],
        proposed_east_north_km=proposed, proposed_latlon=arm["latlon"], proposed_score=arm["score"],
        proposed_nodes=proposal["node_count"], proposed_sample_rms_hz=arm["matched_sample_rms_hz"],
        proposed_supported_tracks=sum(row["retained"] for row in arm["tracks"]),
        proposed_owner_points=arm["sampled_owner_points"], refined_rms_hz=fit["residual_rms_hz"],
        mixture_clocks=mixture_clocks, rebuild_clocks=rebuilt_clocks, one_refit_clocks=clocks,
    )
