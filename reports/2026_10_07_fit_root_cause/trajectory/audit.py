"""Decode optimizer callbacks independently of feasible-query inventory."""
import json
from pathlib import Path
import numpy as np

def physical_callback(z, arm, label, initial):
    size=len(initial)
    scales=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(size-7)]
    if label=='cscale20':scales[6]=20
    if label=='allscale01':scales*=.1
    free=np.arange(size) if arm=='fitted-c' else np.delete(np.arange(size),6)
    result=np.array(initial,copy=True)
    result[free]=np.asarray(z)*scales[free]
    if arm=='zero-c':result[6]=0
    return result

def audit(receipt):
    initial=np.asarray(receipt['events'][0]['vector'])
    values=np.asarray([e['vector'] for e in receipt['events']])
    callbacks=[]
    for row in receipt['iterations']:
        vector=physical_callback(row['z'],receipt['arm'],receipt['label'],initial)
        distances=np.max(np.abs(values-vector),axis=1)
        nearest=int(np.argmin(distances))
        event=receipt['events'][nearest] if distances[nearest]<1e-7 else None
        callbacks.append(dict(iteration=row['iteration'],spatial_feasible=bool(np.linalg.norm(vector[:2]-initial[:2])<=25/np.sqrt(2)+1e-7),matched_query=nearest if event else None,objective=event['value'] if event else None,signal_mass=event['signal_mass'] if event else None,vector=vector.tolist()))
    return callbacks

if __name__=='__main__':
    here=Path(__file__).resolve().parent;output={}
    for path in here.glob('*_associated_*.json'):
        r=json.loads(path.read_text());output[path.stem]=audit(r)
    (here/'callback_audit.json').write_text(json.dumps(output))
