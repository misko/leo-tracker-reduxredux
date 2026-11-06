def _nomination_grids(bank, times, query, positions, *, phase_seconds):
    # Keep full-input validation: an omitted point must not hide a malformed
    # time or extrapolation. Delegate invalid cases to the original path.
    t = np.asarray(times, float)
    knots = np.asarray(bank['time_s'], float)
    shifted = t + phase_seconds
    if (t.ndim != 1 or not np.isfinite(t).all()
            or np.any(shifted < knots[0]) or np.any(shifted > knots[-1])):
        return phase_frequency_grids(bank, times, positions, phase_seconds=phase_seconds)
    return phase_frequency_grids(bank, t[query], positions, phase_seconds=phase_seconds)
