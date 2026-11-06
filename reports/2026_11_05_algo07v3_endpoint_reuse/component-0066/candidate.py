def phase_shifted_states(bank, time_s, phase_seconds):
    phases = np.asarray(phase_seconds, float)
    times = np.asarray(time_s, float)
    count = np.asarray(bank["position_km"]).shape[0]
    scalar_phase = phases.ndim == 0 and count > 0
    if phases.ndim == 0:
        phases = np.full(count, float(phases))
    if phases.shape != (count,) or not np.isfinite(phases).all():
        raise ValueError("finite scalar or one orbit phase per satellite required")
    # The common interpolator supplies geometry validation even for an empty
    # request. Per-satellite phases then use the same linear interpolation rule.
    if not isinstance(bank, FrozenOrbitBank):
        interpolate_states(bank, np.array([], float))
    if times.ndim != 1 or not np.isfinite(times).all():
        raise ValueError("finite one-dimensional observation times required")
    knots = np.asarray(bank["time_s"], float)
    query_phases = phases[:1] if scalar_phase else phases
    requested = times[None, :] + query_phases[:, None]
    if np.any(requested < knots[0]) or np.any(requested > knots[-1]):
        raise ValueError("orbit phase interpolation never extrapolates")
    index = np.clip(np.searchsorted(knots, requested, side="right") - 1, 0, len(knots) - 2)
    fraction = (requested - knots[index]) / (knots[index + 1] - knots[index])
    rows = np.arange(count)[:, None]
    states = []
    angle = EARTH_ROTATION_RAD_S * phases
    cosine, sine = np.cos(angle)[:, None], np.sin(angle)[:, None]
    for name in ("position_km", "velocity_km_s"):
        source = np.asarray(bank[name], float)
        lower = source[rows, index]
        values = lower + fraction[:, :, None] * (source[rows, index + 1] - lower)
        del lower
        x, y = values[:, :, 0].copy(), values[:, :, 1].copy()
        values[:, :, 0] = cosine * x - sine * y
        values[:, :, 1] = sine * x + cosine * y
        states.append(values)
    return tuple(states)
