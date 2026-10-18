"""Controlled same-scan diagnostics of S01's two purple restart endpoints.

No evaluation coordinate enters any fitting or branch choice. Cross-start
experiments use the independently saved endpoints and labels, not GPS. The
active radial campaign and its frozen sources/results remain unchanged.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_radial_restarts import run_modern_recipe
from map_dsx01_clean_region import factory, finite_gradient, loss
from run_dsx01_clean_region import load_scan

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/2026_10_18_dsx01_radial_restarts/DSX01-S01"
OUTPUT = ROOT / "reports/2026_10_18_dsx01_purple_basin"
ARMS = ("c0", "fitted_c")
STARTS = (0, 6, 9)
FAMILY = ("S01-RX2-CH1-T002", "S01-RX2-CH2-T001", "S01-RX2-CH4-T000")


def labels(node):
    return {
        row["component"]: (int(row["candidate_index"]), int(row["candidate_norad"]), int(alias))
        for row, alias in zip(node["seed"]["rows"], node["aliases"], strict=True)
    }


def label_differences(left, right):
    a, b = labels(left), labels(right)
    if a.keys() != b.keys():
        raise ValueError("controlled comparisons must preserve the same fragment population")
    return [dict(component=k, left=a[k], right=b[k]) for k in a if a[k] != b[k]]


def family_swap(node, donor, components=FAMILY):
    result = copy.deepcopy(node)
    replacements = {r["component"]: r for r in donor["seed"]["rows"]}
    found = set()
    for row in result["seed"]["rows"]:
        if row["component"] in components:
            for key in ("candidate_index", "candidate_norad"):
                row[key] = replacements[row["component"]][key]
            found.add(row["component"])
    if found != set(components):
        raise ValueError("all requested family components must be present")
    # Alias choices remain those of the recipient; in this case all agree.
    return result


def problem(scan, sigma, node, arm, common_reference=None):
    reference = None
    if common_reference is not None:
        indexes = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
        reference = np.asarray(common_reference)[indexes]
    return factory(scan, node, sigma, "normal", arm == "fitted_c", reference=reference)


def finite_hessian(function, point, step=0.05):
    point, eye = np.asarray(point, float), np.eye(2) * step
    center = function(point)
    hessian = np.diag([
        (function(point + d) + function(point - d) - 2 * center) / step**2 for d in eye
    ])
    hessian[0, 1] = hessian[1, 0] = (
        function(point + eye[0] + eye[1]) - function(point + eye[0] - eye[1])
        - function(point - eye[0] + eye[1]) + function(point - eye[0] - eye[1])
    ) / (4 * step**2)
    return hessian


def endpoint_diagnostic(p, point):
    calculated = p.calculate(point)
    score = loss(p, point)
    def function(x):
        return loss(p, x)
    gradient = finite_gradient(function, point)
    hessian = finite_hessian(function, point)
    precise = hierarchical_bound(
        p.values - p.q * calculated["intercept"], calculated["features"],
        p.point_noise, p.noise_groups, iterations=2048,
    )
    precise_score = float(precise["residual"] @ precise["residual"])
    precise_score += p.diagonal_logvolume
    precise_score += float(np.sum((np.maximum(0, -calculated["elevation"]) / 2) ** 2))
    return dict(
        point=point, score=score, gradient_loss_per_km=gradient,
        gradient_norm=float(np.linalg.norm(gradient)), hessian_loss_per_km2=hessian,
        hessian_eigenvalues=np.linalg.eigvalsh(hessian),
        precision_iterations=calculated["precision_iterations"],
        precision_log_change=calculated["final_log_precision_change"],
        precision_2048_score=precise_score, precision_score_change=precise_score - score,
    )


def run(*, maps=False, extensions=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = {i: SOURCE / "normal" / f"start_{i:02d}" / "result.json" for i in range(13)}
    records = {i: json.loads(p.read_text()) for i, p in paths.items()}
    scan, sigma = load_scan("DSX01-S01")
    source_receipts = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()
    }
    write(OUTPUT / "protocol.json", dict(
        case=scan.case, source_bindings=source_receipts,
        observation_count=sum(len(scan.tracks[i]["times"]) for i in scan.curved),
        candidate_count=len(scan.norads), input_audit=scan.inference_input_audit,
        no_GPS_in_fitting_or_branch_selection=True,
        matched_c0_fitted_c_observations_labels_aliases_priors_starts_budgets=True,
        original_campaign_unchanged=True,
        cross_start_interventions_are_diagnostics_not_a_production_satellite_whitelist=True,
        longer_fit_iterations=96, finite_derivative_step_km=0.05,
    ))
    comparison, diagnostics, crossfits, swaps = [], [], [], []
    for i, record in records.items():
        for arm in ARMS:
            value = record["arms"][arm]
            comparison.append(dict(
                start_id=i, arm=arm, start=record["start_east_north_km"],
                endpoint=value["endpoint_east_north_km"], score=value["fit"]["score"],
                stop=value["fit"]["stopped"], associated_points=value["associated_points"],
                associated_tracks=value["associated_tracks"],
                changed_labels_vs_S00=label_differences(
                    records[0]["final_node"], record["final_node"]
                ),
            ))
    write(OUTPUT / "all_start_comparison.json", comparison)
    for i in STARTS:
        node = records[i]["final_node"]
        for arm in ARMS:
            p = problem(scan, sigma, node, arm)
            point = np.array(records[i]["arms"][arm]["endpoint_east_north_km"])
            diagnostics.append(dict(
                start_id=i, arm=arm, stored_score=records[i]["arms"][arm]["fit"]["score"],
                **endpoint_diagnostic(p, point),
            ))
            for j in STARTS:
                start = np.array(records[j]["arms"]["c0"]["endpoint_east_north_km"])
                fit = bounded_gauss_newton(p.residual, start, p.lower, p.upper, iterations=96)
                crossfits.append(dict(
                    branch_from_start=i, initialization_from_start=j, arm=arm,
                    initial_point=start, initial_score=loss(p, start), fit=fit,
                    diagnostics=endpoint_diagnostic(p, fit["parameters"]),
                ))
                print("crossfit", i, j, arm, fit["score"], fit["parameters"], flush=True)
        write(OUTPUT / "endpoint_diagnostics.json", diagnostics)
        write(OUTPUT / "cross_branch_fits.json", crossfits)
    common_reference = np.zeros(len(scan.norads))
    for i in STARTS:
        for swapped in (False, True):
            if i == 0 and swapped:
                continue
            node = (
                family_swap(records[i]["final_node"], records[0]["final_node"])
                if swapped else records[i]["final_node"]
            )
            for arm in ARMS:
                p = problem(scan, sigma, node, arm, common_reference=common_reference)
                for j in (0, 6):
                    start = np.array(records[j]["arms"]["c0"]["endpoint_east_north_km"])
                    fit = bounded_gauss_newton(p.residual, start, p.lower, p.upper, iterations=96)
                    swaps.append(dict(
                        recipient_branch=i, family_swapped_from_S00=swapped,
                        all_phase_expansion_references_zero=True, initialization_from_start=j,
                        arm=arm, fit=fit,
                        changed_labels=label_differences(records[i]["final_node"], node),
                    ))
                    print(
                        "controlled", i, swapped, j, arm, fit["score"], fit["parameters"],
                        flush=True,
                    )
        write(OUTPUT / "controlled_family_swap.json", swaps)
    if maps:
        map_path = OUTPUT / "conditional_surfaces.json"
        if not map_path.exists():
            east, north = np.arange(-1, 10.01, 1), np.arange(-10, 4.01, 1)
            points = np.array([(e, n) for n in north for e in east])
            surfaces = []
            for i in STARTS:
                for arm in ARMS:
                    p = problem(scan, sigma, records[i]["final_node"], arm)
                    values = [loss(p, x) for x in points]
                    surfaces.append(dict(branch_from_start=i, arm=arm, loss=values))
                    print("mapped", i, arm, flush=True)
            write(map_path, dict(east=east, north=north, points=points, surfaces=surfaces))
    if extensions:
        for i in STARTS:
            out = OUTPUT / f"eight_round_extension_S{i:02d}.json"
            if out.exists():
                continue
            path = SOURCE / "discovery" / f"start_{i:02d}" / "discovery.json"
            discovery = json.loads(path.read_text())
            extended = run_modern_recipe(scan, sigma, discovery, "normal", rounds=8)
            write(out, extended)
    print("diagnostics saved", OUTPUT, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps", action="store_true")
    parser.add_argument("--extensions", action="store_true")
    args = parser.parse_args()
    run(maps=args.maps, extensions=args.extensions)
