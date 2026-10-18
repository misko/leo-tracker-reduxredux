"""Independent, same-scan satellite discovery and paired regional restarts.

Each discovery begins at the requested regional coordinate with zero radio,
phase and receiver-smooth coefficients. No assignment atlas or fitted site is
read here. Archived radio measurements and the audited causal candidate bank
remain the common upstream observations; they are not reacquired per start.
"""

import itertools
import time

import analyze_dsx01_fixed_site as matching
import numpy as np
from compare_dsx01_frame_joint import actual_metrics
from dsx01_native_drift import NativeDriftEvaluation
from evaluate_shared_satellite_phase import improve
from iterate_dsx01_position_nominations import AnchoredFamilies, nomination_rows
from iterate_dsx01_profiled_identity import explore
from map_dsx01_clean_region import factory, refresh_quality
from prototype_dsx01_calibration_modes import project_radio_state
from prototype_dsx01_continuous_position import latlon, native_point
from run_dsx01_clean_region import reference_state, score_at, standard_problem, zero_state

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, proposal_phases


def validated_start(point):
    """Accept a finite EN coordinate inside the declared regional square."""
    xy = np.asarray(point, dtype=float)
    if xy.shape != (2,) or not np.isfinite(xy).all() or np.any(abs(xy) > 12.5):
        raise ValueError("a finite two-dimensional start inside the 25-km box is required")
    return xy.copy()


def aliases_at_start(scan, seed, point):
    """Compute alias integers at the actual blind anchor, never at town zero."""
    p = AnchoredFamilies(scan, seed, "receiver_smooth", False, validated_start(point))
    return list(p.alias)


def discovery_statistics(scan, point):
    base = phase_linear_frequency(scan.geometry, *latlon(point))
    stats = matching.statistics(
        scan.groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    return base, augment_phase_statistics(stats, scan.times, base[0], base[2])


def discover_at_start(scan, sigma, point, budget=8):
    """Return the best c0 hypothesis discovered freshly at this start only.

    Every raw-curved fragment is retained in the inference population. The
    all-bank proposal stage is finite and heuristic; it is not an exhaustive
    enumeration of joint satellite identities.
    """
    point = validated_start(point)
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("positive integer discovery budget required")
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("positive finite radio-only noise scale required")
    mark = time.monotonic()
    base, stats = discovery_statistics(scan, point)
    bounds = np.full(len(scan.norads), 15.0)
    initial = np.zeros(8)
    phases, _ = proposal_phases(stats, initial, scan.sigma, bounds, return_components=True)
    phi = phases[stats["ci"]]
    adjusted = dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phi,
        xz=stats["xz"] - stats["xh"] * phi,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phi + stats["hh"] * phi**2),
    )
    shape = np.maximum(
        0, adjusted["rss"] - adjusted["xz"] ** 2 / np.maximum(stats["xx"][:, None], 1e-12)
    )
    adjusted["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, stats["starts"], axis=0) / stats["count"][:, None]
    )
    proposals = itertools.islice(matching.seed_calibrations(adjusted, initial, budget), budget)
    candidates = []
    for number, beta in enumerate(proposals):
        state = zero_state(scan)
        if number:
            phase = proposal_phases(stats, beta, scan.sigma, bounds)
            fitted = improve(
                stats, beta, phase, scan.sigma, bounds, drift_sigma_hz_s=10, drift_bound_hz_s=30
            )
            state.update(beta=fitted[1], phases=fitted[2])
        state = project_radio_state(state)
        _, rows, nominees, _ = scan.association(
            state, base, native_point(scan, point), "shared_phase"
        )
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        details = []
        for _ in range(2):
            aliases = aliases_at_start(scan, seed, point)
            p = standard_problem(scan, seed, sigma, aliases=aliases)
            state = p.state(point)
            seed, detail = explore(
                scan, reference_state(state), point, "receiver_smooth", compact_update=False
            )
            details.append(
                {k: detail[k] for k in ("candidate_hypotheses", "explored_candidates")}
            )
        aliases = aliases_at_start(scan, seed, point)
        p = standard_problem(scan, seed, sigma, aliases=aliases)
        candidate = dict(
            hypothesis=number,
            score=score_at(p, point),
            seed=dict(rows=p.rows, state=p.state(point)),
            aliases=list(p.alias),
            proposal_rounds=details,
        )
        candidates.append(candidate)
        print(
            scan.case, "independent discovery", point.tolist(), number,
            candidate["score"], flush=True,
        )
    if not candidates:
        raise ValueError("all-candidate radio proposal stage returned no hypotheses")
    best = min(candidates, key=lambda row: row["score"])
    return dict(
        best,
        case=scan.case,
        start_east_north_km=point,
        discovery_candidates=[
            {k: row[k] for k in ("hypothesis", "score", "proposal_rounds")}
            for row in candidates
        ],
        discovery_provenance=dict(
            zero_initial_radio_phase_and_smooth=True,
            saved_atlas_labels_calibration_or_site_read=False,
            candidate_count=len(scan.norads),
            proposal_budget=budget,
            proposal_hypotheses_run=len(candidates),
            sigma_hz=float(sigma),
            alias_anchor_east_north_km=point,
            GPS_or_following_TLE_used=False,
            seconds=time.monotonic() - mark,
        ),
    )


def assignment_changes(old, new):
    """Count label/alias changes using component identity, not row order."""
    def identities(node):
        return {
            row["component"]: (int(row["candidate_index"]), int(alias))
            for row, alias in zip(node["seed"]["rows"], node["aliases"], strict=True)
        }

    left, right = identities(old), identities(new)
    keys = left.keys() | right.keys()
    return dict(
        changed_components=sum(left.get(k) != right.get(k) for k in keys),
        changed_satellite_labels=sum(
            left.get(k, (None, None))[0] != right.get(k, (None, None))[0] for k in keys
        ),
        changed_aliases=sum(
            left.get(k, (None, None))[1] != right.get(k, (None, None))[1] for k in keys
        ),
    )


def proposal_state(problem, parameters):
    """Project native-Hz radio means only for standard all-bank proposals.

    Native-band and mixed designs have a different coefficient width and RF
    interpretation from the proposal engine. Their actual observation-space
    nonlinear mean is projected onto the common q-scaled RX basis. The model
    used for fitting/scoring and its persisted state retain the native design.
    """
    state = reference_state(problem.state(parameters))
    if not hasattr(problem, "nonlinear_radio_mean"):
        return state
    scan = problem.scan
    width = scan.rx_basis[0].shape[1]
    design = np.zeros((len(problem.flat_times), 2 * width))
    for i, sl in zip(problem.members, problem.slices, strict=True):
        receiver = scan.tracks[i]["receiver"] - 1
        design[sl, receiver * width : (receiver + 1) * width] = (
            problem.q[sl, None] * scan.rx_basis[i]
        )
    mean = np.asarray(problem.nonlinear_radio_mean(parameters))
    coefficient = np.linalg.lstsq(design, mean, rcond=None)[0]
    state["smooth"] = coefficient.reshape(2, width)
    return state


class NativeMetricProblem:
    """Expose native-correct predictions through the common residual gate API."""

    def __init__(self, problem):
        self.problem = problem
        self.evaluation = NativeDriftEvaluation(problem)

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def state(self, x):
        return self.evaluation.association_state(x)

    def conditional_frequency(self, x):
        return self.evaluation.predicted(x)


def metric_problem(problem):
    return NativeMetricProblem(problem) if hasattr(problem, "nonlinear_radio_mean") else problem


def refresh_modern_assignment(scan, sigma, name, node, state, point):
    """Compare incumbent and all-bank refreshed identities using this recipe."""
    state = reference_state(state)
    incumbent = dict(seed=dict(rows=node["seed"]["rows"], state=state), aliases=node["aliases"])
    seed, detail = explore(scan, state, point, "receiver_smooth", compact_update=False)
    proposed = dict(seed=seed, aliases=aliases_at_start(scan, seed, point))
    choices = []
    for origin, candidate in (("incumbent", incumbent), ("all_candidate_refresh", proposed)):
        p = factory(scan, candidate, sigma, name, False)
        choices.append(dict(origin=origin, node=candidate, score=score_at(p, point)))
    selected = min(choices, key=lambda row: row["score"])
    return selected["node"], dict(
        selected=selected["origin"],
        candidate_scores=[dict(origin=r["origin"], score=r["score"]) for r in choices],
        **{k: detail[k] for k in ("candidate_hypotheses", "explored_candidates")},
        **assignment_changes(incumbent, selected["node"]),
    )


def run_modern_recipe(scan, sigma, discovery, name, iterations=24, rounds=2):
    """Run a recipe independently from one start, with matched c arms.

    There is exactly one position start per round. Only c0 proposes/selects
    satellite assignments and the next round's common anchor. This prevents
    fitted-c from receiving a different candidate search or GPS selection.
    """
    if not isinstance(rounds, int) or rounds < 1:
        raise ValueError("positive integer fitting rounds required")
    if not isinstance(iterations, int) or iterations < 1 or iterations > 24:
        raise ValueError("iteration budget must be between 1 and 24")
    mark = time.monotonic()
    anchor = validated_start(discovery["start_east_north_km"])
    node = dict(seed=discovery["seed"], aliases=list(discovery["aliases"]))
    if name.startswith("quality"):
        refresh_quality(
            scan, standard_problem(scan, node["seed"], sigma, aliases=node["aliases"]), anchor
        )
    records = []
    for number in range(rounds):
        problems = {
            arm: factory(scan, node, sigma, name, arm == "fitted_c")
            for arm in ("c0", "fitted_c")
        }
        fits = {}
        for arm, p in problems.items():
            initial = p.initial.copy()
            initial[:2] = anchor
            fit = bounded_gauss_newton(
                p.residual, initial, p.lower, p.upper, iterations=iterations
            )
            fits[arm] = dict(fit, state=p.state(fit["parameters"]), aliases=list(p.alias))
        record = dict(
            round=number,
            start_east_north_km=anchor.copy(),
            fits=fits,
            assignment_rows=node["seed"]["rows"],
            aliases=node["aliases"],
        )
        if number + 1 < rounds:
            anchor = np.asarray(fits["c0"]["parameters"][:2])
            node, detail = refresh_modern_assignment(
                scan, sigma, name, node,
                proposal_state(problems["c0"], fits["c0"]["parameters"]), anchor,
            )
            record["reassociation"] = detail
        records.append(record)
        print(scan.case, name, "independent round", number, {
            arm: fit["parameters"][:2].tolist() for arm, fit in fits.items()
        }, flush=True)
    arms = {}
    for arm, p in problems.items():
        fit = fits[arm]
        endpoint = np.asarray(fit["parameters"][:2])
        calculated = p.calculate(fit["parameters"])
        replay_fit = dict(
            rows=p.rows,
            state=fit["state"],
            east_north_km=endpoint,
            aliases=p.alias,
            fits=[fit],
        )
        metrics = actual_metrics(metric_problem(p), replay_fit, arm, fit["parameters"])
        arms[arm] = dict(
            fit=fit,
            endpoint_east_north_km=endpoint,
            endpoint_latlon=latlon(endpoint),
            state=fit["state"],
            aliases=list(p.alias),
            rows=p.rows,
            members=list(p.members),
            labels=list(p.labels),
            phase_reference_s=p.reference,
            residual_rms_hz=float(np.sqrt(np.mean(calculated["conditional_residual_hz"] ** 2))),
            associated_points=metrics["accepted_points"],
            associated_fragments=metrics["accepted_tracks"],
            associated_tracks=metrics["accepted_tracks"],
            assignment_labels={row["component"]: row["candidate_norad"] for row in p.rows},
            association_metrics=metrics,
            inferred_points=len(p.flat_times),
            inferred_fragments=len(p.members),
            variational_converged=calculated.get("converged"),
        )
    return dict(
        case=scan.case,
        method=name,
        start_east_north_km=discovery["start_east_north_km"],
        arms=arms,
        rounds=records,
        final_node=node,
        final_reference=None,
        final_anchor=anchor,
        provenance=dict(
            discovery=discovery["discovery_provenance"],
            same_start_discovery_hypothesis=discovery["hypothesis"],
            matched_c0_fitted_c_labels_aliases_starts_and_budgets=True,
            reassociation_between_rounds=True,
            assignment_selection="recipe c0 score; incumbent retained as candidate",
            iterations_per_round=iterations,
            fitting_rounds=rounds,
            regional_search_box_width_km=25,
            additional_regional_multistarts=False,
            GPS_or_following_TLE_used=False,
            seconds=time.monotonic() - mark,
        ),
    )
