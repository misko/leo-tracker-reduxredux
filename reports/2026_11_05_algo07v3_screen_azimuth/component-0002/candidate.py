def _elevation_and_rate(position_ecef_km, velocity_ecef_km_s, observer_ecef_km, enu_matrix):
    """Retain the original look-angle math for the two outputs screening uses."""
    relative = position_ecef_km - observer_ecef_km
    east_north_up = relative @ enu_matrix.T
    slant_range = np.linalg.norm(relative, axis=-1)
    east = east_north_up[..., 0]
    north = east_north_up[..., 1]
    up = east_north_up[..., 2]
    elevation = np.rad2deg(np.arctan2(up, np.hypot(east, north)))
    with np.errstate(invalid="ignore", divide="ignore"):
        range_rate = np.where(
            slant_range > 0.0,
            np.einsum("...i,...i->...", relative, velocity_ecef_km_s) / slant_range,
            0.0,
        )
    return elevation, range_rate


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
        elevation, rate = _elevation_and_rate(position, velocity, observer, rotation)
        results.append((-rf_hz * rate / 299792.458, elevation))
    return results
