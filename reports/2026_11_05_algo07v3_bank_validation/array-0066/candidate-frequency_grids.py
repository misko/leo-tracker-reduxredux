def phase_frequency_grids(bank, time_s, positions, *, phase_seconds=0.0,
                         altitude_m=0.0, rf_hz=11.5e9):
    positions = tuple(positions)
    if not positions:
        raise ValueError("At least one receiver position required")
    for latitude, longitude in positions:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("geodetic coordinate outside domain")
    if not np.isfinite(altitude_m) or not np.isfinite(rf_hz) or rf_hz <= 0:
        raise ValueError("finite height and positive reference RF required")
    position, velocity = phase_shifted_states(bank, time_s, phase_seconds)
    results = []
    for latitude, longitude in positions:
        observer = geodetic_to_ecef_km(latitude, longitude, altitude_m)
        rotation = ecef_to_enu_matrix(latitude, longitude)
        _, elevation, _, rate = look_angles(position, velocity, observer, rotation)
        results.append((-rf_hz * rate / 299792.458, elevation))
    return results
