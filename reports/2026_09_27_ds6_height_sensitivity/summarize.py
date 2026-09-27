"""Post-selection height sensitivity evaluation, not altitude calibration."""
import json
import hashlib
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    pose_path=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text());rows=[];hashes={}
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if not path.exists():continue
        result=json.loads(path.read_text());assert result['complete']
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        hashes[path.name]=digest(path);baseline=result['arms'][0];arms=[]
        for arm in result['arms']:
            best=arm['best'];a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
            error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
            arms.append(dict(height_m=arm['height_m'],error_m=error,train_gain=arm['exact_train']-baseline['exact_train'],
                held_gain=arm['exact_held']-baseline['exact_held'],success=best['success'],bound_hit=best['bound_hit']))
        rows.append(dict(session_id=session,selected_height_m=result['selected_height_m'],arms=arms))
    summary=dict(completed=len(rows),expected=len(protocol['sessions']),truth_sha256=digest(pose_path),result_sha256=hashes,results=rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
