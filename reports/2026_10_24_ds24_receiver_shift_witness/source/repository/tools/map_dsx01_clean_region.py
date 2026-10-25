"""Map current graph-based localization hypotheses from fresh regional discovery.

Inference has no GPS input. Each recipe examines all 25 fresh node assignments,
then profiles continuous nuisance coefficients over a 10-km regional disk.
Maps condition on that recipe's selected assignment; this is explicitly not
an exhaustive marginal over every satellite/alias combination at every pixel.
"""

import argparse
import hashlib
import json
import time
from math import lgamma

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_causal_correlation import VARIANTS as CORRELATIONS
from dsx01_causal_correlation import CausalCorrelation
from dsx01_causal_forecast import VARIANTS as FORECASTS
from dsx01_causal_forecast import CausalForecast
from dsx01_frame_joint import VARIANTS as FRAMES
from dsx01_frame_joint import FrameJoint
from dsx01_inference_audit import InferenceReadGuard, disk_grid
from dsx01_joint_rf_time import VARIANTS as RF_TIME
from dsx01_joint_rf_time import JointRFTime
from dsx01_native_drift import VARIANTS as NATIVE
from dsx01_native_drift import NativeDrift
from dsx01_prior_scale_controls import VARIANTS as SCALES
from dsx01_prior_scale_controls import PriorScaleControls
from dsx01_quality_rate_controls import VARIANTS as QUALITY
from dsx01_quality_rate_controls import QualityRateControls
from dsx01_satellite_prior_controls import VARIANTS as PRIORS
from dsx01_satellite_prior_controls import SatellitePriorControls
from dsx01_smooth_background import background_logprob
from prototype_dsx01_continuous_position import CENTER, latlon
from run_dsx01_clean_region import OUTPUT, load_scan, reference_state, standard_problem

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

SPECS = {
    **{v: (SatellitePriorControls, v) for v in PRIORS},
    **{v: (QualityRateControls, v) for v in QUALITY},
    **{v: (PriorScaleControls, v) for v in SCALES},
    **{v: (NativeDrift, v) for v in NATIVE},
    **{v: (JointRFTime, v) for v in RF_TIME},
    **{v: (CausalCorrelation, v) for v in CORRELATIONS},
    **{v: (CausalForecast, v) for v in FORECASTS},
    **{f"frame_{v}": (FrameJoint, v) for v in FRAMES},
}


def refresh_quality(scan, p, point):
    """Recompute the original quality heuristic on this fresh c0 hypothesis."""
    result = p.calculate(np.array(point))
    u = result["features"] / p.point_noise[:, None]
    weighted = u * np.sqrt(result["noise_precision"][p.noise_groups, None])
    root = np.linalg.cholesky(np.eye(u.shape[1]) + weighted.T @ weighted)
    expected = (result["conditional_residual_hz"] / p.point_noise) ** 2
    expected += np.sum(np.linalg.solve(root, u.T) ** 2, axis=0)
    rows = []
    for i, sl in zip(p.members, p.slices, strict=True):
        n = sl.stop - sl.start
        alpha, beta = (4 + n) / 2, (4 + expected[sl].sum()) / 2
        signal = lgamma(alpha) - lgamma(2) + 2 * np.log(2) - alpha * np.log(beta)
        signal -= n / 2 * np.log(2 * np.pi) + np.log(p.point_noise[sl]).sum()
        background = background_logprob(p.values[sl], p.flat_times[sl], p.point_noise[sl])
        log_odds = np.log(0.95 / 0.05) + signal - background["log_probability"]
        rows.append(
            dict(
                component=scan.tracks[i]["key"],
                conditional_signal_probability=float(np.exp(-np.logaddexp(0, -log_odds))),
            )
        )
    scan.fixed_conditional_quality = rows
    scan.fixed_conditional_quality_sha256 = hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode()
    ).hexdigest()


def factory(scan, node, sigma, name, fitted_c, reference=None, aliases=None):
    cls, variant = SPECS[name]
    seed = dict(node["seed"], state=reference_state(node["seed"]["state"]))
    return cls(
        scan,
        seed,
        fitted_c,
        variant=variant,
        sigma=sigma,
        aliases=node["aliases"] if aliases is None else aliases,
        reference=reference,
    )


def loss(p, x):
    r = p.residual(np.array(x))
    return float(r @ r)


def finite_gradient(function, xy, step=0.05):
    xy = np.asarray(xy, float)
    return np.array(
        [(function(xy + step * v) - function(xy - step * v)) / (2 * step) for v in np.eye(2)]
    )


def run(case, names=None, spacing=2.0):
    directory = OUTPUT / case
    guard = InferenceReadGuard(OUTPUT)
    guard.install()
    atlas = json.loads((directory / "atlas.json").read_text())
    scan, sigma = load_scan(case)
    history_path = directory / "causal_history.json"
    if history_path.exists():
        scan.strict_causal_history = json.loads(history_path.read_text())
    elif any(
        n in FORECASTS or n in ("frame_trend_300", "frame_history_300") for n in names or SPECS
    ):
        raise ValueError("export complete past-only regional histories before forecasting")
    axis, points = disk_grid(step_km=spacing)
    write(
        directory / "surface_protocol.json",
        dict(
            methods=list(SPECS),
            center=CENTER,
            radius_km=10,
            spacing_km=spacing,
            initialization="fresh all-candidate discovery, no saved satellite labels or site",
            search_box_width_km=25,
            regional_assignment_nodes=25,
            method_selection="c0 objective, never GPS",
            matched_c0_fitted_c_labels_aliases_priors_starts_budgets=True,
            surface="conditional assignment with nuisances integrated at each position",
            gradient=(
                "central differences of actual conditional objective; coarse map arrows descriptive"
            ),
            no_joint_assignment_global_optimality_claim=True,
            quality_weights="recomputed from this scan's fresh c0 hypothesis, no old quality file",
            phase_rounds=2,
            starts_per_round=3,
            iterations_per_start=24,
            observations="original curved points; GLRT300 CFO; same-scan radio-only noise",
        ),
    )
    for name in names or SPECS:
        path = directory / "surfaces" / name / "result.json"
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        mark = time.monotonic()
        if name.startswith("quality"):
            best = min(atlas["nodes"], key=lambda r: r["score"])
            refresh_quality(
                scan,
                standard_problem(scan, best["seed"], sigma, aliases=best["aliases"]),
                best["point"],
            )
        nodes = []
        for node in atlas["nodes"]:
            p = factory(scan, node, sigma, name, False)
            nodes.append(dict(node=node, score=loss(p, node["point"])))
        selected = min(nodes, key=lambda r: r["score"])["node"]
        # Common assignment and alias branch for both c arms, selected only by c0.
        reference = None
        rounds = []
        anchor = np.array(selected["point"])
        for _iteration in range(2):
            problems = {
                a: factory(scan, selected, sigma, name, a == "fitted_c", reference=reference)
                for a in ("c0", "fitted_c")
            }
            grid = [
                dict(point=n["point"], score=loss(problems["c0"], n["point"]))
                for n in atlas["nodes"]
            ]
            grid.append(dict(point=anchor, score=loss(problems["c0"], anchor)))
            starts = sorted(grid, key=lambda r: r["score"])[:3]
            if not any(np.array_equal(s["point"], anchor) for s in starts):
                starts[-1] = dict(point=anchor, score=loss(problems["c0"], anchor))
            fits = {}
            for arm, p in problems.items():
                attempts = [
                    bounded_gauss_newton(
                        p.residual, np.array(s["point"]), p.lower, p.upper, iterations=24
                    )
                    for s in starts
                ]
                best = min(attempts, key=lambda r: r["score"])
                fits[arm] = dict(
                    best,
                    attempts=attempts,
                    state=p.state(best["parameters"]),
                    reference=p.reference,
                )
            rounds.append(dict(fits=fits, starts=starts))
            anchor = np.array(fits["c0"]["parameters"])
            reference = np.clip(
                np.array(fits["c0"]["state"]["phases"])[problems["c0"].labels], -15, 15
            )
        arms = {}
        for arm, p in problems.items():
            fit = fits[arm]
            endpoint = np.array(fit["parameters"])
            values = [loss(p, point) for point in points]
            starts = [[0.0, 0.0], *[points[i] for i in np.argsort(values)[:2]]]
            probes = [
                bounded_gauss_newton(p.residual, np.array(s), p.lower, p.upper, iterations=24)
                for s in starts
            ]
            result = p.calculate(endpoint)
            arms[arm] = dict(
                fit=fit,
                map_points=points,
                loss=values,
                multistart_probes=probes,
                endpoint_latlon=latlon(endpoint),
                gradient_at_center=finite_gradient(lambda x, p=p: loss(p, x), [0, 0]),
                gradient_at_endpoint=finite_gradient(lambda x, p=p: loss(p, x), endpoint),
                residual_rms_hz=float(np.sqrt(np.mean(result["conditional_residual_hz"] ** 2))),
                phase_reference_s=p.reference,
                variational_converged=result.get("converged"),
            )
        write(
            path,
            dict(
                case=case,
                method=name,
                arms=arms,
                axis=axis,
                rounds=rounds,
                selected_assignment_node=selected,
                node_assignment_losses=[
                    dict(point=r["node"]["point"], score=r["score"]) for r in nodes
                ],
                seconds=time.monotonic() - mark,
                conditional_assignment=True,
                GPS_or_following_TLE_used=False,
                actual_report_inputs_read=sorted(guard.read_paths),
            ),
        )
        print(
            case,
            name,
            {a: r["fit"]["parameters"].tolist() for a, r in arms.items()},
            round(time.monotonic() - mark, 1),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--methods", nargs="+", choices=SPECS)
    parser.add_argument("--spacing", type=float, default=2.0)
    args = parser.parse_args()
    run(args.case, args.methods, args.spacing)
