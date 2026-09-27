"""Score frozen causal-element fits against the separate roof reference."""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    pose_path=REPORTS/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text())
    def error(best):
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    rows=[];hashes={}
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if not path.exists():continue
        result=json.loads(path.read_text())
        if not result['complete']:continue
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        hashes[path.name]=digest(path)
        base=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
        rows.append(dict(session_id=session,rate_msps=result['rate_hz']/1e6,inference_reused=result['inference_reused'],
            baseline_error_m=error(base['best']),fresh_error_m=error(result['best']),
            held_gain=result['exact_held']-base['exact_held'],train_gain=result['exact_train']-base['exact_train'],
            success=result['best']['success'],bound_hit=result['best']['bound_hit'],
            minimum_anchor_top8_mass=result['minimum_anchor_top8_mass']))
    summary=dict(completed=len(rows),expected=len(protocol['sessions']),pending=len(protocol['sessions'])-len(rows),
        refitted=sum(not r['inference_reused'] for r in rows),reused=sum(r['inference_reused'] for r in rows),
        baseline_sub_km=sum(r['baseline_error_m']<1000 for r in rows),fresh_sub_km=sum(r['fresh_error_m']<1000 for r in rows),
        baseline_median_m=statistics.median(r['baseline_error_m'] for r in rows) if rows else None,
        fresh_median_m=statistics.median(r['fresh_error_m'] for r in rows) if rows else None,
        fresh_mean_m=statistics.mean(r['fresh_error_m'] for r in rows) if rows else None,
        fresh_max_m=max((r['fresh_error_m'] for r in rows),default=None),
        selected_optimizer_warnings=sum(not r['success'] for r in rows),boundary_hits=sum(r['bound_hit'] for r in rows),
        truth_sha256=digest(pose_path),result_sha256=hashes,results=rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'errors.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['session_id']);writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['results','result_sha256']},indent=2))
    for row in rows:
        if not row['inference_reused']:print(json.dumps(row))


if __name__=='__main__':main()
