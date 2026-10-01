"""Read a verified causal extension, preserving the original spatial union."""
import json
from pathlib import Path
import numpy as np


def use_extended_orbits(scan):
    from common import digest
    from physics import OrbitBank
    path=Path.home()/f".cache/leo/research/fixed_height_greedy/orbits/{scan.unit_id}-orbits-extended.json"
    meta=json.loads(path.read_text())
    if meta['session_id']!=scan.session_id or not meta['tle']['causal']:
        raise ValueError('extended orbit identity or causality mismatch')
    for binding in (meta['observation'],meta['canonical_observation']):
        if digest(binding['path'])!=binding['sha256']:
            raise ValueError('extended orbit observation mismatch')
    for kind in ('metadata','state'):
        source=meta['parent'][kind+'_path']
        expected=meta['parent'][kind+'_sha256']
        # Parent arrays can be mirrored locally; their content binding is authoritative.
        matches = scan.inputs.get(source)==expected
        if kind == 'state':
            matches = expected in scan.inputs.values()
        if not matches:
            raise ValueError('extended orbit parent mismatch')
    state_path=Path(meta['state_file'])
    if digest(state_path)!=meta['state_sha256']:
        raise ValueError('extended state digest mismatch')
    with np.load(state_path,allow_pickle=False) as data:
        ids={int(identifier):i for i,identifier in enumerate(data['satellite_ids'])}
        ix=np.array([ids[identifier] for identifier in scan.bank.norad_ids])
        bank=OrbitBank(scan.bank.norad_ids,data['knot_times_s'],
                       data['positions_ecef_km'][ix],data['velocities_ecef_km_s'][ix])
    # Verify actual samples, not only a metadata assertion.
    start=int(np.searchsorted(bank.times_s,scan.bank.times_s[0]))
    end=start+len(scan.bank.times_s)
    if not (np.array_equal(bank.times_s[start:end],scan.bank.times_s)
            and np.array_equal(bank.positions_ecef_km[:,start:end],scan.bank.positions_ecef_km)
            and np.array_equal(bank.velocities_ecef_km_s[:,start:end],scan.bank.velocities_ecef_km_s)):
        raise ValueError('original selected orbit knots changed')
    scan.bank=bank
    scan.inputs.update({str(path):digest(path),str(state_path):meta['state_sha256']})
    return scan
