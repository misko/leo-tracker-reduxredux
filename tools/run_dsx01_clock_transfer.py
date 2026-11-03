"""Bounded blind transfer of fixed CFO and nuisance rules across DSX01."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from dsx01_clock_transfer_models import MODES, transfer_problem
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import geometry_problem, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_dsx01_remeasured_position import OUTPUT as PREVIOUS
from prototype_dsx01_remeasured_position import apply_measurements

OUTPUT = ROOT / "reports/2026_10_18_dsx01_clock_transfer"
MEASUREMENTS = ("original", "glrt300")


def measurement_path(case):
    return (
        (PREVIOUS if case == "DSX01-S05" else OUTPUT) / "remeasurement" / case / "measurements.json"
    )


def read_pairs(case):
    path = ROOT / "reports/2026_10_18_dsx01_geographic_calibration/frame_coherent_calibration.json"
    data = json.loads(path.read_text())[case]
    bands = {
        int(b) for b, r in data["relative_calibration_by_band"].items() if r.get("supported", False)
    }
    return [p for p in data["pairs"] if int(p["channel"] > 4) in bands], bands


def check_pair(fits):
    a, b = fits["c0"], fits["fitted_c"]
    if a["rows"] != b["rows"] or a["aliases"] != b["aliases"] or a["starts"] != b["starts"]:
        raise AssertionError(
            "matched c arms differ in observations, nominations, aliases or starts"
        )


def parents(case):
    source = measurement_path(case)
    points = json.loads(source.read_text())["points"]
    scans = {}
    for variant in MEASUREMENTS:
        scans[variant] = Scan(case)
        apply_measurements(scans[variant], points, variant)
    for method in METHODS:
        directory = OUTPUT / "parents" / case / method
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "endpoints.json"
        results = json.loads(path.read_text()) if path.exists() else {}
        _, pair = choose_pair(incumbents(case, method))
        base = pair["c0"]
        seed = dict(rows=base["rows"], state=base["state"])
        anchor = base["east_north_km"]
        write(
            directory / "protocol.json",
            dict(
                case=case,
                method=method,
                measurements=MEASUREMENTS,
                no_GPS_or_future_TLE_input=True,
                original_curved_population_no_withholding=True,
                fixed_c0_blind_incumbent_nominations_and_initial_state=True,
                receiver_mean_contrast_sigmas_hz_s=[10, 0.5],
                phase_sigma_floor_s=1,
                matched_c_same_starts_and_24_iteration_budget=True,
                measurement_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                seed_sha256=hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(),
            ),
        )
        for variant in MEASUREMENTS:
            if variant in results:
                continue
            if case == "DSX01-S05":
                previous = PREVIOUS / "localization" / case / method / "endpoints.json"
                record = json.loads(previous.read_text())[variant]
                results[variant] = dict(
                    record,
                    reused_from=str(previous),
                    reused_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
                )
            else:

                def factory(*args):
                    return geometry_problem(*args, mean_sigma=10, height_sigma=0)

                results[variant] = dict(
                    fits=fit_once(scans[variant], seed, method, anchor, problem_class=factory)
                )
            check_pair(results[variant]["fits"])
            write(path, results)
            print(
                json.dumps(
                    dict(
                        stage="parents",
                        case=case,
                        method=method,
                        measurement=variant,
                        positions={
                            a: list(f["east_north_km"]) for a, f in results[variant]["fits"].items()
                        },
                    )
                ),
                flush=True,
            )


def priors(case, *, modes=MODES):
    method = "receiver_smooth"
    source = measurement_path(case)
    points = json.loads(source.read_text())["points"]
    centre = json.loads((SOURCE / case / f"{method}_center.json").read_text())
    _, incumbent = choose_pair(incumbents(case, method))
    seeds = dict(
        center=centre, wide_state=dict(rows=centre["rows"], state=incumbent["c0"]["state"])
    )
    pairs, bands = read_pairs(case)
    scans = {}
    for variant in MEASUREMENTS:
        scans[variant] = Scan(case)
        apply_measurements(scans[variant], points, variant)
    for mode in modes:
        directory = OUTPUT / "priors" / case / mode
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "attempts.json"
        results = json.loads(path.read_text()) if path.exists() else {}
        write(
            directory / "protocol.json",
            dict(
                case=case,
                method=method,
                mode=mode,
                no_GPS_or_future_TLE_input=True,
                original_curved_population_no_withholding=True,
                same_center_nominations_and_aliases_in_both_nuisance_proposals=True,
                proposals=list(seeds),
                all_geographic_anchors_are_town_center=True,
                supported_band_indices=sorted(bands),
                pair_band_support="20pairs,60seconds,2channels",
                only_repeated_curved_timing_links_with_agreeing_blind_labels=True,
                measurements=MEASUREMENTS,
                matched_c_same_starts_and_24_iteration_budget=True,
                final_proposal_selected_by_c0_score_with_exact_fitted_c_partner=True,
                drift_mixture_core_tail_probability_sigmas=[0.9, 0.5, 10],
                phase_mixture_core_probability=0.9,
                phase_tail_sigma_s="max(3,3*causal_sigma)",
                point_mixture_probability_sigmas=[0.98, 150, 5000],
                point_mixture_source_bias_sigma_hz=1000,
                point_mixture_EM_iterations=12,
                mixture_weights_are_declared_hypotheses_not_calibrated_probabilities=True,
                measurement_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                seeds_sha256={
                    n: hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()
                    for n, s in seeds.items()
                },
                sources_sha256={
                    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [Path(__file__), ROOT / "tools/dsx01_clock_transfer_models.py"]
                },
            ),
        )
        for variant in MEASUREMENTS:
            scan = scans[variant]
            reference = transfer_problem(
                scan, centre, method, False, [0, 0], pairs=pairs, mode="tight_causal"
            )
            aliases = reference.alias
            for proposal, seed in seeds.items():
                key = f"{variant}/{proposal}"
                if key in results:
                    continue

                def factory(*args, config=mode, fixed=aliases):
                    p = transfer_problem(*args, pairs=pairs, mode=config)
                    lock_aliases(p, fixed)
                    return p

                fits = fit_once(scan, seed, method, [0, 0], problem_class=factory)
                check_pair(fits)
                results[key] = dict(
                    fits=fits,
                    pair_metadata=factory(scan, seed, method, False, [0, 0]).pair_metadata,
                )
                write(path, results)
                print(
                    json.dumps(
                        dict(
                            stage="priors",
                            case=case,
                            mode=mode,
                            measurement=variant,
                            proposal=proposal,
                            positions={a: list(f["east_north_km"]) for a, f in fits.items()},
                        )
                    ),
                    flush=True,
                )
            candidates = {k: r for k, r in results.items() if k.startswith(variant + "/")}
            selected = min(candidates, key=lambda k: candidates[k]["fits"]["c0"]["score"])
            selected_path = directory / "selected.json"
            chosen = json.loads(selected_path.read_text()) if selected_path.exists() else {}
            chosen[variant] = dict(selected_proposal=selected, fits=candidates[selected]["fits"])
            write(selected_path, chosen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--stage", required=True, choices=["parents", "priors"])
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    a = parser.parse_args()
    parents(a.case) if a.stage == "parents" else priors(a.case, modes=a.modes)
