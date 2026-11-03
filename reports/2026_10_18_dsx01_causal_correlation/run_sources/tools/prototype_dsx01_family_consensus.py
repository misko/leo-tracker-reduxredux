"""Blind whole-family consensus, with each grid cell's nuisance terms profiled."""

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from prototype_dsx01_continuous_position import CENTER, GRID, latlon
from prototype_dsx01_phase_priors import CausalPhaseFamilies

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.family_switch_likelihood import family_residuals

OUTPUT = ROOT / "reports/2026_10_18_dsx01_family_consensus"
NOMINATIONS = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"
MODES = ("floor1_profiled", "causal_profiled", "consensus_floor", "consensus_causal")


class ConsensusFamilies(CausalPhaseFamilies):
    def __init__(self, scan, seed, method, fitted_c, anchor, *, mode="consensus_causal"):
        prior = "floor1" if mode in ("floor1_profiled", "consensus_floor") else "causal_gaussian"
        super().__init__(scan, seed, method, fitted_c, anchor, mode=prior)
        self.consensus = mode.startswith("consensus")
        blocks, support, offset = defaultdict(list), defaultdict(float), 0
        for i, row in zip(self.members, self.rows, strict=True):
            j, n = row["candidate_index"], len(scan.tracks[i]["times"])
            parts = 2 if method == "penalized_split" and row["split_at"] > 0 else 1
            blocks[j].extend(range(offset, offset + 2 * n + parts))
            support[j] += min(n, 50)
            offset += 2 * n + parts
        for k, j in enumerate(self.labels):
            blocks[j].append(self.phase_slice.start + k)
        offset = self.phase_slice.stop
        for j in self.extra_labels:
            count = 1 if method == "family_rate" else 2
            blocks[j].extend(range(offset, offset + count))
            offset += count
        self.family_blocks = [blocks[j] for j in self.labels]
        self.effective_support = [support[j] for j in self.labels]

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        if self.consensus:
            r, _ = family_residuals(r, self.family_blocks, self.effective_support, cap_per_point=4)
        return (r, diagnostics) if details else r


def fit_grid(scan, seed, method, mode):
    problems = {
        arm: ConsensusFamilies(scan, seed, method, arm == "fitted_c", (0, 0), mode=mode)
        for arm in ("c0", "fitted_c")
    }
    coarse = {arm: [] for arm in problems}
    for point in GRID:
        for arm, p in problems.items():
            x = p.initial.copy()
            x[:2] = point
            fit = bounded_gauss_newton(p.residual, x, p.lower, p.upper, iterations=6)
            fit["start_east_north_km"] = point
            coarse[arm].append(fit)
    order = sorted(range(len(GRID)), key=lambda k: coarse["c0"][k]["score"])
    selected = []
    for k in order:
        if all(
            np.linalg.norm(
                np.array(coarse["c0"][k]["parameters"][:2]) - coarse["c0"][j]["parameters"][:2]
            )
            >= 1
            for j in selected
        ):
            selected.append(k)
        if len(selected) == 3:
            break
    selected = (selected + [k for k in order if k not in selected])[:3]
    output = {}
    for arm, p in problems.items():
        fine = []
        for k in selected:
            fit = bounded_gauss_newton(
                p.residual, coarse[arm][k]["parameters"], p.lower, p.upper, iterations=24
            )
            fit["start_east_north_km"] = GRID[k]
            fine.append(fit)
        candidates = coarse[arm] + fine
        best = min(candidates, key=lambda r: r["score"])
        x = best["parameters"]
        penalty = len(x) * np.log(len(p.flat_times))
        output[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            frequency_prior_score=best["score"],
            score=best["score"] + penalty,
            complexity_penalty=penalty,
            state=p.decode(x),
            rows=p.rows,
            aliases=p.alias,
            coarse_fits=coarse[arm],
            fits=candidates,
            selected_original_grid_starts=[GRID[k] for k in selected],
            family_influence=(
                family_residuals(
                    super(ConsensusFamilies, p).residual(x), p.family_blocks, p.effective_support
                )[1]
                if p.consensus
                else None
            ),
        )
    return output


def run(case, method, modes=MODES):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    seed = json.loads((NOMINATIONS / case / f"{method}_center.json").read_text())
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_or_oracle_seed=True,
            center=CENTER,
            grid=GRID,
            region_box_km=[[-12.5, 12.5]] * 2,
            all_25_grid_starts_refined=True,
            coarse_iterations_per_start=6,
            fine_iterations=24,
            fine_starts=3,
            common_c0_selected_original_grid_starts_for_both_c_arms=True,
            raw_curved_only_calibration=True,
            orbit_priors_inside_family_consensus_cap=True,
            receiver_priors_outside_family_caps=True,
            cap_per_normalized_family=200,
            family_evidence_normalized_to_50_points_in_consensus_modes=True,
            physically_unverified_candidate_labels=True,
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    ROOT / "src/leo/analysis/research/family_switch_likelihood.py",
                )
            },
        ),
    )
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    for mode in modes:
        if all(f"{mode}/{arm}" in results for arm in ("c0", "fitted_c")):
            continue
        mark = time.monotonic()
        fits = fit_grid(scan, seed, method, mode)
        for arm, fit in fits.items():
            results[f"{mode}/{arm}"] = fit
        write(output, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    mode=mode,
                    seconds=time.monotonic() - mark,
                    positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--modes", choices=MODES, nargs="+", default=MODES)
    args = parser.parse_args()
    run(args.case, args.method, tuple(args.modes))
