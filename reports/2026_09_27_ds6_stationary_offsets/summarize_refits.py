import json
import math
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=json.loads((HERE/'refit-protocol.json').read_text())
pose_path=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text())
def error(best):
    a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
    return 12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
rows=[];hashes={}
for session in protocol['sessions']:
    path=HERE/f'{session}-refit.json';r=json.loads(path.read_text())
    assert r['complete'] and r['protocol_sha256']==digest(HERE/'refit-protocol.json')
    hashes[path.name]=digest(path)
    old=json.loads((HERE.parent/'2026_09_27_ds6_element_freshness'/f'{session}.json').read_text())
    rows.append(dict(session_id=session,baseline_error_m=error(old['best']),corrected_error_m=error(r['best']),
        exact_held_gain_vs_original=r['exact']['held']-old['exact_held'],train_gain_after_position_refit=r['best']['train']-r['baseline_corrected']['train'],
        success=r['best']['success'],bound_hit=r['best']['bound_hit']))
summary=dict(scope='Selected-track numerical corrections, not a full stationary-offset estimator',truth_sha256=digest(pose_path),result_sha256=hashes,results=rows)
(HERE/'refit-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
