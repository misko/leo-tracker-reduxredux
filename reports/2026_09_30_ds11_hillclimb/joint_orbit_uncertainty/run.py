"""Zero-parity, derivative and runtime benchmark; no geographic fitting."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
from model import JointOrbit,fast

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def context(index):
    metadata_path=HILL/f'ds11_revision_states/{index:02d}.json';metadata=read(metadata_path)
    sources=dict(metadata['sources'])
    for p,h in sources.items():assert digest(p)==h
    assert digest(metadata['output_path'])==metadata['output_sha256']
    inventory_path=HILL/'ds11_revision_support/inventory.json';inventory=read(inventory_path)
    scan=next(s for s in inventory['scans'] if s['index']==index)
    base=HILL.parent/'2026_09_30_ds11_single10';plan=read(base/'plan.json')
    doc=fast.load_documents(dict(config=plan['config'],inputs=[plan['inputs'][index]]))[0]
    rows={r['track_id']:r for r in metadata['rows']};mapping={tid:r['candidate_norad'] for tid,r in rows.items()}
    oldtracks=[]
    with np.load(metadata['output_path'],allow_pickle=False) as bank:
        np.testing.assert_array_equal(bank['timing_grid_s'],np.array(plan['config']['timing_grid_s']))
        for track in doc['tracks']:
            i=rows[track['track_id']]['index'];oldtracks.append(dict(track,candidate_position_km=bank[f'position_km_{i}'],candidate_velocity_km_s=bank[f'velocity_km_s_{i}']))
    older=dict(doc,tracks=oldtracks)
    prior_path=HILL/'orbit_uncertainty_transfer/priors.json';priors=read(prior_path)
    for p,h in priors['sources'].items():assert digest(p)==h
    sources.update(priors['sources'])
    original_path=base/f'runs/{index:02d}_iid.json';original=read(original_path)['selected'];assert original['qualified']
    paths=[metadata_path,Path(metadata['output_path']),inventory_path,prior_path,original_path,Path(__file__),HERE/'model.py',HERE/'test_model.py',HERE/'PROTOCOL.md',HILL/'joint_identity/model.py']
    for p in paths:sources[str(p)]=digest(p)
    return doc,older,plan['config'],mapping,scan,np.array(original['x']),priors,sources

def main(index):
    started=time.monotonic();doc,older,config,mapping,scan,x,priors,sources=context(index)
    lookup={t['track_id']:i for i,t in enumerate(doc['tracks'])}
    groups=[dict(document_index=0,norad=g['selected_norad'],members=tuple((0,lookup[t]) for t in g['track_ids']),candidate_norad=g['candidate_norad']) for g in scan['groups']]
    singletons=tuple((0,lookup[s['track_id']]) for s in scan['singletons'])
    spec=importlib.util.spec_from_file_location('existing_joint_identity',HILL/'joint_identity/model.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    expected=old.JointIdentity([doc],config,[mapping],groups,singletons).evaluate(x)
    results={}
    for variant in ('zero','orbit','linear'):
        weights=priors['priors']['orbit' if variant=='zero' else variant]['weights']
        model=JointOrbit(doc,older,config,mapping,scan['groups'],scan['singletons'],variant,weights)
        start=time.monotonic();r=model.evaluate(x);elapsed=time.monotonic()-start
        finite=[]
        for axis,step in enumerate((1e-4,1e-4,1e-5)):
            d=np.eye(3)[axis]*step
            finite.append((model.evaluate(x+d,False)['score']-model.evaluate(x-d,False)['score'])/(2*step))
        result=dict(score=r['score'],gradient=r['gradient'].tolist(),finite_gradient=finite,
                    maximum_gradient_discrepancy=float(np.max(abs(r['gradient']-finite))),gradient_evaluation_s=elapsed)
        if variant=='zero':result.update(parity_score_error=abs(r['score']-expected['score']),parity_gradient_error=float(np.max(abs(r['gradient']-expected['gradient']))))
        results[variant]=result
    passed=all(r['maximum_gradient_discrepancy']<.02 for r in results.values()) and results['zero']['parity_score_error']<1e-6 and results['zero']['parity_gradient_error']<1e-6
    outcome=dict(index=index,results=results,numerical_gate_pass=passed,sources=sources,position_fits=0,reference_used=False,elapsed_s=time.monotonic()-started)
    with (HERE/f'{index:02d}.json').open('x') as f:json.dump(outcome,f,indent=2)
    print(json.dumps({k:v for k,v in outcome.items() if k!='sources'},indent=2))
if __name__=='__main__':main(int(sys.argv[1]))
