"""Whole-cohort unblinding for separately versioned topology confirmation."""
import argparse
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
LOCATION=HERE.parent/'2026_09_27_roof_location_geometry'
DIRECTION=HERE.parent/'2026_09_27_roof_direction_subset'
sys.path.insert(0,str(LOCATION))
from score_distances import distance_km
from score_confirmation import digest, summarize, verify_result
from guided_selection import select_rx_guided_doppler


def main(deduplicate=False):
    prefix='topology-dedup-search-' if deduplicate else 'topology-search-'
    manifest_bytes=(HERE/'manifest.json').read_bytes()
    inventory_bytes=(HERE/'inventory.json').read_bytes()
    inventory=json.loads(inventory_bytes)
    if len(inventory)!=4 or len({x['session_id'] for x in inventory})!=4:
        raise ValueError('expected the same four unique frozen recordings')
    completed={};hashes={};pending=[]
    for entry in inventory:
        sid=entry['session_id'];path=HERE/f'{prefix}{sid}.json'
        if not path.exists():pending.append(sid);continue
        payload=path.read_bytes();result=json.loads(payload)
        if not result.get('finished'):pending.append(sid);continue
        completed[sid]=result;hashes[sid]=digest(payload)
    if pending:
        print(json.dumps(dict(complete=False,pending_sessions=pending,status='No reference errors exposed before all four amended searches complete.')))
        return
    expected=dict(manifest_sha256=digest(manifest_bytes),inventory_sha256=digest(inventory_bytes),
        frequency_parameters_sha256=digest((LOCATION/'topology_frequency_parameters.json').read_bytes()),
        calibration_sha256=digest((HERE/'topology_calibration.json').read_bytes()),
        pairing_summary_sha256=digest((DIRECTION/'pairing_summary.json').read_bytes()),
        topology_audit_sha256=digest((HERE/'audit_source_topology.json').read_bytes()),
        amendment_sha256=digest((HERE/'AMENDMENT_SOURCE_TOPOLOGY.md').read_bytes()),
        secondary_protocol_sha256=digest((HERE/'SECONDARY_PROTOCOL.md').read_bytes()))
    for entry in inventory:
        result=completed[entry['session_id']]
        verify_result(result,entry,expected)
        if result['protocol']['deduplicate_reception']!=deduplicate:
            raise ValueError('dependence-sensitivity arm mismatch')
        if result['code_sha256']['guided_selection.py']!=digest((HERE/'guided_selection.py').read_bytes()):
            raise ValueError('secondary selection implementation changed')
        for branch in result['branches'].values():
            if select_rx_guided_doppler(branch)!=branch['geometry_guided_doppler']:
                raise ValueError('stored secondary selection disagrees with its exact arm inventory')
    manifest=json.loads(manifest_bytes)
    if [x['pose']['session_id'] for x in manifest['sessions']]!=[x['session_id'] for x in inventory]:
        raise ValueError('reference manifest order differs from frozen inventory')
    rows=[]
    for item in manifest['sessions']:
        sid=item['pose']['session_id'];pose=item['pose']['pose_authority']
        truth=(pose['latitude_deg'],pose['longitude_deg'])
        def error(point):return distance_km((point['latitude_deg'],point['longitude_deg']),truth)
        for prior,branch in completed[sid]['branches'].items():
            d=branch['arms']['D'];j=branch['arms']['D_plus_geometry'];guided=branch['geometry_guided_doppler']['selected']
            de,je,ge=error(d['selected']),error(j['selected']),error(guided)
            rows.append(dict(session_id=sid,prior=prior,doppler_error_km=de,geometry_error_km=je,
                change_km=je-de,geometry_guided_doppler_error_km=ge,guided_change_km=ge-de,
                coordinates={name:[point['latitude_deg'],point['longitude_deg']] for name,point in
                    [('D',d['selected']),('D_plus_geometry',j['selected']),('geometry_guided_doppler',guided)]},
                doppler_stop=d['stop_reason'],geometry_stop=j['stop_reason'],
                removed_track_ids=completed[sid]['topology_receipt']['removed_track_ids'],
                common_inventory_errors_km={arm:error(point) for arm,point in branch['common_inventory_best'].items()}))
    guided_rows=[dict(row,geometry_error_km=row['geometry_guided_doppler_error_km'],change_km=row['guided_change_km']) for row in rows]
    out=dict(complete=True,variant='topology-dedup' if deduplicate else 'topology',rows=rows,
        primary_aggregate=summarize(rows),secondary_guidance_aggregate=summarize(guided_rows),
        search_artifact_sha256=hashes,frozen_inputs=expected,
        scope='Separately amended outcome-blind four-recording confirmation; reference is operator metadata, not surveyed GPS. Both arms160 evaluations; secondary D selection strictly inside J arm inventory. Finite-budget, limited-cohort evidence; composite dependence requires its separate sensitivity.')
    filename='topology_dedup_distance_results.json' if deduplicate else 'topology_distance_results.json'
    (HERE/filename).write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--deduplicate-reception',action='store_true')
    main(parser.parse_args().deduplicate_reception)
