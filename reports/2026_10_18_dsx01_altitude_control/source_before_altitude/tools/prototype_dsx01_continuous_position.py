"""Blind 25 x 25 km Mill Valley probes with frozen curved-family hypotheses.

No evaluation GPS or oracle states enter this tool. These are exploratory
localization variants; fixed satellite nominations are not identity truth.
"""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan

from leo.analysis.research.continuous_curve_fit import (
    bounded_gauss_newton,
    paired_phase_frequency,
    project_curve,
    robust_curve,
)
from leo.analysis.research.retained_track_likelihood import PERIOD

OUTPUT = ROOT / "reports/2026_10_18_dsx01_mill_valley_continuous"
# Predeclared rounded town centre, independent of the evaluation site.
CENTER = (37.906, -122.545)
VARIANTS = ("continuous", "shape_only", "family_balanced")
GRID = tuple(
    (e, n) for e in (-12.5, -6.25, 0.0, 6.25, 12.5) for n in (-12.5, -6.25, 0.0, 6.25, 12.5)
)


def native_point(scan, local):
    east, north = local
    latitude = CENTER[0] + north / 111.0
    longitude = CENTER[1] + east / (111.32 * np.cos(np.deg2rad(CENTER[0])))
    return np.array(
        [(longitude - scan.center[1]) * scan.scale, (latitude - scan.center[0]) * 111.0]
    )


def latlon(local):
    return (
        CENTER[0] + local[1] / 111.0,
        CENTER[1] + local[0] / (111.32 * np.cos(np.deg2rad(CENTER[0]))),
    )


def numpy_state(state):
    return dict(
        beta=np.array(state["beta"]),
        phases=np.array(state["phases"]),
        extra={int(j): np.array(v) for j, v in state["extra"].items()},
        smooth=np.array(state["smooth"]),
    )


class FixedFamilies:
    """Keep the entire raw-curved population and one blind label per fragment."""

    def __init__(self, scan, seed, method, variant, fitted_c):
        self.scan, self.method, self.variant = scan, method, variant
        self.rows = [r for r in seed["rows"] if r["active_curvature"]]
        self.track_indices = {t["key"]: i for i, t in enumerate(scan.tracks)}
        self.members = [self.track_indices[r["component"]] for r in self.rows]
        assert set(self.members) == set(scan.curved)
        self.labels = sorted({r["candidate_index"] for r in self.rows})
        self.local_j = {j: k for k, j in enumerate(self.labels)}
        counts = np.array([len(scan.tracks[i]["times"]) for i in self.members])
        boundaries = np.r_[0, np.cumsum(counts)]
        self.slices = [slice(a, b) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True)]
        self.flat_times = np.concatenate([scan.tracks[i]["times"] for i in self.members])
        self.flat_labels = np.repeat(
            [self.local_j[r["candidate_index"]] for r in self.rows], counts
        )
        self.starts = numpy_state(seed["state"])
        if fitted_c:
            self.starts["beta"] = np.r_[self.starts["beta"][:8], 0.0]
        else:
            self.starts["beta"] = self.starts["beta"][:8]
        self.sky = dict(
            time_s=scan.sky["time_s"],
            position_km=scan.sky["position_km"][self.labels].copy(),
            velocity_km_s=scan.sky["velocity_km_s"][self.labels].copy(),
        )
        self.families = Counter(r["candidate_index"] for r in self.rows)
        self.coordinates = []
        self.initial, self.lower, self.upper = [], [], []

        def parameter(key, value, scale, low, high):
            self.coordinates.append((key, scale))
            self.initial.append(value / scale)
            self.lower.append(low / scale)
            self.upper.append(high / scale)

        parameter(("east", 0), 0.0, 1, -12.5, 12.5)
        parameter(("north", 0), 0.0, 1, -12.5, 12.5)
        if variant != "shape_only":
            for k, value in enumerate(self.starts["beta"]):
                scale = 1000 if k < 4 else (75 if k < 8 else 10000)
                bound = PERIOD / 2 if k < 4 else (150 if k < 8 else 200000)
                parameter(("beta", k), value, scale, -bound, bound)
        for j in self.labels:
            parameter(("phases", j), self.starts["phases"][j], 1, -15, 15)
        self.extra_labels = []
        if method in ("family_rate", "orbit_em"):
            for j in self.labels:
                channels = {
                    scan.tracks[i]["channel"]
                    for i, r in zip(self.members, self.rows, strict=True)
                    if r["candidate_index"] == j
                }
                if len(channels) < 2 or (variant == "shape_only" and method == "family_rate"):
                    continue
                self.extra_labels.append(j)
                for k in range(1 if method == "family_rate" else 2):
                    value = self.starts["extra"].get(j, np.zeros(2))[k]
                    scale, bound = (10, 20) if method == "family_rate" else (1e-4, 5e-4)
                    parameter(("extra", j, k), value, scale, -bound, bound)
                if method == "orbit_em":
                    scan.element_basis(j)
        if method == "receiver_smooth":
            for receiver in range(2):
                for k, value in enumerate(self.starts["smooth"][receiver]):
                    parameter(("smooth", receiver, k), value, 200, -2000, 2000)
        self.initial = np.clip(self.initial, self.lower, self.upper)
        self.alias = []
        frequency, _ = self.predicted(self.initial)
        for i, block in zip(self.members, self.slices, strict=True):
            t = scan.tracks[i]
            y = t["values"] - scan.hardware(t, self.starts["beta"])
            raw = y - t["rf_hz"] / 11.5e9 * frequency[block]
            if method == "receiver_smooth":
                raw -= (
                    t["rf_hz"]
                    / 11.5e9
                    * scan.rx_basis[i]
                    @ self.starts["smooth"][t["receiver"] - 1]
                )
            self.alias.append(int(np.rint(-raw.mean() / PERIOD)))

    def decode(self, x):
        state = numpy_state(self.starts)
        state["extra"] = {
            j: np.zeros(1 if self.method == "family_rate" else 2) for j in self.extra_labels
        }
        for (key, scale), value in zip(self.coordinates[2:], x[2:], strict=True):
            if key[0] in ("beta", "phases"):
                state[key[0]][key[1]] = value * scale
            else:
                state[key[0]][key[1]][key[2]] = value * scale
        return state

    def predicted(self, x):
        state = self.decode(x)
        sky = self.sky
        if self.method == "orbit_em":
            sky = {k: v.copy() for k, v in self.sky.items()}
            for j, extra in state["extra"].items():
                dp, dv = self.scan.element_basis(j)
                k = self.local_j[j]
                sky["position_km"][k] += np.einsum("k,ktd->td", extra, dp)
                sky["velocity_km_s"][k] += np.einsum("k,ktd->td", extra, dv)
        f, elevation = paired_phase_frequency(
            sky, self.flat_times, self.flat_labels, state["phases"][self.labels], *latlon(x[:2])
        )
        if self.method == "family_rate":
            for j, extra in state["extra"].items():
                use = self.flat_labels == self.local_j[j]
                f[use] += extra[0] * (self.flat_times[use] - 150)
        return f, elevation

    def residual(self, x, *, details=False):
        state, scan = self.decode(x), self.scan
        f, elevation = self.predicted(x)
        residuals, diagnostics = [], []
        for i, row, alias, observation_slice in zip(
            self.members, self.rows, self.alias, self.slices, strict=True
        ):
            t = scan.tracks[i]
            raw = t["values"] + alias * PERIOD - scan.hardware(t, state["beta"])
            raw = raw - t["rf_hz"] / 11.5e9 * f[observation_slice]
            if self.method == "receiver_smooth":
                raw -= t["rf_hz"] / 11.5e9 * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
            w = (scan.ou if self.method == "correlated_noise" else scan.white)[i][0]
            cut = row["split_at"] if self.method == "penalized_split" else -1
            blocks = (slice(None),) if cut <= 0 else (slice(0, cut), slice(cut, None))
            z = []
            for block in blocks:
                # Fixed split is diagnostic: preserve all observations, exactly
                # the same pieces/alias in both c arms, never pick a GPS split.
                ww = w if cut <= 0 else np.eye(len(raw[block])) / 150
                z.append(
                    project_curve(
                        raw[block], ww, t["times"][block], affine=self.variant == "shape_only"
                    )
                )
            z = np.concatenate(z)
            weight = min(1, 50 / len(raw))
            if self.variant == "family_balanced":
                weight /= self.families[row["candidate_index"]]
            transformed = robust_curve(z, len(raw)) * np.sqrt(weight)
            # Smooth visibility penalty, with no binary gate in the objective.
            below = np.maximum(0, -elevation[observation_slice])
            residuals.extend((transformed, below / 2))
            if details:
                diagnostics.append(
                    dict(
                        component=t["key"],
                        norad=row["candidate_norad"],
                        points=len(raw),
                        alias=alias,
                        cost=float(transformed @ transformed),
                        projected_rms_hz=float(150 * np.sqrt(np.mean(z[: len(raw)] ** 2))),
                        minimum_elevation_deg=float(elevation[observation_slice].min()),
                    )
                )
        if self.variant != "shape_only":
            residuals.append(state["beta"][4:8] / 75)
        residuals.append(state["phases"][self.labels] / scan.sigma[self.labels])
        for extra in state["extra"].values():
            residuals.append(extra / (10 if self.method == "family_rate" else 1e-4))
        if self.method == "receiver_smooth":
            residuals.append(state["smooth"].ravel() / 200)
        result = np.concatenate(residuals)
        return (result, diagnostics) if details else result


def run(case, *, methods=METHODS, iterations=24, starts=3):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    seed_path = directory / "mill_valley_center_seeds.json"
    if seed_path.exists():
        seeds = json.loads(seed_path.read_text())
    else:
        mark = time.monotonic()
        seeds = scan.at_point(native_point(scan, (0, 0)), rounds=8, all_tracks=False)
        write(seed_path, seeds)
        print(json.dumps(dict(case=case, center_seed_seconds=time.monotonic() - mark)), flush=True)
    protocol = dict(
        region_center=list(CENTER),
        region_box_km=[[-12.5, 12.5]] * 2,
        grid_east_north_km=GRID,
        methods=list(methods),
        variants=VARIANTS,
        max_joint_iterations=iterations,
        refined_grid_starts=starts,
        no_GPS_or_oracle_state_in_fit=True,
        raw_curved_only=True,
        labels_and_aliases_fixed_from_blind_center_c0_seed=True,
        all_raw_curved_fragments_retained_in_location_objective=True,
        paired_c_arms_same_labels_points_priors_grid_and_iterations=True,
        structure_gates_used_only_after_position_freeze=True,
        candidate_identities_not_verified=True,
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), ROOT / "src/leo/analysis/research/continuous_curve_fit.py")
        },
        bank_sha256=scan.receipt["bank_sha256"],
    )
    write(directory / "protocol.json", protocol)
    results = {}
    output = directory / "endpoints.json"
    if output.exists():
        results = json.loads(output.read_text())
    for method in methods:
        seed = seeds[f"c0/{method}"]
        for variant in VARIANTS:
            if all(f"{variant}/{arm}/{method}" in results for arm in ("c0", "fitted_c")):
                continue
            problems = {
                arm: FixedFamilies(scan, seed, method, variant, arm == "fitted_c")
                for arm in ("c0", "fitted_c")
            }
            grid = []
            for local in GRID:
                row = dict(east_north_km=local, scores={})
                for arm, problem in problems.items():
                    x = problem.initial.copy()
                    x[:2] = local
                    r = problem.residual(x)
                    row["scores"][arm] = float(r @ r)
                grid.append(row)
            selected = sorted(grid, key=lambda r: r["scores"]["c0"])[:starts]
            for arm, problem in problems.items():
                mark, fits = time.monotonic(), []
                for row in selected:
                    x = problem.initial.copy()
                    x[:2] = row["east_north_km"]
                    fit = bounded_gauss_newton(
                        problem.residual, x, problem.lower, problem.upper, iterations=iterations
                    )
                    fit["start_east_north_km"] = row["east_north_km"]
                    fits.append(fit)
                best = min(fits, key=lambda r: r["score"])
                state = problem.decode(best["parameters"])
                position = best["parameters"][:2]
                # Freeze position first; the evaluator is a separate program.
                key = f"{variant}/{arm}/{method}"
                results[key] = dict(
                    latitude_deg=latlon(position)[0],
                    longitude_deg=latlon(position)[1],
                    east_north_km=position,
                    score=best["score"],
                    state=state,
                    grid=grid,
                    starts=selected,
                    fits=fits,
                    curved_track_diagnostics=problem.residual(best["parameters"], details=True)[1],
                    elapsed_seconds=time.monotonic() - mark,
                )
                write(output, results)
                print(
                    json.dumps(
                        dict(
                            case=case,
                            key=key,
                            xy=list(position),
                            score=best["score"],
                            seconds=time.monotonic() - mark,
                        )
                    ),
                    flush=True,
                )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--iterations", type=int, default=24)
    parser.add_argument("--starts", type=int, default=3)
    args = parser.parse_args()
    run(args.case, methods=tuple(args.methods), iterations=args.iterations, starts=args.starts)
