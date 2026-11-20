"""Compare zero, common and independent carrier offsets on held VHF passes."""

import numpy as np
from scipy.optimize import least_squares

if __package__:
    from . import external_orbcomm as base
else:
    import external_orbcomm as base

METHODS = (
    "orbcomm_shared_offset",
    "orbcomm_zero_offset",
    "orbcomm_free_pass",
    "orbcomm_final_time_reverse",
    "orbcomm_final_offer_center",
)
MIN_RF_RELATIVE_NORM = 0.05
RF_REFERENCE_HZ = 137.5e6


def anchored(panel, xy, c=0.0):
    r = panel.profile(xy, "absolute")
    f = (panel.rf_hz - RF_REFERENCE_HZ) / 1e6
    here = r - c * f * panel.weights
    return here - (here @ panel.weights) * panel.weights


def slope_column(panel):
    axis = (panel.rf_hz - RF_REFERENCE_HZ) / 1e6 * panel.weights
    return axis - (axis @ panel.weights) * panel.weights


def relative_leverage(panel, center):
    column = slope_column(panel)
    derivatives = np.column_stack(
        [
            (anchored(panel, base.geographic(center, step)) - anchored(panel, center)) / 0.02
            for step in ((0.02, 0.0), (0.0, 0.02))
        ]
    )
    fit = np.linalg.lstsq(derivatives, column, rcond=None)[0]
    scale = float(np.linalg.norm(column))
    return float(np.linalg.norm(column - derivatives @ fit) / scale) if scale else 0.0


def shared_fit(training, held, center, estimate=False):
    def fit(panel, profile_slope, fixed_c):
        axis = slope_column(panel)
        axis_energy = axis @ axis

        def locate(local):
            point = base.geographic(center, local)
            carrier = anchored(panel, point, fixed_c)
            c = float((carrier @ axis) / axis_energy) if profile_slope else fixed_c
            return (carrier - c * axis if profile_slope else carrier), c

        def residual(local):
            return locate(local)[0]

        grid = np.linspace(-base.WIDTH / 2, base.WIDTH / 2, base.GRID_POINTS)
        start = min(((e, n) for e in grid for n in grid), key=lambda q: np.linalg.norm(residual(q)))
        outcome = least_squares(
            residual,
            start,
            bounds=(-base.WIDTH / 2, base.WIDTH / 2),
            max_nfev=30,
            ftol=1e-7,
            xtol=1e-7,
            gtol=1e-7,
        )
        return outcome, residual, locate(outcome.x)[1]

    first, loss, c = fit(training, estimate, 0.0)
    independent, test, _ = fit(held, False, c)
    singular = np.linalg.svd(first.jac, compute_uv=False)
    rf = float(np.linalg.norm(test(first.x)))
    where = base.geographic(center, first.x)
    weighted = training.profile(where, "absolute")
    nominal_rf = (training.rf_hz - RF_REFERENCE_HZ) / 1e6
    return dict(
        forced_latlon=where,
        horizontal_rank=int(np.count_nonzero(singular > 1e-5)),
        numerically_returned=bool(first.success and independent.success),
        max_face_km=float(base.WIDTH / 2 - max(abs(first.x))),
        held_face_km=float(base.WIDTH / 2 - max(abs(independent.x))),
        held_stability_km=float(np.linalg.norm(first.x - independent.x)),
        held_center_gain_hz=float(np.linalg.norm(test((0, 0))) - rf),
        training_rms_hz=float(np.linalg.norm(loss(first.x))),
        held_rms_hz=rf,
        c_hz_per_mhz=c,
        receiver_offset_hz=float((weighted - c * nominal_rf * training.weights) @ training.weights),
    )


def endpoint(data):
    reason = base.hold_reason(data)
    return dict(
        latlon=data["forced_latlon"] if reason is None else None,
        forced_latlon=data["forced_latlon"] if reason else None,
        rf_rms_hz=data["held_rms_hz"],
        status="withheld" if reason else "published",
        reason=reason,
    )


def one_arm(data, unavailable):
    arm = endpoint(data)
    return dict(
        status="ok" if arm["latlon"] is not None else "withheld",
        reason=arm["reason"],
        boundary="Cooperative VHF Doppler at one measured receiver",
        metrics=data,
        arms=dict(c0=arm, fitted_c=dict(latlon=None, status="unavailable", reason=unavailable)),
    )


def infer(packet, center):
    train = base.observations(packet["training"], packet["elements"])
    held = base.observations(packet["held"], packet["elements"])
    leverage = [relative_leverage(panel, center) for panel in (train, held)]
    zero = shared_fit(train, held, center)
    conditional = (
        shared_fit(train, held, center, estimate=True)
        if min(leverage) > MIN_RF_RELATIVE_NORM
        else None
    )
    outcomes = {
        "c0": endpoint(zero),
        "fitted_c": endpoint(conditional)
        if conditional is not None
        else dict(
            latlon=None, status="unavailable", reason="insufficient_conditional_rf_design_rank"
        ),
    }
    published = any(arm["latlon"] is not None for arm in outcomes.values())
    shared = dict(
        status="ok" if published else "withheld",
        reason=None if published else "neither_calibration_passed",
        boundary="Cooperative VHF Doppler at one measured receiver",
        metrics=dict(
            c0=zero,
            fitted_c=conditional,
            rf_relative_leverage=leverage,
            rf_slope_scope="conditional on common offset and nominal carriers",
        ),
        arms=outcomes,
    )
    controls = [
        one_arm(base.solve_mode(train, held, center, kind), msg)
        for kind, msg in (
            ("absolute", "nominal_zero_frequency_control"),
            ("shape", "per_pass_offsets_span_rf_term"),
            ("reversed", "per_pass_offsets_span_rf_term"),
        )
    ]
    prior = base.outcome(center, None, is_prior=True)
    prior["arms"]["fitted_c"].update(status="unavailable", reason="no_signal_prior_control")
    return dict(zip(METHODS, [shared, *controls, prior], strict=True)), dict(
        training_tracks=train.track_count,
        held_tracks=held.track_count,
        training_rows=len(train.observed),
        held_rows=len(held.observed),
        train_norads=list(train.norads),
        held_norads=list(held.norads),
    )


if __name__ == "__main__":
    import json
    import sys

    request = json.load(sys.stdin)
    values, support = infer(request["packet"], request["tile"])
    print(json.dumps(dict(results=values, support=support), allow_nan=False))
