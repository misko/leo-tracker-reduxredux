"""Post-fit DS6 geographic assessment, with incomplete membership explicit."""
import json
import hashlib
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    pose_path=REPORTS/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text());rows=[];hashes={}
    def error(best):
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if not path.exists():continue
        r=json.loads(path.read_text());assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        old=json.loads((REPORTS/'2026_09_27_ds6_element_freshness'/f'{session}.json').read_text());hashes[path.name]=digest(path)
        rows.append(dict(session_id=session,rate_msps=old['rate_hz']/1e6,baseline_error_m=error(old['best']),stationary_error_m=error(r['best']),
            exact_train_gain=r['exact_train']-old['exact_train'],exact_held_gain=r['exact_held']-old['exact_held'],
            success=r['best']['success'],bound_hit=r['best']['bound_hit'],maximum_gradient_difference=r['maximum_gradient_difference']))
    summary=dict(completed=len(rows),expected=len(protocol['sessions']),pending=len(protocol['sessions'])-len(rows),
        truth_sha256=digest(pose_path),result_sha256=hashes,results=rows)
    if rows:
        summary['metrics']=dict(sub_km=sum(r['stationary_error_m']<1000 for r in rows),
            baseline_sub_km=sum(r['baseline_error_m']<1000 for r in rows),
            mean_m=statistics.mean(r['stationary_error_m'] for r in rows),median_m=statistics.median(r['stationary_error_m'] for r in rows),
            max_m=max(r['stationary_error_m'] for r in rows),warnings=sum(not r['success'] for r in rows),
            boundary_hits=sum(r['bound_hit'] for r in rows),held_gain=sum(r['exact_held_gain'] for r in rows))
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='result_sha256'},indent=2))

if __name__=='__main__':main()
