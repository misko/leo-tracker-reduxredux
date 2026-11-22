"""Score model sensitivity to receiver height on one saved orbital snapshot."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import parse_element_sets


def measure(snapshot):
    raw = snapshot.read_bytes()
    stamp, digest = snapshot.stem.split("-", 1)
    if sha256(raw).hexdigest() != digest:
        raise ValueError("Saved orbital snapshot differs from its digest")
    catalogue = parse_element_sets(raw.decode())
    times = np.arange(0., 301., 15.)
    position, velocity, usable = ecef_states(catalogue, int(stamp), times)
    rows = []
    for site in ((15., 75.), (-25., -65.), (65., 120.)):
        rotation = ecef_to_enu_matrix(*site)
        def projection(height):
            observer = geodetic_to_ecef_km(*site, height)
            _, elevation, _, rate = look_angles(position, velocity, observer, rotation)
            return elevation, -11.5e9 * rate / 299792.458

        elevation, base = projection(0.)
        selected = usable & (elevation.min(axis=1) >= 10)
        if not np.any(selected):
            raise ValueError("No satellites stayed above ten degrees for the full interval")
        centered_time = times - times.mean()
        for height in (100., 1000., 2000.):
            _, other = projection(height)
            delta = other[selected] - base[selected]
            centered = delta - delta.mean(axis=1, keepdims=True)
            slope = (centered @ centered_time) / (centered_time @ centered_time)
            curved = centered - slope[:, None] * centered_time
            terms = {"raw": delta, "after_constant": centered, "after_affine": curved}
            rows.append(dict(latitude=site[0], longitude=site[1], height_m=height,
                             satellites=int(selected.sum()), median_track_rms_hz={
                                 name: float(np.median(np.sqrt(np.mean(values**2, axis=1))))
                                 for name, values in terms.items()
                             }))
    return dict(snapshot=snapshot.name, sample_times_s=times.tolist(), rf_hz=11.5e9, results=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    print(json.dumps(measure(parser.parse_args().snapshot), indent=2, allow_nan=False))
