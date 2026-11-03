"""Verify and mirror experiment-owned orbit outputs into the local cache."""
import json
from pathlib import Path

import numpy as np
from regression_batch import digest


def verify_extension(raw, extended):
    if not np.array_equal(raw['satellite_ids'], extended['satellite_ids']):
        raise ValueError('extended catalogue changed')
    times = extended['knot_times_s']
    if np.any(np.diff(times) <= 0):
        raise ValueError('extended times are not increasing')
    start = int(np.searchsorted(times, raw['knot_times_s'][0]))
    stop = start+len(raw['knot_times_s'])
    if not np.array_equal(raw['knot_times_s'], times[start:stop]):
        raise ValueError('original time knots changed')
    for key in ['positions_ecef_km', 'velocities_ecef_km_s']:
        if not np.all(np.isfinite(extended[key])):
            raise ValueError('nonfinite extended states')
        if not np.array_equal(raw[key], extended[key][:, start:stop]):
            raise ValueError('original physical states changed')


def admit(unit_dir, prefix, cache):
    unit_dir, prefix, cache = map(Path, (unit_dir, prefix, cache))
    raw_path, meta_path = prefix.with_suffix('.npz'), prefix.with_suffix('.json')
    ext_path = prefix.with_name(prefix.name+'-extended.npz')
    ext_meta_path = prefix.with_name(prefix.name+'-extended.json')
    meta, ext = json.loads(meta_path.read_text()), json.loads(ext_meta_path.read_text())
    observations_path = unit_dir/'observations.json'
    observations = json.loads(observations_path.read_text())
    if digest(raw_path) != meta['state_sha256'] or digest(ext_path) != ext['state_sha256']:
        raise ValueError('state digest mismatch')
    if digest(observations_path) != meta['observation_sha256']:
        raise ValueError('observation digest mismatch')
    if (meta['session_id'] != observations['session_id'] or not meta['tle']['causal']
            or meta['tle']['sha256'] != observations['snapshot_sha256']):
        raise ValueError('identity or causal snapshot mismatch')
    if (ext['parent']['metadata_sha256'] != digest(meta_path)
            or ext['parent']['state_sha256'] != digest(raw_path)
            or ext['session_id'] != meta['session_id'] or ext['tle'] != meta['tle']):
        raise ValueError('extension provenance mismatch')
    with (np.load(raw_path, allow_pickle=False) as raw,
          np.load(ext_path, allow_pickle=False) as expanded):
        verify_extension(raw, expanded)
    destinations = [unit_dir/n for n in ['orbits.json', 'orbits-extended.json',
                                        'orbit-export-original.json',
                                        'extended-orbit-export-original.json']]
    if cache.exists() or any(p.exists() for p in destinations):
        raise FileExistsError('orbit admission would overwrite existing artifacts')
    cache.mkdir(parents=True, exist_ok=False)
    for source, target in [(raw_path, cache/'orbits.npz'),
                           (ext_path, cache/'orbits-extended.npz'),
                           (meta_path, destinations[2]), (ext_meta_path, destinations[3])]:
        with target.open('xb') as stream:
            stream.write(source.read_bytes())
        if digest(source) != digest(target):
            raise ValueError('copied bytes differ')
    meta['state_file'] = str((cache/'orbits.npz').resolve())
    meta['original_export_metadata_sha256'] = digest(meta_path)
    with destinations[0].open('x') as stream:
        json.dump(meta, stream, indent=2)
    ext['state_file'] = str((cache/'orbits-extended.npz').resolve())
    ext['parent'] = dict(metadata_path=str(destinations[0].resolve()),
                         metadata_sha256=digest(destinations[0]),
                         state_path=meta['state_file'], state_sha256=meta['state_sha256'])
    ext['original_export_metadata_sha256'] = digest(ext_meta_path)
    with destinations[1].open('x') as stream:
        json.dump(ext, stream, indent=2)
    return dict(unit=unit_dir.name, propagated=meta['propagated_count'],
                rejected=meta['propagation_rejected_count'],
                state_sha256=ext['state_sha256'], original_knots_preserved=True)
