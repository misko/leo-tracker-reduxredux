"""Stream comparison against direct causal SGP4 at TRAIN epochs."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from regular_cache import interpolate_states

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads((args.cache_dir / 'cache_receipt.json').read_text())
    cache_path = args.cache_dir / 'state_cache.npz'
    if receipt['bindings']['state_cache'] != digest(cache_path):
        raise ValueError('cache hash mismatch')
    store = ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            receipt['session_id'], inputs=store, archive=TleArchiveReader(Path('/var/lib/leo/tle'))
        )
    finally:
        store.close()
    for key in ('evidence_sha256', 'snapshot_digest', 'start_utc_ns'):
        if getattr(prepared, key) != receipt['prepared_evidence'][key]:
            raise ValueError(f'prepared authority changed: {key}')
    query = np.unique(np.concatenate([
        np.rint(track.times_s[track.training_mask] * 1e9).astype(np.int64)
        for track in prepared.tracks
    ]))
    with np.load(cache_path) as loaded:
        cache = {key: loaded[key] for key in loaded.files}
    ids = cache['candidate_id']
    lookup = {int(n): index for index, n in enumerate(prepared.catalogue.satellite_numbers)}
    sites = {}
    for name, lat, lon, east, north in [
        ('sac_center', 38.5816, -121.4944, 0, 0),
        ('reno_center', 39.5296, -119.8138, 0, 0),
        ('sac_e50_n50', 38.5816, -121.4944, 50, 50),
        ('reno_e100_n100', 39.5296, -119.8138, 100, 100),
    ]:
        sites[name] = {
            'latitude_deg': lat + north / 111.32,
            'longitude_deg': lon + east / (111.32 * np.cos(np.deg2rad(lat))),
            'sse': 0.0, 'count': 0, 'max_abs_hz': 0.0, 'raw_max_abs_hz': 0.0,
        }
    for begin in range(0, len(ids), 8):
        end = min(begin + 8, len(ids))
        indices = np.asarray([lookup[int(n)] for n in ids[begin:end]])
        exact_p, exact_v, valid = propagate_candidate_states(
            prepared.catalogue, indices, prepared.start_utc_ns, query / 1e9, np.asarray([0.0])
        )
        if not np.array_equal(indices, valid):
            raise ValueError('direct propagation lost or reordered a cached candidate')
        block = {key: value if key == 'receive_plus_tau_offset_ns' else value[begin:end]
                 for key, value in cache.items()}
        interp_p, interp_v = interpolate_states(block, query)
        for site in sites.values():
            receiver = geodetic_to_ecef_km(site['latitude_deg'], site['longitude_deg'], 0)

            def doppler(position, velocity, origin=receiver):
                delta = position - origin
                return -11.2e9 / 299792.458 * np.sum(delta * velocity, axis=-1) / np.linalg.norm(
                    delta, axis=-1
                )

            error = doppler(interp_p, interp_v) - doppler(exact_p[:, 0], exact_v[:, 0])
            site['raw_max_abs_hz'] = max(site['raw_max_abs_hz'], float(np.max(np.abs(error))))
            error -= error.mean(axis=1, keepdims=True)
            site['sse'] += float(np.sum(error**2))
            site['count'] += error.size
            site['max_abs_hz'] = max(site['max_abs_hz'], float(np.max(np.abs(error))))
    for site in sites.values():
        site['cfo_removed_rms_hz'] = float(np.sqrt(site.pop('sse') / site['count']))
    result = {
        'reference': 'Direct SGP4 from same causal catalogue; no interpolation oracle',
        'scope': 'All compact candidates, unique zero-tau TRAIN epochs, four fixed sites',
        'cfo_removal': 'One constant per candidate over all selected training epochs',
        'candidate_count': len(ids), 'training_epoch_count': len(query), 'sites': sites,
        'acceptance_max_hz': 1.0,
        'accepted': max(site['max_abs_hz'] for site in sites.values()) < 1.0,
        'bindings': {'cache': digest(cache_path),
                     'receipt': digest(args.cache_dir / 'cache_receipt.json'),
                     'benchmark': digest(__file__),
                     'adapter': digest(Path(__file__).with_name('regular_cache.py'))},
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
