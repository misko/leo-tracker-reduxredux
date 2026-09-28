"""Post-search reporting only: reference coordinates never enter search code."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
LOCATION = HERE.parent/'2026_09_27_roof_location_geometry'
DIRECTION = HERE.parent/'2026_09_27_roof_direction_subset'
sys.path.insert(0, str(LOCATION))
from score_distances import distance_km


def digest(payload):
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


def verify_result(result, entry, expected):
    if result['session_id'] != entry['session_id'] or set(result['branches']) != {'sacramento','reno'}:
        raise ValueError('completed search does not cover its independent priors')
    for key in ('cache_sha256','input_manifest_sha256','analysis_manifest_sha256'):
        if result[key] != entry[key]:
            raise ValueError('search input binding mismatch: '+key)
    for key, value in expected.items():
        if result[key] != value:
            raise ValueError('search frozen-model or cohort binding mismatch: '+key)
    for branch in result['branches'].values():
        if set(branch['arms']) != {'D','D_plus_geometry'}:
            raise ValueError('missing matched objective arm')
    if result['protocol']['budget_per_arm'] != 160:
        raise ValueError('confirmation search budget changed')


def summarize(rows):
    result = {}
    for prior in ('sacramento', 'reno', 'all'):
        group = [r for r in rows if prior == 'all' or r['prior'] == prior]
        if not group:
            continue
        result[prior] = dict(cases=len(group), improved=sum(r['change_km'] < -1e-9 for r in group),
            worsened=sum(r['change_km'] > 1e-9 for r in group),
            unchanged=sum(abs(r['change_km']) <= 1e-9 for r in group),
            doppler_mean_km=statistics.mean(r['doppler_error_km'] for r in group),
            geometry_mean_km=statistics.mean(r['geometry_error_km'] for r in group),
            doppler_median_km=statistics.median(r['doppler_error_km'] for r in group),
            geometry_median_km=statistics.median(r['geometry_error_km'] for r in group))
    return result


def main():
    manifest_bytes = (HERE/'manifest.json').read_bytes()
    inventory_bytes = (HERE/'inventory.json').read_bytes()
    inventory = json.loads(inventory_bytes)
    rows, pending, hashes, completed = [], [], {}, {}
    if len(inventory) != 4 or len({x['session_id'] for x in inventory}) != 4:
        raise ValueError('expected four unique frozen recordings')
    # Gate the entire cohort before parsing any reference pose or computing an error.
    for entry in inventory:
        sid = entry['session_id']
        path = HERE/f'confirmation-search-{sid}.json'
        if not path.exists():
            pending.append(sid)
            continue
        payload = path.read_bytes()
        result = json.loads(payload)
        if not result.get('finished'):
            pending.append(sid)
            continue
        hashes[sid] = digest(payload)
        completed[sid] = result
    if pending:
        print(json.dumps(dict(complete=False,pending_sessions=pending,
                              status='All confirmation distances withheld until every frozen scan finishes.')))
        return
    expected = dict(manifest_sha256=digest(manifest_bytes), inventory_sha256=digest(inventory_bytes),
        frequency_parameters_sha256=digest((LOCATION/'fixedpoint_parameters.json').read_bytes()),
        calibration_sha256=digest((LOCATION/'calibration.json').read_bytes()),
        pairing_summary_sha256=digest((DIRECTION/'pairing_summary.json').read_bytes()))
    for entry in inventory:
        verify_result(completed[entry['session_id']], entry, expected)
    manifest = json.loads(manifest_bytes)
    if [x['pose']['session_id'] for x in manifest['sessions']] != [x['session_id'] for x in inventory]:
        raise ValueError('manifest and inventory cohort order differ')
    for item in manifest['sessions']:
        sid = item['pose']['session_id']
        result = completed[sid]
        pose = item['pose']['pose_authority']
        truth = (pose['latitude_deg'], pose['longitude_deg'])
        def error(point):
            return distance_km((point['latitude_deg'], point['longitude_deg']), truth)
        for prior, branch in result['branches'].items():
            d = branch['arms']['D']
            g = branch['arms']['D_plus_geometry']
            de, ge = error(d['selected']), error(g['selected'])
            rows.append(dict(session_id=sid, prior=prior, doppler_error_km=de, geometry_error_km=ge,
                change_km=ge-de, doppler_coordinate=[d['selected']['latitude_deg'],d['selected']['longitude_deg']],
                geometry_coordinate=[g['selected']['latitude_deg'],g['selected']['longitude_deg']],
                doppler_stop=d['stop_reason'], geometry_stop=g['stop_reason'],
                common_inventory_errors_km={arm:error(p) for arm,p in branch['common_inventory_best'].items()}))
    out = dict(complete=not pending, pending_sessions=pending, rows=rows, aggregate=summarize(rows),
        search_artifact_sha256=hashes, manifest_sha256=digest(manifest_bytes),
        scope='Four disjoint readiness-selected roof recordings; independent-prior searches. Operator metadata reference, not surveyed GPS truth. Per-anchor composite reception evidence; finite search budgets. No population precision claim.')
    (HERE/'distance_results.json').write_text(json.dumps(out, indent=2, allow_nan=False)+'\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
