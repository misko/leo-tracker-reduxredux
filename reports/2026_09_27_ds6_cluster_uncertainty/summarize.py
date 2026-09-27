"""Compare nominal local ellipses with the independently stored roof reference."""
import json
import hashlib
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
CHI2_95=5.991464547107979


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def ellipse(cov,delta):
    xy=np.asarray(cov)[:2,:2];eigenvalues=np.linalg.eigvalsh(xy)
    if eigenvalues[0]<=0:return dict(state='unavailable',reason='Non-positive horizontal covariance')
    squared=float(delta@np.linalg.solve(xy,delta))
    return dict(state='complete',major95_m=float(np.sqrt(CHI2_95*eigenvalues[-1])*1000),
        minor95_m=float(np.sqrt(CHI2_95*eigenvalues[0])*1000),squared_mahalanobis=squared,reference_inside=squared<=CHI2_95)


def main():
    protocol=json.loads((HERE/'protocol.json').read_text());rows=[];hashes={}
    pose_path=HERE.parent/'2026_09_27_ds6_roof/pose-authority.json';pose=json.loads(pose_path.read_text())
    lat,lon=protocol['center']
    truth=np.array([(pose['longitude_deg']-lon)*111.195*np.cos(np.radians(lat)),(pose['latitude_deg']-lat)*111.195])
    for session in protocol['sessions']:
        path=HERE/f'{session}.json'
        if not path.exists():continue
        result=json.loads(path.read_text());assert result['complete']
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        hashes[path.name]=digest(path);delta=truth-np.array(result['x'][:2]);arms={}
        track=result['arms']['track']
        if 'model_covariance' in track:arms['model']=ellipse(track['model_covariance'],delta)
        else:arms['model']=dict(state='unavailable',reason=track['reason'])
        for name in ['track','candidate']:
            arm=result['arms'][name]
            if arm['state']=='complete':
                arms[name]=ellipse(arm['cluster_covariance'],delta)
                half=result['half_steps'][name]
                if half['state']=='complete' and arms[name]['state']=='complete':
                    alt=ellipse(half['cluster_covariance'],delta)
                    if alt['state']=='complete':arms[name]['half_step_major_relative_change']=alt['major95_m']/arms[name]['major95_m']-1
            else:arms[name]=dict(state='unavailable',reason=arm['reason'])
        half_arms={}
        half_track=result['half_steps']['track']
        half_arms['model']=ellipse(half_track['model_covariance'],delta) if 'model_covariance' in half_track else dict(state='unavailable',reason=half_track['reason'])
        for name in ['track','candidate']:
            half=result['half_steps'][name]
            half_arms[name]=ellipse(half['cluster_covariance'],delta) if half['state']=='complete' else dict(state='unavailable',reason=half['reason'])
        rows.append(dict(session_id=session,local_reference_error_m=float(np.linalg.norm(delta)*1000),tracks=len(result['tracks']),
            candidate_groups=result['arms']['candidate']['groups'],
            minimum_training_map_mass=min(t['training_map_mass'] for t in result['tracks']),arms=arms,half_arms=half_arms))
    summary=dict(scope='Nominal local conditional ellipses; descriptive coverage, not calibrated confidence or an irreducible precision bound',
        completed=len(rows),expected=len(protocol['sessions']),truth_sha256=digest(pose_path),result_sha256=hashes,arms={},half_arms={},results=rows)
    for key in ['arms','half_arms']:
        for name in ['model','track','candidate']:
            usable=[r[key][name] for r in rows if r[key][name]['state']=='complete']
            summary[key][name]=dict(available=len(usable),reference_inside=sum(a['reference_inside'] for a in usable),
                median_major95_m=float(np.median([a['major95_m'] for a in usable])) if usable else None,
                major95_below_1km=sum(a['major95_m']<1000 for a in usable))
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['results','result_sha256']},indent=2))


if __name__=='__main__':main()
