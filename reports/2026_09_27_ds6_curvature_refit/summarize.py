"""Score completed, source-bound outputs against the separate operator reference."""
import csv
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    pose_path=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json'
    pose=json.loads(pose_path.read_text());rows=[];files={}
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if not path.exists():continue
        result=json.loads(path.read_text())
        if not result['complete']:continue
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        files[path.name]=digest(path);arms={}
        for order,arm in result['arms'].items():
            best=arm['best']
            a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
            error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
            arms[order]=dict(error_m=error,success=best['success'],bound_hit=best['bound_hit'],held=arm['exact_held'])
        rows.append(dict(session_id=session,rate_msps=result['rate_hz']/1e6,arms=arms,
            quadratic_vs_linear_held_gain=arms['2']['held']-arms['1']['held'],
            quadratic_vs_linear_error_change_m=arms['2']['error_m']-arms['1']['error_m']))
    summary=dict(completed=len(rows),expected=len(protocol['sessions']),
        completed_development=sum(r['session_id'] in protocol['development_sessions'] for r in rows),
        truth_sha256=digest(pose_path),result_sha256=files,results=rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'errors.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['scan_id','MS/s','constant_error_m','linear_error_m','quadratic_error_m','quadratic_minus_linear_held_log_score'])
        for r in rows:writer.writerow([r['session_id'],r['rate_msps'],*[r['arms'][str(i)]['error_m'] for i in range(3)],r['quadratic_vs_linear_held_gain']])
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
