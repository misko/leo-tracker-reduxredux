"""Original likelihood, with an explicitly offline slot-preserving patch."""
import importlib.util
import inspect
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
sys.path.insert(0,str(HILL/'joint_receiver_association'))
from doppler_pilot import fast,read,digest
spec=importlib.util.spec_from_file_location('pure_orbit_patch',HILL/'causal_fresh/model.py')
patch_helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch_helpers)


class Model:
    def __init__(self,document,config,identities):
        fast.baseline.profile=fast.profile
        self.engine=fast.Stationary(document,config);self.document=document;self.identities=identities

    def evaluate(self,x,gradient=True):
        score,derivative=self.engine.evaluate(np.asarray(x,float),gradient=gradient)
        return dict(score=score,gradient=derivative)

    def diagnostics(self,x):
        train=joint=0.;rows=[]
        for t in self.document['tracks']:
            prediction,visible=self.engine.prediction(t,np.asarray(x,float))
            a,b,audits,_=fast.profile(t['y'][None]-prediction,t['mask']);assert all(v['converged'] for v in audits)
            a=np.where(visible,a,-np.inf);b=np.where(visible,b,-np.inf)
            z=logsumexp(a);train+=float(z-np.log(t['catalogue_size']));joint+=float(logsumexp(b)-np.log(t['catalogue_size']))
            slot=int(np.argmax(a));rows.append(dict(track_id=t['track_id'],norad=self.identities[t['track_id']]['candidate_norad'][slot],confidence=float(np.exp(a[slot]-z))))
        return dict(training_score=train,held_score=joint-train,identities=rows)


def load(index,arm):
    assert arm in ('original','offline')
    plan_path=HILL.parent/'2026_09_30_ds11_single10/plan.json';plan=read(plan_path)
    selection_path=HERE/'selection.json';selection=read(selection_path);assert index in selection['selected']
    identity_path=HILL/'source_balance/catalogue_identities.json';identity=read(identity_path)['scans'][str(index)]
    entry=plan['inputs'][index];doc=fast.load_documents(dict(config=plan['config'],inputs=[entry]))[0]
    paths=[Path(__file__),HERE/'PROTOCOL.md',plan_path,selection_path,identity_path,HILL/'causal_fresh/model.py',Path(inspect.getfile(fast)),Path(inspect.getfile(fast.baseline))]
    for a in entry['artifacts']:
        assert digest(a['path'])==a['sha256'].removeprefix('sha256:');paths.append(Path(a['path']))
    if arm=='offline':
        path=HERE/f'patch-{index:02d}.json';patch=read(path)
        assert patch['schema']=='ds11-offline-orbit-patch/v1' and patch['offline_only'] is True and patch['index']==index
        for p,h in patch['sources'].items():assert digest(p)==h,p
        with np.load(patch['array_path'],allow_pickle=False) as arrays:doc=patch_helpers.apply_arrays(doc,patch,arrays,plan['config']['timing_grid_s'])
        paths.append(path)
    initial_path=plan_path.parent/f'runs/{index:02d}_iid.json';initial=np.array(read(initial_path)['selected']['x']);paths.append(initial_path)
    return Model(doc,plan['config'],identity['tracks']),initial,{str(p):digest(p) for p in paths}
