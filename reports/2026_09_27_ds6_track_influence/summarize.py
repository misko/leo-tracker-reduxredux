"""Post-fit geographic and held-score assessment; no deletion policy selection."""
import csv
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    results=[json.loads((HERE/f'{s}.json').read_text()) for s in protocol['sessions']]
    assert all(r['complete'] for r in results)
    pose_path=REPORTS/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text())
    def error(best):
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    rows=[]
    for result in results:
        session=result['session_id'];base=json.loads((REPORTS/'2026_09_27_ds6_element_freshness'/f'{session}.json').read_text())
        tracks={t['track_id']:t for t in result['tracks']}
        for fit in result['fits']:
            t=tracks[fit['track_id']];predicted=t['predicted_shift'];half=t['half_step_predicted_shift']
            rows.append(dict(session_id=session,rate_msps=base['rate_hz']/1e6,track_id=fit['track_id'],selection=fit['selection'],
                baseline_error_m=error(base['best']),deleted_error_m=error(fit['best']),
                predicted_shift_m=None if predicted is None else 1000*math.hypot(*predicted[:2]),
                actual_shift_m=1000*math.hypot(*fit['actual_shift'][:2]),
                derivative_step_shift_difference_m=None if half is None or predicted is None else 1000*math.hypot(half[0]-predicted[0],half[1]-predicted[1]),
                exact_retained_held_gain=fit['exact_retained_held_gain'],exact_omitted_held_gain=fit['exact_omitted_held_gain'],
                success=fit['best']['success'],bound_hit=fit['best']['bound_hit']))
    summary=dict(scope='Frozen diagnostic deletions, not a truth-selected estimator',scans=len(results),fits=len(rows),
        truth_sha256=digest(pose_path),results_sha256={f"{r['session_id']}.json":digest(HERE/f"{r['session_id']}.json") for r in results},results=rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'deletions.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for session in protocol['sessions']:
        selected=[r for r in rows if r['session_id']==session]
        for group in ['influence','random_control']:
            group_rows=[r for r in selected if r['selection']==group]
            print(json.dumps(dict(session=session,group=group,baseline_error_m=selected[0]['baseline_error_m'],
                deletion_errors_m=[r['deleted_error_m'] for r in group_rows],
                actual_shifts_m=[r['actual_shift_m'] for r in group_rows],
                retained_held_gains=[r['exact_retained_held_gain'] for r in group_rows],
                omitted_held_gains=[r['exact_omitted_held_gain'] for r in group_rows])))


if __name__=='__main__':main()
