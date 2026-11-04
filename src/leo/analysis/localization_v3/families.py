"""Fixed-family layout and aliases, with an explicitly supplied search region."""
from collections import Counter

import numpy as np

from leo.analysis.research.continuous_curve_fit import (
    paired_phase_frequency,
    project_curve,
    robust_curve,
)
from leo.analysis.research.retained_track_likelihood import PERIOD


def numpy_state(state):
    return dict(
        beta=np.array(state["beta"]),
        phases=np.array(state["phases"]),
        extra={int(j): np.array(v) for j, v in state["extra"].items()},
        smooth=np.array(state["smooth"]),
    )


def nomination_rows(scan, rows, nominations):
    """Take the lowest visible cost nominee, independent of binary noise gates."""
    result = []
    for row in rows:
        if not row["active_curvature"]:
            raise ValueError("linear tracks cannot nominate calibration families")
        i = next(k for k in scan.curved if scan.tracks[k]["key"] == row["component"])
        n = nominations[i]
        j, terms = n["j"], n["terms"]
        result.append(
            dict(
                row,
                candidate_index=int(j),
                candidate_norad=int(scan.norads[j]),
                rms_hz=float(terms["rms"][j]),
                bias_hz=float(terms["bias"][j]),
                cost=float(terms["cost"][j]),
                parts=int(terms["parts"][j]),
                split_at=int(terms["split_at"][j]),
                compatible=bool(terms["passing"][j]),
            )
        )
    return result


class FixedFamilies:
    """Keep the entire raw-curved population and one blind label per fragment."""

    def __init__(self, scan, seed, method, variant, fitted_c):
        if scan.search_region is None:
            raise ValueError("An explicit search region is required")
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

        parameter(("east", 0), 0.0, 1, -scan.search_region.half_width_km,
                  scan.search_region.half_width_km)
        parameter(("north", 0), 0.0, 1, -scan.search_region.half_width_km,
                  scan.search_region.half_width_km)
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

    def orbit_sky(self, state):
        """Return state-corrected causal geometry for shared orbital controls."""
        sky = self.sky
        if self.method == "orbit_em":
            sky = {k: v.copy() for k, v in self.sky.items()}
            for j, extra in state["extra"].items():
                dp, dv = self.scan.element_basis(j)
                k = self.local_j[j]
                sky["position_km"][k] += np.einsum("k,ktd->td", extra, dp)
                sky["velocity_km_s"][k] += np.einsum("k,ktd->td", extra, dv)
        return sky

    def predicted(self, x):
        state = self.decode(x)
        sky = self.orbit_sky(state)
        times = self.observation_times(state)
        f, elevation = paired_phase_frequency(
            sky,
            times,
            self.flat_labels,
            state["phases"][self.labels],
            *self.scan.search_region.latlon(x[:2]),
            altitude_m=state.get("altitude_m", 0.0),
        )
        if self.method == "family_rate":
            for j, extra in state["extra"].items():
                use = self.flat_labels == self.local_j[j]
                f[use] += extra[0] * (times[use] - 150)
        return f, elevation

    def observation_times(self, state):
        """UTC sample times; timing-control subclasses may supply receiver shifts."""
        return self.flat_times

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


class AnchoredFamilies(FixedFamilies):
    """Fix aliases at the actual blind calibration anchor, rather than town zero."""

    def __init__(self, scan, seed, method, fitted_c, anchor):
        super().__init__(scan, seed, method, "continuous", fitted_c)
        self.initial[:2] = anchor
        frequency, _ = self.predicted(self.initial)
        self.alias = []
        for i, block in zip(self.members, self.slices, strict=True):
            t = scan.tracks[i]
            raw = t["values"] - scan.hardware(t, self.starts["beta"])
            raw = raw - t["rf_hz"] / 11.5e9 * frequency[block]
            if method == "receiver_smooth":
                raw -= (
                    t["rf_hz"]
                    / 11.5e9
                    * scan.rx_basis[i]
                    @ self.starts["smooth"][t["receiver"] - 1]
                )
            self.alias.append(int(np.rint(-raw.mean() / PERIOD)))
