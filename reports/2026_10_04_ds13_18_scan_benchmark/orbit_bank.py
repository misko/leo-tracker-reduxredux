"""Bounded catalogue-wide ephemeris export; selection independent of GLRT fit."""
import argparse
import inspect
import json
import math
import time
from pathlib import Path

from cohort import ROOF, digest


def observer_ecef(latitude, longitude, altitude_km=0.):
    latitude, longitude = map(math.radians, (latitude, longitude))
    semi_major, eccentricity2 = 6378.137, 6.6943799901413165e-3
    normal = semi_major/math.sqrt(1-eccentricity2*math.sin(latitude)**2)
    return [(normal+altitude_km)*math.cos(latitude)*math.cos(longitude),
            (normal+altitude_km)*math.cos(latitude)*math.sin(longitude),
            (normal*(1-eccentricity2)+altitude_km)*math.sin(latitude)]


def build(observations, *, maximum_seconds=180.):
    import numpy as np
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    started = time.monotonic()
    raw = observations.read_bytes()
    data = json.loads(raw)
    out = observations.parent/'orbit-bank'
    signature = dict(observations_sha256=digest(raw), implementation_sha256=digest(Path(__file__).read_bytes()),
                     propagation_sha256=digest(Path(inspect.getfile(propagate_candidate_states)).read_bytes()),
                     tle=data['tle'], roof_lat_lon=ROOF)
    receipt_path = out/'receipt.json'
    if receipt_path.exists():
        saved = json.loads(receipt_path.read_text())
        if saved['signature'] != signature or saved['arrays_sha256'] != digest((out/'states.npz').read_bytes()):
            raise ValueError('orbit bank resume digest mismatch')
        return saved
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshot = archive.select_latest_before(data['origin_utc_ns'])
    if snapshot.digest != data['tle']['sha256']:
        raise ValueError('archived TLE selection changed after export')
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    end = max(300., max(r['support_end_s'] for r in data['records']))
    nodes = np.arange(-21., math.ceil(end+21.)+.25, .25)
    observer = np.asarray(observer_ecef(*ROOF))
    latitude, longitude = np.radians(ROOF)
    up = np.array([np.cos(latitude)*np.cos(longitude), np.cos(latitude)*np.sin(longitude), np.sin(latitude)])
    indices = list(range(len(catalogue.satellite_numbers)))
    states, invalid, visible, maxima = [], [], [], []
    for begin in range(0, len(indices), 128):
        if time.monotonic()-started > maximum_seconds:
            raise TimeoutError('bounded orbit-bank build exceeded deadline')
        batch = indices[begin:begin+128]
        position, velocity, valid = propagate_candidate_states(catalogue, batch, data['origin_utc_ns'], nodes, np.array([0.]))
        invalid.extend(sorted(set(batch)-set(valid)))
        position, velocity = position[:, 0], velocity[:, 0]
        delta = position-observer
        height = np.sum(delta*up, axis=-1)/np.linalg.norm(delta, axis=-1)
        maximum = np.max(height, axis=1)
        # Include a one-degree horizon margin for the 2 km search disk and
        # discrete ephemeris grid. Exact visibility is evaluated at each fit site.
        keep = maximum >= math.sin(math.radians(-1.))
        for index, p, v, h in zip(valid[keep], position[keep], velocity[keep], maximum[keep]):
            visible.append(int(index)); states.append((p.copy(), v.copy())); maxima.append(float(h))
    if not visible:
        raise ValueError('empty near-visible candidate bank')
    out.mkdir(exist_ok=True)
    target = out/'states.npz'
    if target.exists():
        raise FileExistsError('unsealed states.npz exists; inspect before replacing')
    with target.open('xb') as stream:
        np.savez_compressed(stream, nodes_s=nodes, numbers=np.asarray(catalogue.satellite_numbers)[visible],
                            position_km=np.stack([s[0] for s in states]), velocity_km_s=np.stack([s[1] for s in states]),
                            maximum_elevation_sine=np.asarray(maxima), observer_ecef_km=observer)
    result = dict(signature=signature, status='complete', catalogue_count=len(indices), retained_count=len(visible),
                  invalid_propagation_numbers=[int(catalogue.satellite_numbers[i]) for i in invalid],
                  retained_numbers=[int(catalogue.satellite_numbers[i]) for i in visible],
                  nodes_count=len(nodes), arrays_sha256=digest(target.read_bytes()), elapsed_s=time.monotonic()-started,
                  units='ECEF km and km/s; receive seconds from capture origin; WGS84 observer h=0',
                  screen='All non-debris archived catalogue entries; quarter-second grid expanded by 21 s; maximum roof elevation >= -1 degree. No GLRT score or assigned-satellite whitelist. Final visibility must be checked at fitted site and shifted epoch.',
                  propagation_policy='Installed public propagator rejects nonfinite/SGP4-error states and geocentric radius <=6498.137 km; rejected catalogue IDs explicitly listed.')
    with receipt_path.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=Path)
    parser.add_argument('--maximum-seconds', type=float, default=180.)
    args = parser.parse_args()
    result = build(args.observations, maximum_seconds=args.maximum_seconds)
    print(json.dumps({k:result[k] for k in ('status','catalogue_count','retained_count','nodes_count','elapsed_s')}))
