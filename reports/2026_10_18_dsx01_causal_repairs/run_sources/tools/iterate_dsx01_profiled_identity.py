"""Explore candidate-specific phase hypotheses before shared-family updates."""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import fit_once, nomination_rows
from prototype_dsx01_continuous_position import CENTER, latlon, native_point, numpy_state

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, proposal_phases

OUTPUT = ROOT / "reports/2026_10_18_dsx01_profiled_identity"
SOURCE = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"


def select_endpoints(case, method, records):
    inherited = json.loads((SOURCE / case / "endpoints.json").read_text())
    output = {}
    for arm in ("c0", "fitted_c"):
        choices = [dict(inherited[f"{arm}/{method}"], selected_from="inherited")]
        choices.extend(
            dict(r["fits"][arm], selected_from=f"round{r['iteration']}") for r in records
        )
        output[arm] = min(choices, key=lambda r: r["score"])
    write(OUTPUT / case / method / "endpoints.json", output)
    write(
        OUTPUT / case / method / "selection_protocol.json",
        dict(
            incumbent_always_remains_a_candidate=True,
            no_reference_position_read=True,
            same_frequency_prior_plus_complexity_score=True,
            source_sha256=hashlib.sha256(
                (SOURCE / case / "endpoints.json").read_bytes()
            ).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    return output


def coherent_phase(phases, sigma, weight):
    """One weighted phase mode; incompatible component hypotheses stay separate."""
    p, s, w = (np.asarray(a, float) for a in (phases, sigma, weight))
    if p.ndim != 1 or s.shape != p.shape or w.shape != p.shape or not len(p):
        raise ValueError("matching nonempty phase hypotheses required")
    if not np.isfinite(p).all() or np.any(s <= 0) or np.any(w < 0) or not w.sum():
        raise ValueError("finite phases, positive scales and nonzero weights required")
    compatible = abs(p[:, None] - p[None, :]) <= 3 * np.sqrt(s[:, None] ** 2 + s[None, :] ** 2)
    support = compatible @ w
    chosen = int(np.argmax(support))
    mask = compatible[chosen]
    order = np.argsort(p[mask])
    values = p[mask][order]
    weights = w[mask][order]
    phase = float(values[np.searchsorted(np.cumsum(weights), weights.sum() / 2)])
    return phase, float(support[chosen]), int(mask.sum())


def explore(scan, state, anchor, method, topk=4, maximum=64, *, compact_update=True):
    base = phase_linear_frequency(scan.geometry, *latlon(anchor))
    groups = scan.groups
    if method == "receiver_smooth":
        groups = []
        for i in scan.curved:
            t = scan.tracks[i]
            adjusted = dict(
                t,
                values=t["values"]
                - t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1],
            )
            groups.append((t["key"], [adjusted]))
    stats = matching.statistics(
        groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    # Eligibility is frozen from the original raw observations, even when a
    # receiver smooth term was subtracted for proposal generation.
    stats["active"][:] = True
    stats["fragment_active"][:] = True
    phases, scores = proposal_phases(
        stats, state["beta"], scan.sigma, np.full(len(scan.norads), 15.0), return_components=True
    )
    n = stats["n"][:, None]
    information = np.maximum(
        0, stats["hh"] + n * stats["hm"] ** 2 - (n * stats["hm"]) ** 2 / (n + 150**2 / 1000**2)
    )
    phase_sigma = 150 / np.sqrt(information + 150**2 / scan.sigma[None, :] ** 2)
    best = np.argsort(scores, axis=1)[:, :topk]
    weights = np.exp(
        -0.5
        * np.maximum(0, scores - scores.min(axis=1)[:, None])
        * np.minimum(stats["count"], 50)[:, None]
        / 150**2
    )
    hypotheses = {}
    for j in np.unique(best):
        rows = np.flatnonzero(
            np.any(best == j, axis=1) & (scores[:, j] < 1000**2) & (weights[:, j] > 0.001)
        )
        if not len(rows):
            continue
        phase, support, count = coherent_phase(
            phases[rows, j], phase_sigma[rows, j], weights[rows, j]
        )
        hypotheses[int(j)] = dict(phase_s=phase, support=support, coherent_curves=count)
    chosen = sorted(hypotheses, key=lambda j: -hypotheses[j]["support"])[:maximum]
    proposal = numpy_state(state)
    for j in chosen:
        proposal["phases"][j] = hypotheses[j]["phase_s"]
    point = native_point(scan, anchor)
    # Exploratory component-specific phases are discarded after this step.
    # The update returns one shared phase per selected satellite and no phase
    # fields for unsupported candidate hypotheses.
    _, _, nominations, predicted = scan.association(proposal, base, point, method)
    if compact_update:
        compact, _ = scan.update(proposal, nominations, predicted, point, method)
    else:
        # A caller with different radio priors must use its own joint fitter.
        # The legacy update has original +/-1 Hz/s bounds and would overwrite
        # a wider calibrated state. Proposals already have one phase per sat.
        compact = proposal
    _, rows, nominations, _ = scan.association(compact, base, point, method)
    return dict(state=compact, rows=nomination_rows(scan, rows, nominations)), dict(
        candidate_hypotheses=len(hypotheses),
        explored_candidates=len(chosen),
        hypotheses={str(int(scan.norads[j])): hypotheses[j] for j in chosen},
    )


def run(case, method, rounds=3):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    source = SOURCE / case / "endpoints.json"
    old = json.loads(source.read_text())[f"c0/{method}"]
    anchor, state = old["east_north_km"], numpy_state(old["state"])
    output = directory / "iterations.json"
    records = json.loads(output.read_text()) if output.exists() else []
    if records:
        last = records[-1]["fits"]["c0"]
        anchor, state = last["east_north_km"], numpy_state(last["state"])
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_or_oracle_parameters=True,
            inherited_position_is_a_completed_blind_25km_grid_estimate=True,
            center=CENTER,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            top_candidate_phases_per_curve=4,
            maximum_exploratory_satellites=64,
            phase_bound_s=15,
            phase_cluster_width_sigma=3,
            all_proposals_raw_curved_only=True,
            component_phase_hypotheses_are_not_final_parameters=True,
            final_one_phase_per_satellite=True,
            common_c0_labels_and_starts_for_both_c_arms=True,
            rounds=rounds,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for iteration in range(len(records), rounds):
        seed, diagnostics = explore(scan, state, anchor, method)
        fits = fit_once(scan, seed, method, anchor)
        records.append(dict(iteration=iteration, proposal=diagnostics, fits=fits))
        write(output, records)
        anchor, state = fits["c0"]["east_north_km"], fits["c0"]["state"]
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    iteration=iteration,
                    hypotheses=diagnostics["explored_candidates"],
                    positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                )
            ),
            flush=True,
        )
    select_endpoints(case, method, records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--method", choices=METHODS, default="shared_phase")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    run(args.case, args.method, args.rounds)
