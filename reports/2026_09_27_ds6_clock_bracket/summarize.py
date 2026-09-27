"""Post-fit geographic assessment; never imported by the fitting program."""
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def distance(lat,lon,ref):
    a,b,c,d=map(math.radians,[lat,lon,ref['latitude_deg'],ref['longitude_deg']])
    return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))

def main():
    p=json.loads((HERE/'protocol.json').read_text())
    truth=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json';ref=json.loads(truth.read_text());rows=[]
    for session in p['sessions']:
        r=json.loads((HERE/f'{session}.json').read_text());assert r['complete']
        baseline=json.loads((HERE.parent/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text())
        rows.append(dict(session_id=session,baseline_error_m=distance(baseline['best']['latitude'],baseline['best']['longitude'],ref),
            bracket_error_m=distance(r['best']['latitude'],r['best']['longitude'],ref),held_gain=r['held_gain'],
            timing_bound_hit=r['best']['timing_bound_hit'],success=r['best']['success']))
    s=dict(results=rows,truth_sha256=digest(truth),result_sha256={f'{s}.json':digest(HERE/f'{s}.json') for s in p['sessions']})
    (HERE/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s,indent=2))
if __name__=='__main__':main()
