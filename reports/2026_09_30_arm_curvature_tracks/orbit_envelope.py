"""Independent-recording TLE Doppler-curvature envelope; no target track labels."""
from pathlib import Path
import hashlib
import json
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_30_arm_location_prototype"


def visible_curvature(states, receiver, up, dt):
    if not np.isfinite(dt) or dt <= 0 or states.shape[-1] != 6 or states.shape[-2] < 3:
        raise ValueError("invalid orbit geometry")
    if not np.all(np.isfinite(states)):
        raise ValueError("nonfinite state")
    relative = states[..., :3] - np.asarray(receiver)
    distance = np.linalg.norm(relative, axis=-1)
    if np.any(distance <= 0):
        raise ValueError("zero slant range")
    doppler = -11_200_000_000 / 299_792.458 * np.sum(
        states[..., 3:] * relative, axis=-1) / distance
    visible = np.sum(relative * np.asarray(up), axis=-1) > 0
    eligible = visible[..., :-2] & visible[..., 1:-1] & visible[..., 2:]
    acceleration = np.diff(doppler, n=2, axis=-1) / dt**2
    return acceleration[eligible], distance[..., 1:-1][eligible]


def main():
    meta = json.loads((SOURCE / "inputs.json").read_text())
    path = SOURCE / "local/states.npy"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != meta["states_sha256"]:
        raise ValueError("orbit-state provenance mismatch")
    states = np.load(path, mmap_mode="r")
    rows = []
    all_values = []
    for site in meta["points"]:
        curvature, distance = visible_curvature(states, site["receiver"], site["up"],
                                                meta["knot_step_s"])
        values = np.abs(curvature)
        all_values.append(values)
        rows.append({"site": site["name"], "latitude_deg": site["latitude_deg"],
                     "longitude_deg": site["longitude_deg"], "visible_time_samples": len(values),
                     "minimum_visible_slant_range_km": float(distance.min()),
                     "absolute_curvature_hz_per_s2": {
                         str(q):float(np.percentile(values,q)) for q in (50,90,95,99,99.9,100)}})
    values = np.concatenate(all_values)
    result = {"schema":"leo-independent-orbit-curvature-envelope/v1",
              "calibration_session":meta["session_id"],
              "target_session_used":False, "snapshot_digest":meta["snapshot_digest"],
              "states_sha256":digest, "state_shape":list(states.shape),
              "carrier_hz":11200000000, "difference_step_s":meta["knot_step_s"],
              "maximum_observed_absolute_curvature_hz_per_s2":float(values.max()),
              "sites":rows,
              "scope":"Empirical envelope over this independent historical TLE catalogue, time interval and two sites; not a universal physical bound or an RF oscillator-drift bound."}
    (HERE / "orbit-envelope.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
