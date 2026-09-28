"""Report matched search-policy and geometry comparisons separately."""
import json
from pathlib import Path
from score_confirmation import digest, distance_km
from guided_selection import select_rx_guided_doppler

HERE = Path(__file__).resolve().parent


def verify_budget(arm):
    points = [(t['east_km'], t['north_km']) for t in arm['trace'] if t['event']=='evaluate']
    if arm['evaluated_points'] != 160 or len(points) != 160 or len(set(points)) != 160:
        raise ValueError('each arm must evaluate exactly160 unique points')


def main():
    inventory_bytes = (HERE/'inventory.json').read_bytes()
    inventory = json.loads(inventory_bytes)
    if len(inventory)!=4 or len({e['session_id'] for e in inventory})!=4:
        raise ValueError('four unique recordings required')
    runs = {}; hashes = {}
    for entry in inventory:
        sid = entry['session_id']; path = HERE/f'balanced-development-{sid}.json'
        if not path.exists() or not json.loads(path.read_text()).get('finished'):
            print('PENDING: all four development searches must complete'); return
        payload = path.read_bytes(); run = json.loads(payload)
        assert run['session_id']==sid and run['inventory_sha256']==digest(inventory_bytes)
        assert run['manifest_sha256']==digest((HERE/'manifest.json').read_bytes())
        assert run['original_search_sha256']==digest((HERE/f'topology-search-{sid}.json').read_bytes())
        assert set(run['branches'])=={'sacramento','reno'}
        for path, expected in run['code_sha256'].items():
            assert digest(Path(path).read_bytes())==expected
        for branch in run['branches'].values():
            assert set(branch['arms'])=={'D','D_plus_geometry'}
            for arm in branch['arms'].values(): verify_budget(arm)
            assert select_rx_guided_doppler(branch)==branch['geometry_guided_doppler']
        runs[sid]=run; hashes[sid]=digest(payload)
    baseline=json.loads((HERE/'topology_distance_results.json').read_text())
    baseline_rows={(r['session_id'],r['prior']):r for r in baseline['rows']}
    manifest=json.loads((HERE/'manifest.json').read_text())
    rows=[]
    for item in manifest['sessions']:
        sid=item['pose']['session_id']; pose=item['pose']['pose_authority']
        truth=(pose['latitude_deg'],pose['longitude_deg'])
        def error(point): return distance_km((point['latitude_deg'],point['longitude_deg']),truth)
        for prior,branch in runs[sid]['branches'].items():
            old=baseline_rows[sid,prior]
            d=error(branch['arms']['D']['selected'])
            j=error(branch['arms']['D_plus_geometry']['selected'])
            g=error(branch['geometry_guided_doppler']['selected'])
            rows.append(dict(session_id=sid,prior=prior,original_d_km=old['doppler_error_km'],
                original_joint_km=old['geometry_error_km'],balanced_d_km=d,balanced_joint_km=j,
                balanced_guided_d_km=g,search_change_d_km=d-old['doppler_error_km'],
                search_change_joint_km=j-old['geometry_error_km'],geometry_change_balanced_km=j-d))
    output=dict(complete=True,rows=rows,search_artifact_sha256=hashes,
        scope='Post-unblinding development only. Matched160-point independent-prior searches. Operator reference, not surveyed truth. Search improvement is distinct from RX geometry improvement.')
    (HERE/'balanced_development_distances.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))


if __name__=='__main__': main()
