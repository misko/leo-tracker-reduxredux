"""Choose supported epoch updates without reading geographic references."""
import inspect
import json
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_receiver_association'))
from doppler_pilot import fast,read,digest


def main():
    plan_path=HILL.parent/'2026_09_30_ds11_single10/plan.json';plan=read(plan_path)
    inventory_path=HILL/'delayed_orbit_inventory/inventory.json';inventory=read(inventory_path)
    identity_path=HILL/'source_balance/catalogue_identities.json';identities=read(identity_path)
    assert identities['plan_sha256']==digest(plan_path)
    paths=[Path(__file__),HERE/'PROTOCOL.md',plan_path,inventory_path,identity_path,Path(inspect.getfile(fast)),Path(inspect.getfile(fast.baseline))]
    sources={str(p):digest(p) for p in paths};rows=[];selected=[]
    for scan in sorted(inventory['scans'],key=lambda r:r['index']):
        index=scan['index'];newer={r['norad']:r for r in scan['candidates'] if r['delayed_epoch_ns']>r['original_epoch_ns']}
        if not newer:
            rows.append(dict(index=index,eligible=False,reason='no_newer_retained_candidate_epoch'));continue
        entry=plan['inputs'][index];assert scan['session']==entry['session_id']
        doc=fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
        initial_path=plan_path.parent/f'runs/{index:02d}_iid.json';x=np.array(read(initial_path)['selected']['x']);sources[str(initial_path)]=digest(initial_path)
        side=identities['scans'][str(index)]
        for a in entry['artifacts']:
            assert digest(a['path'])==a['sha256'].removeprefix('sha256:');sources[a['path']]=digest(a['path'])
        engine=fast.Stationary(doc,plan['config']);supported=[]
        for track in doc['tracks']:
            pred,visible=engine.prediction(track,x)
            score,_,audits,_=fast.profile(track['y'][None]-pred,track['mask']);assert all(a['converged'] for a in audits)
            score=np.where(visible,score,-np.inf);slot=int(np.argmax(score));confidence=float(np.exp(score[slot]-logsumexp(score)))
            norad=side['tracks'][track['track_id']]['candidate_norad'][slot]
            if confidence>=.9 and norad in newer:supported.append(dict(track_id=track['track_id'],norad=norad,confidence=confidence,epoch_advance_s=(newer[norad]['delayed_epoch_ns']-newer[norad]['original_epoch_ns'])/1e9))
        rows.append(dict(index=index,eligible=bool(supported),supported_tracks=supported,newer_candidate_count=len(newer)))
        if supported:selected.append(index)
        if len(selected)==2:break
    result=dict(selected=selected,screened=rows,offline_only=True,primary_causal_goal_satisfied=False,reference_used=False,sources=sources)
    with (HERE/'selection.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(selected=selected,screened=[dict(index=r['index'],eligible=r['eligible'],supported_tracks=len(r.get('supported_tracks',[]))) for r in rows]),indent=2))


if __name__=='__main__':main()
