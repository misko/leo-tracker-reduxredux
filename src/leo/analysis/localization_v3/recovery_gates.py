"""Original recovery gates replayed with one exact family orbit at a time."""

import numpy as np

from leo.analysis.localization_v3.event_position import track_events
from leo.analysis.localization_v3.feasible import noise_slacks, residual_slacks
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import profile, whitening


def gate_slacks(p, x, entries=(), *, family=None):
    """Every original profile, conditional, alias, elevation and support gate."""
    scan, c, state = (p.scan, p.calculate(x), p.state(x))
    frequency, elevation = p.conditional_frequency(x)
    slacks = {}
    owners = {}
    for row, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        if family is not None and row["candidate_index"] != family:
            continue
        t, active = (scan.tracks[i], p.keep[sl])
        if not active.any():
            continue
        times = t["times"][active]
        q = t["rf_hz"] / 11500000000.0
        observed = t["values"] - scan.hardware(t, state["beta"])
        observed -= q * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        terms = profile(observed[active], q * frequency[sl][active], *whitening(times))
        prefix = t["key"]
        values = dict(
            rms=1 - float(terms["rms"][0]) / 450,
            bias=1 - abs(float(terms["bias"][0])) / 3000,
            alias=0.5 - abs(int(terms["alias"][0]) - alias),
            elevation=float(elevation[sl][active].min()) / 10,
            **noise_slacks(terms["innovations"][0], times),
        )
        slacks.update({prefix + "/profile/" + k: v for k, v in values.items()})
        slacks.update(
            {
                prefix + "/conditional/" + k: v
                for k, v in residual_slacks(c["conditional_residual_hz"][sl][active], times).items()
            }
        )
        owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
    for j in p.supported:
        if j in owners:
            slacks["support/" + str(j)] = float(len(owners[j]) - 1.5)
    for entry, sl in zip(entries, getattr(p, "linear_slices", []), strict=True):
        if family is not None and entry["candidate_index"] != family:
            continue
        t = scan.tracks[entry["track_index"]]
        raw = c["linear_raw_prediction_residual_hz"][sl]
        terms = profile(
            raw, np.zeros(len(raw)), *scan.white[entry["track_index"]], bias_sigma=300.0
        )
        values = dict(
            rms=1 - float(terms["rms"][0]) / 450,
            bias=1 - abs(float(terms["bias"][0])) / 3000,
            alias=0.5 - abs(int(terms["alias"][0])),
            elevation=float(c["linear_elevation"][sl].min()) / 10,
            **noise_slacks(terms["innovations"][0], t["times"]),
        )
        slacks.update({entry["component"] + "/linear/" + k: v for k, v in values.items()})
    return slacks


def family_frequency(p, x, j, bank=None, corrected=True, times=None):
    scan = p.scan
    state = p.state(x)
    times = scan.times if times is None else np.asarray(times)
    source = scan.sky if bank is None else bank
    sub = dict(
        time_s=source["time_s"],
        position_km=source["position_km"][[j]],
        velocity_km_s=source["velocity_km_s"][[j]],
    )
    phase = np.asarray([state["phases"][j]])
    f, e = paired_phase_frequency(
        sub, times, np.zeros(len(times), int), phase, *p.scan.search_region.latlon(x)
    )
    if corrected and j in p.supported:
        local = p.labels.index(j)
        k = p.supported.index(j)
        begin = p.hardware.shape[1] + p.smooth.shape[1] + len(p.labels)
        modes = dict(
            time_s=p.mode_bank["time_s"],
            position_km=p.mode_bank["position_km"][3 * local : 3 * local + 3],
            velocity_km_s=p.mode_bank["velocity_km_s"][3 * local : 3 * local + 3],
        )
        derivative = paired_frequency_modes(
            sub, modes, times, np.zeros(len(times), int), phase, *p.scan.search_region.latlon(x)
        )
        f += derivative @ p.calculate(x)["coefficient"][begin + 3 * k : begin + 3 * k + 3]
    return (f, e)


def family_event_frequency(p, x, track, label):
    """Family event contribution in reference-frequency units for this track."""
    selected = [k for k, e in enumerate(getattr(p, "events", [])) if e["kind"] == "family"]
    if not selected:
        return np.zeros(len(track["times"]))
    design = track_events(track, label, [p.events[k] for k in selected])
    coefficient = p.calculate(x)["coefficient"][p.event_start + np.asarray(selected)]
    return design @ coefficient / (track["rf_hz"] / 11500000000.0)


def exact_gate_replay(p, z, entries, *, base_slacks=None):
    """Keep fitted coefficients; replace only the selected family's orbit.

    Optional base slacks must be freshly computed for this same fixed problem,
    position and entries before any orbit replacement. Only that family's
    residuals/elevations change; every other gate retains its original value.
    """
    c = p.calculate(z)
    j = p.explicit_phase_family
    frequency, elevation = p.conditional_frequency(z)
    frequency = frequency.copy()
    elevation = elevation.copy()
    conditional = c["conditional_residual_hz"].copy()
    linear = c["linear_raw_prediction_residual_hz"].copy() if entries else np.empty(0)
    le = c["linear_elevation"].copy() if entries else np.empty(0)
    maximum = 0.0
    for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        if row["candidate_index"] != j:
            continue
        t = p.scan.tracks[i]
        f, e = family_frequency(p, z, j, times=t["times"])
        f += family_event_frequency(p, z, t, j)
        difference = p.q[sl] * (f - frequency[sl])
        maximum = max(maximum, float(np.max(abs(difference))))
        conditional[sl] -= difference
        frequency[sl] = f
        elevation[sl] = e
    for entry, sl in zip(entries, getattr(p, "linear_slices", []), strict=True):
        if entry["candidate_index"] != j:
            continue
        view, *_ = linear_geometry(p, [entry])
        g = geometry_features(view, z, 0.0)
        t = p.scan.tracks[entry["track_index"]]
        begin = p.hardware.shape[1] + p.smooth.shape[1]
        stop = begin + len(p.labels) + 3 * len(p.supported)
        f, e = family_frequency(p, z, j, times=t["times"])
        approximate = (
            view.q * g["intercept"] + g["features"][:, begin:stop] @ c["coefficient"][begin:stop]
        )
        difference = view.q * f - approximate
        maximum = max(maximum, float(np.max(abs(difference))))
        linear[sl] -= difference
        le[sl] = e
    calculate = p.calculate
    conditional_frequency = p.conditional_frequency
    p.calculate = lambda _: dict(
        c,
        conditional_residual_hz=conditional,
        linear_raw_prediction_residual_hz=linear,
        linear_elevation=le,
    )
    p.conditional_frequency = lambda _: (frequency, elevation)
    try:
        if base_slacks is None:
            gates = gate_slacks(p, z, entries)
        else:
            gates = dict(base_slacks)
            gates.update(gate_slacks(p, z, entries, family=j))
    finally:
        p.calculate = calculate
        p.conditional_frequency = conditional_frequency
    witnesses = []
    for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        active = p.keep[sl]
        if row["candidate_index"] != j or not active.any():
            continue
        t = p.scan.tracks[i]
        residual = conditional[sl][active]
        witnesses.append(
            dict(
                component=t["key"],
                times_s=t["times"][active],
                residual_hz=residual,
                RMS_hz=float(np.sqrt(np.mean(residual**2))),
            )
        )
    return dict(
        all_gate_slacks=gates,
        minimum_slack=min(gates.values()),
        family_witnesses=witnesses,
        maximum_linearization_difference_hz=maximum,
        all_pass=min(gates.values()) >= 0,
    )
