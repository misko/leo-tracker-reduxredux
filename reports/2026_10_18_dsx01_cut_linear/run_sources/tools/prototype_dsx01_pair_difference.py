"""Separate source-common frequency error from simultaneous RX differences.

Pair means and differences replace the two original observations; they are
never appended as extra observations. Only repeated frame-coherent links of
originally curved fragments with agreeing blind satellite labels are eligible.
"""

import argparse
import json
from collections import Counter

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from profile_dsx01_geographic_calibration import incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_dsx01_remeasured_position import OUTPUT, VARIANTS, apply_measurements
from prototype_s01_receiver_drift import ReceiverDriftProblem

from leo.analysis.research.continuous_curve_fit import robust_curve


def orthogonal_parts(values, left, right):
    """Return exactly N orthogonal coordinates, separating paired differences."""
    y = np.asarray(values)
    a, b = np.asarray(left, dtype=int), np.asarray(right, dtype=int)
    if len(a) != len(b) or len(set(np.r_[a, b])) != 2 * len(a):
        raise ValueError("pairs must be disjoint")
    if len(a) and (np.min(np.r_[a, b]) < 0 or np.max(np.r_[a, b]) >= len(y)):
        raise ValueError("pair index outside observation inventory")
    unpaired = np.setdiff1d(np.arange(len(y)), np.r_[a, b])
    common = np.r_[y[unpaired], (y[a] + y[b]) / np.sqrt(2)]
    difference = (y[a] - y[b]) / np.sqrt(2)
    constant_design = np.r_[np.ones(len(unpaired)), np.full(len(a), np.sqrt(2))]
    return common, difference, constant_design


class PairDifferenceFamilies(AnchoredFamilies):
    def __init__(self, *args, provided_pairs, phase_mode="causal", use_pairs=True):
        super().__init__(*args)
        if self.method not in ("shared_phase", "receiver_smooth"):
            raise ValueError("pair prototype currently covers shared phase and smooth receiver")
        self.phase_mode = phase_mode
        oid_index = {
            oid: (i, sl.start + k)
            for i, sl in zip(self.members, self.slices, strict=True)
            for k, oid in enumerate(self.scan.tracks[i]["observation_ids"])
        }
        labels = {i: r["candidate_index"] for i, r in zip(self.members, self.rows, strict=True)}
        eligible = []
        edges = Counter()
        skipped = 0
        for row in provided_pairs if use_pairs else []:
            if not row["frame_coherent"] or not row["both_original_curved"]:
                continue
            if any(oid not in oid_index for oid in row["observation_ids"]):
                continue
            (i, a), (j, b) = [oid_index[oid] for oid in row["observation_ids"]]
            if labels[i] != labels[j]:
                skipped += 1
                continue
            edge = tuple(sorted((i, j)))
            edges[edge] += 1
            eligible.append((edge, a, b))
        eligible = [p for p in eligible if edges[p[0]] >= 3]
        parent = {i: i for i in self.members}

        def root(i):
            while parent[i] != i:
                i = parent[i]
            return i

        for (i, j), _, _ in eligible:
            parent[root(i)] = root(j)
        groups = {}
        for i, sl in zip(self.members, self.slices, strict=True):
            groups.setdefault(root(i), []).extend(range(sl.start, sl.stop))
        self.pair_groups = []
        for owner, positions in groups.items():
            lookup = {a: k for k, a in enumerate(positions)}
            pairs = [(lookup[a], lookup[b]) for (i, _), a, b in eligible if root(i) == owner]
            a, b = (
                (np.array(v, dtype=int) for v in zip(*pairs, strict=True))
                if pairs
                else (np.array([], dtype=int), np.array([], dtype=int))
            )
            # Validate that the transformation counts every original point once.
            common, difference, design = orthogonal_parts(np.zeros(len(positions)), a, b)
            assert len(common) + len(difference) == len(positions)
            self.pair_groups.append((np.array(positions), a, b, design))
        self.pair_metadata = dict(
            paired_points=2 * len(eligible),
            pairs=len(eligible),
            groups=len(groups),
            skipped_disagreeing_labels=skipped,
            original_points=len(self.flat_times),
        )

    def residual(self, x, *, details=False):
        state = self.decode(x)
        f, e = self.predicted(x)
        raw = np.empty(len(self.flat_times))
        for i, sl, alias in zip(self.members, self.slices, self.alias, strict=True):
            t = self.scan.tracks[i]
            q = t["rf_hz"] / 11.5e9
            raw[sl] = (
                t["values"] + alias / 4.4e-6 - self.scan.hardware(t, state["beta"]) - q * f[sl]
            )
            if self.method == "receiver_smooth":
                raw[sl] -= q * (self.scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1])
        residuals = [np.maximum(0, -e) / 2]
        for positions, a, b, design in self.pair_groups:
            common, difference, _ = orthogonal_parts(raw[positions], a, b)
            # One transmitter/source constant per timing-linked group. It
            # vanishes exactly from the orthogonal difference coordinates.
            bias = np.dot(design, common) / (design @ design + 150**2 / 1000**2)
            z = np.r_[(common - design * bias) / 150, bias / 1000]
            residuals.append(robust_curve(z, len(common)) * np.sqrt(min(1, 50 / len(common))))
            z = difference / 150
            # Pointwise Huber protection is independent of family orbit error.
            residuals.append(np.sign(z) * np.sqrt(np.where(abs(z) <= 3, z * z, 6 * abs(z) - 9)))
        residuals.append(state["beta"][4:8] / 75)
        sigma = (
            self.scan.sigma[self.labels]
            if self.phase_mode == "floor"
            else np.maximum(0.1, self.scan.sky["phase_sigma_s"][self.labels])
        )
        residuals.append(state["phases"][self.labels] / sigma)
        if self.method == "receiver_smooth":
            residuals.append(state["smooth"].ravel() / 200)
        r = np.concatenate(residuals)
        return (r, [self.pair_metadata]) if details else r


def pair_problem(*args, pairs, mode, use_pairs):
    p = PairDifferenceFamilies(
        *args, provided_pairs=pairs, phase_mode="causal", use_pairs=use_pairs
    )
    return (
        restore_radio_initialization(ReceiverDriftProblem(p, mean_sigma=10))
        if mode == "wide_causal"
        else p
    )


def run(case, method, mode):
    source = OUTPUT / "remeasurement" / case / "measurements.json"
    points = json.loads(source.read_text())["points"]
    pairs = json.loads(
        (
            OUTPUT.parent
            / "2026_10_18_dsx01_geographic_calibration/frame_coherent_calibration.json"
        ).read_text()
    )[case]["pairs"]
    if mode == "tight_causal":
        seed = json.loads((SOURCE / case / f"{method}_center.json").read_text())
        anchor = [0, 0]
    else:
        _, pair = choose_pair(incumbents(case, method))
        seed = pair["c0"]
        anchor = seed["east_north_km"]
    directory = OUTPUT / "pair_difference" / case / mode / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            case=case,
            method=method,
            mode=mode,
            variants=VARIANTS,
            same_original_curved_points_latest_causal_candidates_no_GPS=True,
            pair_means_differences_replace_not_duplicate_original_points=True,
            minimum_repeated_timing_links_per_fragment_pair=3,
            blind_labels_must_agree=True,
            difference_point_Huber_threshold_sigma=3,
            white_sigma_hz=150,
            source_bias_sigma_hz=1000,
            same_c0_selected_starts_and_24_iterations_for_c_arms=True,
        ),
    )
    for variant in VARIANTS:
        scan = Scan(case)
        meta = apply_measurements(scan, points, variant)
        for use_pairs in (False, True):
            key = f"{variant}/pairs{int(use_pairs)}"
            if key in results:
                continue

            def factory(*args, enabled=use_pairs):
                return pair_problem(*args, pairs=pairs, mode=mode, use_pairs=enabled)

            fits = fit_once(scan, seed, method, anchor, problem_class=factory)
            results[key] = dict(
                fits=fits,
                measurement_metadata=meta,
                pair_metadata=factory(scan, seed, method, False, anchor).pair_metadata,
            )
            write(path, results)
            print(
                json.dumps(
                    dict(
                        method=method,
                        mode=mode,
                        variant=key,
                        positions={a: list(f["east_north_km"]) for a, f in fits.items()},
                    )
                ),
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S05")
    parser.add_argument(
        "--method", choices=["shared_phase", "receiver_smooth"], default="receiver_smooth"
    )
    parser.add_argument("--mode", choices=["tight_causal", "wide_causal"], required=True)
    a = parser.parse_args()
    run(a.case, a.method, a.mode)
