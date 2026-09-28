"""Read truth only after completed, immutable independent searches exist."""
import hashlib
import argparse
import json
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_27_roof_direction_subset'


def distance_km(a,b):
    la,lo,lb,ln=map(math.radians,(*a,*b))
    q=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((ln-lo)/2)**2
    return 2*6371.0088*math.asin(math.sqrt(min(1.,max(0.,q))))


def main(variant='original'):
    prefix={'original':'search-', 'measured':'measured-search-', 'robust':'robust-search-'}[variant]
    inventory=json.loads((SOURCE/'evaluation_inventory.json').read_text())
    sessions=[x['session_id'] for x in inventory if x['split']=='holdout']
    # Only the reporting process reads held-out roof coordinates.
    manifest=json.loads((SOURCE/'evaluation_manifest.json').read_text())
    truth={x['pose']['session_id']:(x['pose']['pose_authority']['latitude_deg'],x['pose']['pose_authority']['longitude_deg']) for x in manifest['sessions']}
    rows=[];pending=[];hashes={}
    for sid in sessions:
        path=HERE/f'{prefix}{sid}.json'
        if not path.exists():pending.append(sid);continue
        data=path.read_bytes();result=json.loads(data)
        if not result.get('finished'):pending.append(sid);continue
        hashes[sid]='sha256:'+hashlib.sha256(data).hexdigest()
        for prior,b in result['branches'].items():
            def error(p):return distance_km((p['latitude_deg'],p['longitude_deg']),truth[sid])
            d=b['arms']['D'];g=b['arms']['D_plus_geometry']
            base=error(d['selected']);geo=error(g['selected'])
            rows.append(dict(session_id=sid,prior=prior,truth_latitude_deg=truth[sid][0],truth_longitude_deg=truth[sid][1],
                doppler_error_km=base,geometry_error_km=geo,change_km=geo-base,
                doppler_coordinate=[d['selected']['latitude_deg'],d['selected']['longitude_deg']],
                geometry_coordinate=[g['selected']['latitude_deg'],g['selected']['longitude_deg']],
                doppler_budget_status=d['stop_reason'],geometry_budget_status=g['stop_reason'],
                common_inventory_errors_km={arm:error(p) for arm,p in b['common_inventory_best'].items()},
                common_inventory_points=len(b['point_components'])))
    aggregate={}
    for prior in ('sacramento','reno','all'):
        r=[x for x in rows if prior=='all' or x['prior']==prior]
        if not r:continue
        aggregate[prior]=dict(cases=len(r),improved=sum(x['change_km']<0 for x in r),
            doppler_median_km=float(np.median([x['doppler_error_km'] for x in r])),
            geometry_median_km=float(np.median([x['geometry_error_km'] for x in r])),
            doppler_mean_km=float(np.mean([x['doppler_error_km'] for x in r])),
            geometry_mean_km=float(np.mean([x['geometry_error_km'] for x in r])))
    cohort='Original frozen roof holdouts' if variant=='original' else 'Four roof development scans; not fresh confirmation data'
    out=dict(variant=variant,complete=not pending,pending_sessions=pending,rows=rows,aggregate=aggregate,search_artifact_sha256=hashes,
             scope=cohort+'. Paired independent-prior searches. Geographic errors relative to operator-supplied metadata coordinates; not population accuracy or surveyed precision.')
    filename='distance_results.json' if variant=='original' else f'{variant}_distance_results.json'
    (HERE/filename).write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',choices=('original','measured','robust'),default='original')
    main(parser.parse_args().variant)
