"""Post-fit geographic evaluation of both frozen likelihood arms."""
import hashlib
import json
import math
from pathlib import Path
HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def distance(b,r):
    a,o,c,d=map(math.radians,[b['latitude'],b['longitude'],r['latitude_deg'],r['longitude_deg']])
    return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((o-d)/2)**2))
def main():
    p=json.loads((HERE/'protocol.json').read_text());refpath=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json'
    ref=json.loads(refpath.read_text());rows=[]
    for s in p['sessions']:
        r=json.loads((HERE/f'{s}.json').read_text());assert r['complete']
        old=json.loads((HERE.parent/'2026_09_27_ds6_full_stationary'/f'{s}.json').read_text())
        rows.append(dict(session_id=s,baseline_error_m=distance(old['best'],ref),
            arms={name:dict(error_m=distance(a['best'],ref),exact_held=a['exact_held'],success=a['best']['success'],bound_hit=a['best']['bound_hit']) for name,a in r['arms'].items()},
            slope_vs_zero_held_gain=r['arms']['cross_subset_slope']['exact_held']-r['arms']['zero_slope']['exact_held']))
    summary=dict(results=rows,truth_sha256=digest(refpath),result_sha256={f'{s}.json':digest(HERE/f'{s}.json') for s in p['sessions']})
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
