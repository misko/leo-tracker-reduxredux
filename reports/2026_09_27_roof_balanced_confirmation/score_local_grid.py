"""Whole-cohort posthoc local-ranking report, separate from grid evaluation."""
import argparse
import json
from pathlib import Path
import run_balanced_confirmation as runner
from local_grid_reporting import compare
from run_local_grid import local_grid

HERE=Path(__file__).resolve().parent


def main(deduplicate=False):
    entries,contract=runner.inputs();suffix='-dedup' if deduplicate else ''
    runs={};hashes={};sources={}
    for entry in entries:
        sid=entry['session_id'];path=HERE/f'local-grid{suffix}-{sid}.json'
        if not path.exists() or not json.loads(path.read_text()).get('finished'):
            print('PENDING: all four local grids required');return
        payload=path.read_bytes();run=json.loads(payload)
        if run['session_id']!=sid or run['deduplicate_reception']!=deduplicate:
            raise ValueError('local-grid identity mismatch')
        bindings={'contract_sha256':'contract.json','source_search_sha256':f'search-{sid}.json',
            'distance_results_sha256':'distance_results.json','local_grid_protocol_sha256':'LOCAL_GRID_PROTOCOL.md',
            'topology_audit_sha256':'audit_source_topology.json'}
        for key,name in bindings.items():
            if run[key]!=runner.base.digest((HERE/name).read_bytes()):raise ValueError('changed binding: '+key)
        for name,expected in run['code_sha256'].items():
            candidates=[root/name for root in (HERE,runner.PREVIOUS,runner.LOCATION)]
            path=next(p for p in candidates if p.exists())
            if runner.base.digest(path.read_bytes())!=expected:raise ValueError('changed code: '+name)
        source=json.loads((HERE/f'search-{sid}.json').read_text())
        if set(run['branches'])!={'sacramento','reno'}:raise ValueError('missing local prior')
        for prior,b in run['branches'].items():
            seed=source['branches'][prior]['arms']['D']['selected']
            expected=set(local_grid(seed['east_km'],seed['north_km'],b['radius_km']))
            actual={(p['east_km'],p['north_km']) for p in b['point_components']}
            if expected!=actual or b['grid_count']!=len(expected):raise ValueError('grid inventory changed')
        runs[sid]=run;sources[sid]=source;hashes[sid]=runner.base.digest(payload)
    manifest=json.loads((HERE/'manifest.json').read_text());rows=[]
    for item in manifest['sessions']:
        sid=item['pose']['session_id'];pose=item['pose']['pose_authority'];truth=(pose['latitude_deg'],pose['longitude_deg'])
        for prior,b in runs[sid]['branches'].items():
            seed=sources[sid]['branches'][prior]['arms']['D']['selected']
            result=compare(b['point_components'],seed,truth)
            for arm,p in result['selected'].items():
                stored=b['arms'][arm]['selected']
                if (p['east_km'],p['north_km'])!=(stored['east_km'],stored['north_km']):raise ValueError('selected point mismatch')
            rows.append(dict(session_id=sid,prior=prior,boundary_flags=b['boundary_flags'],**result))
    output=dict(complete=True,deduplicate_reception=deduplicate,rows=rows,artifact_sha256=hashes,
        scope='Posthoc local-ranking diagnostic on identical grids; no fresh-validation, cost-parity-to160-point-search, or calibrated-resolution claim.')
    runner.base.atomic(HERE/f'local-grid{suffix}-distances.json',output)
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--deduplicate-reception',action='store_true')
    main(parser.parse_args().deduplicate_reception)
