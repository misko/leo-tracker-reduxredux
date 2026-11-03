import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
REFERENCE=[37.849056280893684,-122.48575489722863]


def distance(a,b):
    p,q=map(math.radians,a);r,s=map(math.radians,b)
    return 12742017.6*math.asin(math.sqrt(math.sin((r-p)/2)**2+math.cos(p)*math.cos(r)*math.sin((s-q)/2)**2))


if __name__=='__main__':
    plan=json.loads((HERE/'plan.json').read_text());plan_hash=hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    for name,h in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
    rows=[];hashes={}
    for unit in plan['sets']:
        ds=unit['dataset'];p=HERE/ds/'result.json';r=json.loads(p.read_text())
        assert r['plan_sha256']==plan_hash and r['sessions']==[s['session_id'] for s in unit['scans']]
        assert len(r['starts'])==6 and {(s['family'],s['initial'][0]) for s in r['starts']}=={(f,e) for f in ['cold','timing_grid'] for e in [-2,0,2]}
        selected=r['selected'];assert selected and selected['qualified']
        assert selected['score']==max(s['score'] for s in r['starts'] if s['qualified'])
        old_path=HERE.parent/f'2026_09_29_scan_budget/{ds}_n24_0.json'
        old=json.loads(old_path.read_text())
        rows.append(dict(dataset=ds,old_reference_distance_m=distance(old['selected']['estimate_deg'],REFERENCE),rank24_reference_distance_m=distance(selected['estimate_deg'],REFERENCE),position_shift_m=distance(old['selected']['estimate_deg'],selected['estimate_deg']),overlap_scans=unit['overlap_with_old_n24'],old_tracks=old['tracks'],new_tracks=r['tracks'],old_observations=old['observations'],new_observations=r['observations'],qualified_starts=sum(s['qualified'] for s in r['starts'])))
        for path in [p,old_path]:hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    ds10_path=HERE.parent/'2026_09_29_ds10_geographic/fits/N24_h0/result.json'
    ds10=json.loads(ds10_path.read_text());hashes[str(ds10_path)]=hashlib.sha256(ds10_path.read_bytes()).hexdigest()
    result=dict(rows=rows,ds10_rank24_reference_distance_m=distance(ds10['selected']['estimate_deg'],REFERENCE),configured_center_reference_distance_m=distance(plan['config']['geographic_prior_center_deg'],REFERENCE),plan_sha256=plan_hash,hashes=hashes)
    with (HERE/'summary.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))
