"""Pure numerical positioning over caller-prepared ragged scanner tracks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.formal_orbit import (
    FormalOrbitConfig,
    FormalOrbitData,
    doppler_hz,
    fit_formal_orbit,
    phase_state,
)
from leo.analysis.research.identity_mixture import (
    MixtureConfig,
    mixture_statistics,
    profile_offsets,
)


@dataclass(frozen=True)
class ScanPositionEpisode:
    track_id: str
    pass_id: str
    observation_id: np.ndarray
    observed_hz: np.ndarray
    training: np.ndarray
    time_s: np.ndarray
    candidate_id: np.ndarray
    position_ecef_km: np.ndarray
    velocity_ecef_km_s: np.ndarray
    catalogue_size: int
    visible: np.ndarray | None = None
    orbit_age_h: np.ndarray | None = None
    phase_position_minus_ecef_km: np.ndarray | None = None
    phase_velocity_minus_ecef_km_s: np.ndarray | None = None
    phase_position_plus_ecef_km: np.ndarray | None = None
    phase_velocity_plus_ecef_km_s: np.ndarray | None = None
    phase_position_minus2_ecef_km: np.ndarray | None = None
    phase_velocity_minus2_ecef_km_s: np.ndarray | None = None
    phase_position_plus2_ecef_km: np.ndarray | None = None
    phase_velocity_plus2_ecef_km_s: np.ndarray | None = None

    def __post_init__(self):
        n, k = len(self.observed_hz), len(self.candidate_id)
        if not self.track_id or not self.pass_id or n < 4 or k < 1:
            raise ValueError("episode is incomplete")
        if any(
            np.asarray(x).shape != (n,) for x in (self.observation_id, self.training, self.time_s)
        ):
            raise ValueError("vector shape mismatch")
        if (
            np.asarray(self.training).dtype != bool
            or not np.any(self.training)
            or not np.any(~self.training)
        ):
            raise ValueError("train/evaluation mask required")
        if self.position_ecef_km.shape != (k, n, 3) or self.velocity_ecef_km_s.shape != (k, n, 3):
            raise ValueError("state shape mismatch")
        if self.catalogue_size < k or len(np.unique(self.observation_id)) != n:
            raise ValueError("invalid catalogue or duplicate IDs")
        if not all(
            np.all(np.isfinite(x))
            for x in (self.observed_hz, self.time_s, self.position_ecef_km, self.velocity_ecef_km_s)
        ):
            raise ValueError("non-finite input")
        if self.visible is not None and (
            np.asarray(self.visible).shape != (k,) or np.asarray(self.visible).dtype != bool
        ):
            raise ValueError("invalid visibility")
        outer = (
            self.phase_position_minus2_ecef_km,
            self.phase_velocity_minus2_ecef_km_s,
            self.phase_position_plus2_ecef_km,
            self.phase_velocity_plus2_ecef_km_s,
        )
        if any(x is not None for x in outer):
            if any(x is None for x in outer) or any(
                np.asarray(x).shape != (k, n, 3) for x in outer
            ):
                raise ValueError("all four candidate phase +/-2 arrays are required together")
            if not all(np.all(np.isfinite(x)) for x in outer):
                raise ValueError("candidate phase +/-2 arrays must be finite")


def _valid(eps):
    eps = tuple(eps)
    if not eps:
        return eps
    if len({e.track_id for e in eps}) != len(eps):
        raise ValueError("unique tracks required")
    ids = np.concatenate([np.asarray(e.observation_id).astype(str) for e in eps])
    if len(ids) != len(np.unique(ids)):
        raise ValueError("globally unique observation IDs required")
    return eps


def _point(region, xy):
    return region.points([float(xy[0])], [float(xy[1])])


def _opt(fn, region, initial):
    bounds = [
        (-region.width_km / 2, region.width_km / 2),
        (-region.height_km / 2, region.height_km / 2),
    ]
    if initial is None:
        grid = region.grid(max(region.width_km, region.height_km) / 16)
        values = np.asarray([fn((x, y)) for x, y in zip(grid.east_km, grid.north_km, strict=True)])
        initial = (grid.east_km[np.argmin(values)], grid.north_km[np.argmin(values)])
    return minimize(
        fn,
        np.asarray(initial, float),
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": 600, "xatol": 1e-4, "fatol": 1e-8},
    )


def _local_information(fn, xy, step_km=0.5):
    """Finite-difference curvature diagnostic for the profiled 2-D objective."""
    x = np.asarray(xy, float)
    e0, e1 = np.eye(2) * step_km
    try:
        f0 = fn(x)
        probes = [
            fn(x + e0),
            fn(x - e0),
            fn(x + e1),
            fn(x - e1),
            fn(x + e0 + e1),
            fn(x + e0 - e1),
            fn(x - e0 + e1),
            fn(x - e0 - e1),
        ]
    except ValueError:
        return {"rank": 0, "condition": None, "eigenvalues": [], "identified": False}
    h00 = (probes[0] - 2 * f0 + probes[1]) / step_km**2
    h11 = (probes[2] - 2 * f0 + probes[3]) / step_km**2
    h01 = (probes[4] - probes[5] - probes[6] + probes[7]) / (4 * step_km**2)
    eigenvalues = np.linalg.eigvalsh([[h00, h01], [h01, h11]])
    largest = float(eigenvalues[-1])
    identified = bool(eigenvalues[0] > max(1e-12, largest * 1e-8))
    condition = float(largest / eigenvalues[0]) if identified else None
    return {
        "rank": 2 if identified else int(np.sum(eigenvalues > 1e-12)),
        "condition": condition,
        "eigenvalues": eigenvalues.tolist(),
        "identified": identified,
    }


def _result(eps, name, a, region, tr, ev, **extra):
    p = _point(region, a.x)
    sources = {str(e.candidate_id[0]) for e in eps}
    boundary = (
        abs(a.x[0]) >= region.width_km / 2 - 1e-3 or abs(a.x[1]) >= region.height_km / 2 - 1e-3
    )
    state = (
        "complete" if a.success and not boundary else "failed" if not a.success else "insufficient"
    )
    reasons = (
        []
        if state == "complete"
        else ([str(a.message)] if not a.success else ["optimum is on regional boundary"])
    )
    return {
        "method": name,
        "state": state,
        "latitude_deg": float(p.latitude_deg[0]),
        "longitude_deg": float(p.longitude_deg[0]),
        "east_km": float(a.x[0]),
        "north_km": float(a.x[1]),
        "training_rms_hz": float(np.sqrt(np.mean(np.asarray(tr) ** 2))),
        "evaluation_rms_hz": float(np.sqrt(np.mean(np.asarray(ev) ** 2))),
        "track_count": len(eps),
        "source_count": len(sources),
        "training_point_count": len(tr),
        "evaluation_point_count": len(ev),
        "training_residual_hz": np.asarray(tr).tolist(),
        "evaluation_residual_hz": np.asarray(ev).tolist(),
        "track_ids": [e.track_id for e in eps],
        "observation_ids": [str(x) for e in eps for x in e.observation_id],
        "training_mask": [bool(x) for e in eps for x in e.training],
        "candidate_ids_by_track": [[str(x) for x in e.candidate_id] for e in eps],
        "objective": float(a.fun),
        "reasons": reasons,
        **extra,
    }


def _insufficient(eps, name, reason):
    return {
        "method": name,
        "state": "insufficient",
        "latitude_deg": None,
        "longitude_deg": None,
        "east_km": None,
        "north_km": None,
        "training_rms_hz": None,
        "evaluation_rms_hz": None,
        "track_count": len(eps),
        "source_count": len({str(e.candidate_id[0]) for e in eps}),
        "training_point_count": sum(int(np.sum(e.training)) for e in eps),
        "evaluation_point_count": sum(int(np.sum(~e.training)) for e in eps),
        "training_residual_hz": [],
        "evaluation_residual_hz": [],
        "track_ids": [e.track_id for e in eps],
        "observation_ids": [str(x) for e in eps for x in e.observation_id],
        "training_mask": [bool(x) for e in eps for x in e.training],
        "candidate_ids_by_track": [[str(x) for x in e.candidate_id] for e in eps],
        "objective": None,
        "modes": {},
        "diagnostics": {},
        "reasons": [reason],
    }


def fit_expanded_pass_balanced_doppler(episodes, region, initial_xy_km=None, *, sigma_hz=250.0):
    eps = _valid(episodes)
    if len({str(e.candidate_id[0]) for e in eps}) < 3:
        return _insufficient(
            eps, "expanded_pass_balanced_doppler", "fewer than three fixed sources"
        )
    if sigma_hz <= 0:
        raise ValueError("positive sigma required")

    def residual(xy):
        rx = _point(region, xy).ecef_km[0]
        out = []
        offsets = []
        for e in eps:
            raw = e.observed_hz - doppler_hz(rx, e.position_ecef_km[0], e.velocity_ecef_km_s[0])
            off = float(np.mean(raw[e.training]))
            out.append(raw - off)
            offsets.append(off)
        return out, offsets

    passes = sorted({e.pass_id for e in eps})

    def objective(xy):
        r, _ = residual(xy)
        per = []
        for pid in passes:
            z = np.concatenate(
                [x[e.training] / sigma_hz for e, x in zip(eps, r, strict=True) if e.pass_id == pid]
            )
            per.append(np.mean(np.sqrt(1 + z * z) - 1))
        return float(np.mean(per))

    a = _opt(objective, region, initial_xy_km)
    r, offsets = residual(a.x)
    tr = np.concatenate([x[e.training] for e, x in zip(eps, r, strict=True)])
    ev = np.concatenate([x[~e.training] for e, x in zip(eps, r, strict=True)])
    information = _local_information(objective, a.x)
    result = _result(
        eps,
        "expanded_pass_balanced_doppler",
        a,
        region,
        tr,
        ev,
        modes={
            "fixed_candidate_id": [str(e.candidate_id[0]) for e in eps],
            "candidate_weights_by_track": [[1.0] + [0.0] * (len(e.candidate_id) - 1) for e in eps],
        },
        diagnostics={
            "track_offsets_hz": offsets,
            "pass_count": len(passes),
            "weighting": "equal robust mean per pass",
            "local_information": information,
        },
    )
    if not information["identified"]:
        result["state"] = "insufficient"
        result["reasons"].append("profiled position objective lacks rank-two curvature")
    return result


def fit_joint_position_orbit_corrections(episodes, region, initial_xy_km=None, *, config=None):
    eps = _valid(episodes)
    names = (
        "orbit_age_h",
        "phase_position_minus_ecef_km",
        "phase_velocity_minus_ecef_km_s",
        "phase_position_plus_ecef_km",
        "phase_velocity_plus_ecef_km_s",
    )
    outer_names = (
        "phase_position_minus2_ecef_km",
        "phase_velocity_minus2_ecef_km_s",
        "phase_position_plus2_ecef_km",
        "phase_velocity_plus2_ecef_km_s",
    )
    if len({str(e.candidate_id[0]) for e in eps}) < 3:
        return _insufficient(
            eps, "joint_position_orbit_corrections", "fewer than three fixed sources"
        )
    if any(getattr(e, n) is None for e in eps for n in names):
        raise ValueError("phase +/- states and ages required")
    uses_quartic = all(getattr(e, n) is not None for e in eps for n in outer_names)
    if not uses_quartic and any(getattr(e, n) is not None for e in eps for n in outer_names):
        raise ValueError("phase +/-2 states must be available for every episode")
    if initial_xy_km is None:
        seed = fit_expanded_pass_balanced_doppler(eps, region)
        initial_xy_km = (seed["east_km"], seed["north_km"])

    def cat(attr):
        return np.concatenate([np.asarray(getattr(e, attr))[0] for e in eps])

    y = np.concatenate([e.observed_hz for e in eps])
    train = np.concatenate([e.training for e in eps])
    seg = np.concatenate([np.full(len(e.observed_hz), i) for i, e in enumerate(eps)])
    src = np.concatenate([np.full(len(e.observed_hz), str(e.candidate_id[0])) for e in eps])
    outer_states = tuple(cat(name) for name in outer_names) if uses_quartic else (None,) * 4
    d = FormalOrbitData(
        y,
        train,
        seg,
        seg.copy(),
        src,
        cat("orbit_age_h"),
        np.concatenate([e.position_ecef_km[0] for e in eps]),
        np.concatenate([e.velocity_ecef_km_s[0] for e in eps]),
        cat(names[1]),
        cat(names[2]),
        cat(names[3]),
        cat(names[4]),
        np.concatenate([e.time_s for e in eps]),
        np.concatenate([e.observation_id for e in eps]),
        *outer_states,
    )
    cfg = config or FormalOrbitConfig()
    f = fit_formal_orbit(d, region, initial_xy_km, cfg)
    rx = _point(region, f.x_km).ecef_km[0]
    rates = np.asarray([f.rate_corrections_s_h[str(x)] for x in src])
    phase_s = d.age_h * rates
    corrected_p = phase_state(
        d.p_km,
        d.phase_p_minus_km,
        d.phase_p_plus_km,
        phase_s,
        cfg.phase_sensitivity_step_s,
        minus2=d.phase_p_minus2_km,
        plus2=d.phase_p_plus2_km,
    )
    corrected_v = phase_state(
        d.v_km_s,
        d.phase_v_minus_km_s,
        d.phase_v_plus_km_s,
        phase_s,
        cfg.phase_sensitivity_step_s,
        minus2=d.phase_v_minus2_km_s,
        plus2=d.phase_v_plus2_km_s,
    )
    r = y - doppler_hz(rx, corrected_p, corrected_v)
    for i, off in f.segment_offsets_hz.items():
        r[seg == int(i)] -= off

    class A:
        pass

    a = A()
    a.x = np.asarray(f.x_km)
    a.fun = f.negative_log_posterior
    a.success = f.converged
    a.message = f.identifiability
    ans = _result(
        eps,
        "joint_position_orbit_corrections",
        a,
        region,
        r[train],
        r[~train],
        modes={
            "fixed_candidate_id": [str(e.candidate_id[0]) for e in eps],
            "candidate_weights_by_track": [[1.0] + [0.0] * (len(e.candidate_id) - 1) for e in eps],
        },
        diagnostics={
            "rate_corrections_s_h": f.rate_corrections_s_h,
            "track_offsets_hz": f.segment_offsets_hz,
            "identifiability": f.identifiability,
            "information_rank": f.information_rank,
            "information_condition": (
                float(f.information_condition) if np.isfinite(f.information_condition) else None
            ),
            "major_95_km": f.major_95_km,
            "model": f.approximation,
            "phase_interpolation": "quartic_5_point" if uses_quartic else "quadratic_3_point",
            "exact_correction_replay": "pending",
        },
    )
    ans["training_rms_hz"] = f.training_rms_hz
    ans["evaluation_rms_hz"] = f.evaluation_rms_hz
    if f.identifiability != "identified":
        ans["state"] = "insufficient"
        ans["reasons"].append(f"formal information geometry is {f.identifiability}")
    return ans


def fit_soft_identity_mixture(episodes, region, initial_xy_km=None, *, config=None):
    eps = _valid(episodes)
    cfg = config or MixtureConfig()
    if len(eps) < 3:
        return _insufficient(eps, "soft_identity_mixture", "fewer than three tracks")
    if initial_xy_km is None:
        seed = fit_expanded_pass_balanced_doppler(eps, region)
        initial_xy_km = (seed["east_km"], seed["north_km"])

    def stats(xy):
        rx = _point(region, xy).ecef_km[0]
        out = []
        for e in eps:
            pred = np.asarray(
                [
                    doppler_hz(rx, p, v)
                    for p, v in zip(e.position_ecef_km, e.velocity_ecef_km_s, strict=True)
                ]
            )
            out.append(
                mixture_statistics(
                    e.observed_hz[None] - pred,
                    e.observed_hz,
                    np.zeros(len(e.observed_hz), int),
                    e.training,
                    e.catalogue_size,
                    visible=e.visible,
                    config=cfg,
                )
            )
        return out

    a = _opt(
        lambda xy: -sum(float(s["train_log_evidence"]) for s in stats(xy)), region, initial_xy_km
    )
    information = _local_information(
        lambda xy: -sum(float(s["train_log_evidence"]) for s in stats(xy)), a.x
    )
    final = stats(a.x)
    rx = _point(region, a.x).ecef_km[0]
    residual = []
    modes = []
    for e, s in zip(eps, final, strict=True):
        m = int(np.argmax(s["candidate_posterior"]))
        modes.append(m)
        raw = e.observed_hz - doppler_hz(rx, e.position_ecef_km[m], e.velocity_ecef_km_s[m])
        residual.append(profile_offsets(raw, np.zeros(len(raw), int), e.training)[0])
    tr = np.concatenate([r[e.training] for e, r in zip(eps, residual, strict=True)])
    ev = np.concatenate([r[~e.training] for e, r in zip(eps, residual, strict=True)])
    result = _result(
        eps,
        "soft_identity_mixture",
        a,
        region,
        tr,
        ev,
        modes={
            "candidate_id": [str(e.candidate_id[m]) for e, m in zip(eps, modes, strict=True)],
            "candidate_posterior": [np.asarray(s["candidate_posterior"]).tolist() for s in final],
            "candidate_weights_by_track": [
                np.asarray(s["candidate_posterior"]).tolist() for s in final
            ],
            "unassigned_posterior": [float(s["unassigned_posterior"]) for s in final],
        },
        diagnostics={
            "heldout_log_predictive": float(sum(s["heldout_log_predictive"] for s in final)),
            "correlation_warning": (
                "per-track identity likelihoods are composite and not a calibrated "
                "independent-RX posterior"
            ),
            "candidate_scope": (
                "site-conditioned alternatives; no independent association validation"
            ),
            "local_information": information,
        },
    )
    meaningful = [
        str(e.candidate_id[m])
        for e, m, s in zip(eps, modes, final, strict=True)
        if 1.0 - float(s["unassigned_posterior"]) >= 0.5
    ]
    result["selected_mode_source_count"] = len(set(meaningful))
    if len(set(meaningful)) < 3:
        result["state"] = "insufficient"
        result["reasons"].append("fewer than three distinct signal-dominated mode sources")
    if not information["identified"]:
        result["state"] = "insufficient"
        result["reasons"].append("profiled mixture objective lacks rank-two curvature")
    return result
