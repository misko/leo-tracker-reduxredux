"""Shared frequency-event likelihood and exact paired phase-refresh fitting.

The signed-prior production path passes no events. Event coordinates retain the
original design slots for the subsequent recovery policies.
"""

import copy
from functools import lru_cache

import numpy as np

from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.hierarchical import hierarchical_bound
from leo.analysis.localization_v3.history_position import make_problem, scale_posterior
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.position import fit
from leo.analysis.localization_v3.predictive_linear import (
    geometry_features,
    linear_geometry,
    predictive_residual,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile


def event_design(times, receivers, channels, rf_hz, labels, events):
    t, rx, ch, rf, j = np.broadcast_arrays(
        np.asarray(times, float),
        np.asarray(receivers),
        np.asarray(channels),
        np.asarray(rf_hz, float),
        np.asarray(labels),
    )
    if t.ndim != 1 or not all(np.isfinite(v).all() for v in (t, rx, ch, rf, j)):
        raise ValueError("matching finite one-dimensional event coordinates required")
    columns = []
    for event in events:
        if event["kind"] not in ("receiver", "receiver_RF", "band", "family"):
            raise ValueError("unknown event kind")
        if (
            not np.isfinite(event["time_s"])
            or not np.isfinite(event["sigma_hz"])
            or event["sigma_hz"] < 0
        ):
            raise ValueError("finite event time and nonnegative prior SD required")
        use = (t >= event["time_s"]).astype(float)
        if event["kind"] == "family":
            use *= j == event["candidate_index"]
        else:
            use *= rx == event["receiver"]
        if event["kind"] == "band":
            use *= (ch > 4) == bool(event["band"])
        if event["kind"] in ("receiver_RF", "family"):
            use *= rf / 11500000000.0
        columns.append(use * event["sigma_hz"])
    return np.column_stack(columns) if columns else np.zeros((len(t), 0))


def track_events(track, label, events):
    n = len(track["times"])
    return event_design(
        track["times"],
        np.full(n, track["receiver"]),
        np.full(n, track["channel"]),
        np.full(n, track["rf_hz"]),
        np.full(n, label),
        events,
    )


def make_event_problem(
    scan, node, keep, arm, reference, powers, means, model, events, *, base_problem_factory=None
):
    factory = make_problem if base_problem_factory is None else base_problem_factory
    p = factory(scan, node, keep, arm, reference, powers, means, model["multiplier"], model["nu"])
    p.events = list(events)
    labels = np.asarray(p.labels)[p.flat_labels]
    receivers = np.concatenate(
        [np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["receiver"]) for i in p.members]
    )
    channels = np.concatenate(
        [np.full(len(scan.tracks[i]["times"]), scan.tracks[i]["channel"]) for i in p.members]
    )
    design = event_design(p.flat_times, receivers, channels, p.q * 11500000000.0, labels, events)
    original_state = p.state
    original_frequency = p.conditional_frequency
    original_width = (
        p.hardware.shape[1]
        + p.smooth.shape[1]
        + len(p.labels)
        + 3 * len(p.supported)
        + len(p.members)
    )
    p.event_start = original_width
    if not events:
        return p
    width = original_width + len(events)
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    mean = np.zeros(width)
    mean[begin : begin + len(p.labels)] = means / p.phase_sigma
    groups = np.full(width, -1, int)
    if model["nu"] is not None:
        groups[begin : begin + len(p.labels)] = np.arange(len(p.labels))
    scales = np.ones(width)
    scales[original_width - len(p.members) : original_width] = 0.3

    def calculate(position):
        geometry = JointMarginal.calculate(p, position)
        features = np.column_stack((geometry["features"], design))
        raw = p.values - p.q * geometry["intercept"] - features @ mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(
            raw[keep],
            (features * scales)[keep],
            p.point_noise[keep],
            p.noise_groups[keep],
            powers=np.asarray(powers)[present],
            prior_groups=None if model["nu"] is None else groups,
            prior_nu=4 if model["nu"] is None else model["nu"],
        )
        bound = scale_posterior(bound, scales)
        bound["latent_coefficient"] = bound["coefficient"].copy()
        bound["coefficient"] += mean
        precision = np.zeros(len(p.members))
        precision[present] = bound["noise_precision"]
        bound["noise_precision"] = precision
        bound["conditional_residual_hz"] = (
            p.values - p.q * geometry["intercept"] - features @ bound["coefficient"]
        )
        volume = float(
            2 * np.sum(np.asarray(powers)[p.noise_groups[keep]] * np.log(p.point_noise[keep] / 40))
        )
        bound["residual"] = np.r_[bound["residual"], np.sqrt(volume)]
        geometry.update(
            bound,
            features=features,
            event_amplitudes_hz=np.array([e["sigma_hz"] for e in events])
            * bound["coefficient"][original_width:],
        )
        return geometry

    p.calculate = calculate
    radio = [k for k, e in enumerate(events) if e["kind"] != "family"]
    family = [k for k, e in enumerate(events) if e["kind"] == "family"]
    p.scan = copy.copy(scan)
    base_hardware = scan.hardware
    nb = 8 + int(arm == "fitted_c")

    def hardware(track, beta):
        base = base_hardware(track, np.asarray(beta)[:nb])
        if radio:
            unit = [dict(events[k], sigma_hz=1.0) for k in radio]
            base = base + track_events(track, -1, unit) @ np.asarray(beta)[nb:]
        return base

    p.scan.hardware = hardware

    def state(position):
        result = original_state(position)
        c = p.calculate(position)
        amplitudes = c["event_amplitudes_hz"]
        result["frequency_events_hz"] = amplitudes
        if radio:
            result["beta"] = np.r_[result["beta"], amplitudes[radio]]
        return result

    p.state = state

    def conditional_frequency(position):
        f, elevation = original_frequency(position)
        if family:
            c = p.calculate(position)
            f = f + design[:, family] @ c["coefficient"][original_width + np.asarray(family)] / p.q
        return (f, elevation)

    p.conditional_frequency = conditional_frequency
    return p


def attach_event_predictive(p, entries, powers):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    rx = np.concatenate(
        [
            np.full(
                len(p.scan.tracks[e["track_index"]]["times"]),
                p.scan.tracks[e["track_index"]]["receiver"],
            )
            for e in entries
        ]
    )
    ch = np.concatenate(
        [
            np.full(
                len(p.scan.tracks[e["track_index"]]["times"]),
                p.scan.tracks[e["track_index"]]["channel"],
            )
            for e in entries
        ]
    )
    labels = np.asarray(p.labels)[view.flat_labels]
    design = event_design(view.flat_times, rx, ch, view.q * 11500000000.0, labels, p.events)
    curved = p.calculate

    def calculate(position):
        c = curved(position)
        g = p.noise_groups[p.keep]
        weights = np.asarray(powers)[g] * c["noise_precision"][g] / p.point_noise[p.keep] ** 2
        features = c["features"][p.keep]
        gram = np.diag(c["coefficient_prior_precision"]) + features.T @ (
            features * weights[:, None]
        )
        geometry = geometry_features(view, position, 0.0)
        all_features = np.column_stack((geometry["features"], design))
        predicted = view.q * geometry["intercept"] + all_features @ c["coefficient"]
        prediction = predictive_residual(
            values - predicted, all_features, gram, sigma * np.sqrt(2), groups
        )
        c["curved_negative_twice_elbo"] = c["negative_twice_elbo"]
        c["linear_predictive_objective"] = prediction["objective"]
        c["negative_twice_elbo"] += prediction["objective"]
        c["normalization_constant"] += prediction["normalization_constant"]
        c["residual"] = np.r_[c["residual"], prediction["residual"]]
        c["linear_raw_prediction_residual_hz"] = values - predicted
        c["linear_elevation"] = geometry["elevation"]
        return c

    p.calculate = calculate
    p.curved_calculate = curved
    p.linear_slices = slices
    p.linear_entries = entries
    return p


def event_profile(raw, design, sigma, groups, prior_sigma_hz=300.0):
    """Exact conditional Gaussian bound, eliminating one constant per curve."""
    y, d, s, g = (
        np.asarray(raw, float),
        np.asarray(design, float),
        np.asarray(sigma, float),
        np.asarray(groups, int),
    )
    if (
        y.ndim != 1
        or d.ndim != 2
        or d.shape[0] != len(y)
        or (s.shape != y.shape)
        or (g.shape != y.shape)
        or np.any(s <= 0)
    ):
        raise ValueError("matching event measurements, positive noise and curve groups required")
    constants = np.eye(int(g.max()) + 1)[g] * prior_sigma_hz
    u = np.column_stack((d, constants)) / s[:, None]
    z = y / s
    normal = np.eye(u.shape[1]) + u.T @ u
    rhs = u.T @ z
    coefficient = np.linalg.solve(normal, rhs)
    cost = float(z @ z - rhs @ coefficient + np.linalg.slogdet(normal)[1])
    return dict(cost=cost, coefficient=coefficient, covariance=np.linalg.inv(normal))


def cached(p):
    original = p.calculate

    @lru_cache(maxsize=8)
    def calculate(x):
        return original(np.asarray(x))

    p.calculate = lambda x: calculate(tuple(x))
    return p


def summary(p, x, entries):
    c = p.calculate(x)
    curved = p.curved_calculate(x) if entries else c
    linear = []
    for entry, sl in zip(entries, getattr(p, "linear_slices", []), strict=True):
        t = p.scan.tracks[entry["track_index"]]
        r = c["linear_raw_prediction_residual_hz"][sl]
        terms = profile(r, np.zeros(len(r)), *p.scan.white[entry["track_index"]], bias_sigma=300.0)
        noise = batch_noise_screen(terms["innovations"], t["times"])
        linear.append(
            dict(
                component=entry["component"],
                norad=entry["norad"],
                candidate_index=entry["candidate_index"],
                observation_ids=entry["observation_ids"],
                points=len(r),
                compatible=bool(
                    terms["rms"][0] <= 450
                    and abs(terms["bias"][0]) <= 3000
                    and (int(terms["alias"][0]) == 0)
                    and noise["noise_screen_pass"][0]
                    and (c["linear_elevation"][sl].min() >= 0)
                ),
            )
        )
    return dict(
        endpoint_east_north_km=x,
        endpoint_latlon=p.scan.search_region.latlon(x),
        state=p.state(x),
        phase_reference=p.reference,
        gates=retained_metrics(p, x),
        linear_gates=linear,
        negative_twice_elbo=c["negative_twice_elbo"],
        curved_negative_twice_elbo=curved["negative_twice_elbo"],
        RMS_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][p.keep] ** 2))),
        active_points=int(p.keep.sum()),
        predictive_points=sum(e["points"] for e in entries),
        linear_calibration_max_difference=float(
            np.max(abs(c["coefficient"] - curved["coefficient"]))
        ),
        events=p.events,
        event_amplitudes_hz=c.get("event_amplitudes_hz", np.array([])),
    )


def refit(scan, node, keep, arm, powers, means, model, events, entries):
    reference = np.zeros(len(means))
    x = np.zeros(2)
    history = []
    for _epoch in range(5):
        p = make_event_problem(scan, node, keep, arm, reference, powers, means, model, events)
        attach_event_predictive(p, entries, powers)
        cached(p)
        result = fit(p, x, iterations=48)
        x = np.asarray(result["parameters"])
        phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
        history.append(dict(fit=result, phase_change_s=float(np.max(abs(phase - reference)))))
        reference = phase
    record = summary(p, x, entries)
    record.update(history=history, final_phase_change_s=history[-1]["phase_change_s"])
    return record
