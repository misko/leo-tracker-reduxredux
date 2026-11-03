"""Audit provenance and receiver state census without target errors."""
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    inventory = json.loads((HERE.parent / 'acquisition-calibration-inventory.json').read_text())
    checked, donors = {}, []
    for index in range(23):
        path = HERE / f'donor-{index:02d}.json'
        doc = json.loads(path.read_text())
        for p, expected in doc['sources'].items():
            if p not in checked:
                checked[p] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
            assert checked[p] == expected, p
        family = inventory['families'][doc['family']]
        declared = next(r for r in family[doc['role']] if r['index'] == index)
        assert declared['session_id'] == doc['session_id']
        assert max(declared['capture_end_utc_ns'], declared['finalized_utc_ns']) < inventory['earliest_target_utc_ns']
        counts = np.zeros(5, int)
        keys = set()
        for lane in doc['lanes']:
            key = lane['norad'], lane['rf_hz']
            assert key not in keys
            keys.add(key)
            bits = np.array(lane['bits'])
            assert bits.shape == (len(lane['times_s']), 2)
            assert len(lane['los_enu']) == len(lane['training_mask']) == len(bits)
            assert np.isin(bits, [-1, 0, 1]).all()
            assert np.all(np.diff(lane['times_s']) >= 0)
            np.testing.assert_allclose(np.linalg.norm(lane['los_enu'], axis=1), 1., atol=1e-10)
            unknown = (bits < 0).any(axis=1)
            counts[4] += unknown.sum()
            state = bits[~unknown, 0] + 2 * bits[~unknown, 1]
            counts[:4] += np.bincount(state, minlength=4)
        donors.append(dict(index=index, family=doc['family'], role=doc['role'], physical_sources=len(keys), excluded_tracks=len(doc['excluded_tracks']), state_counts_00_10_01_11_unknown=counts.tolist(), replay_max=doc['original_bank_replay_maximum']))
    result = dict(donors=donors, checked_unique_sources=len(checked), passed=True, scope='source-specific inferred ownership states; 00 is no assigned detection, not verified physical absence', sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), *(HERE / f'donor-{i:02d}.json' for i in range(23))]})
    with (HERE / 'export-audit.json').open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(dict(passed=True, donors=len(donors), physical_sources=sum(d['physical_sources'] for d in donors), unique_sources=len(checked), maximum_replay=max(d['replay_max'] for d in donors))))


if __name__ == '__main__':
    main()
