import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from tools.rx_paired_state_cv import prepare_fold
from core import design,objective,log_probabilities


def main():
    here=Path(__file__).resolve().parent
    path=here.parent/'2026_09_30_rx_causal_response/run.py'
    spec=importlib.util.spec_from_file_location('causal_baseline',path)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    previous_path=here.parent/'2026_09_30_rx_causal_response/results.json'
    previous=json.loads(previous_path.read_text())
    dataset=here.parent/'2026_09_28_rx_geometry_association/dataset.json'
    document=json.loads(dataset.read_text());records=[]
    for i in range(6):
        train,held,receipt=prepare_fold(document,i)
        old=previous['records'][i];assert old['session']==receipt['held_session']
        tau=old['tau_s']
        def prepare(lanes):
            prepared=[]
            for lane in lanes:
                rows=[{'prediction_utc_ns':t,'category':int(y),'source_window_id':sid,'role':str(role)}
                      for t,y,sid,role in zip(lane['timestamps'],lane['y'],lane['ids'],lane['roles'])]
                prediction=baseline.predict(rows,lane['background'].tolist(),tau)
                prepared.append((lane,np.log([r['probabilities'] for r in prediction])))
            return prepared
        training=prepare(train);target=prepare(held)
        x=np.concatenate([design(l) for l,o in training]);offset=np.concatenate([o for l,o in training]);y=np.concatenate([l['y'] for l,o in training])
        target_y=np.concatenate([l['y'][l['roles']=='held_frequency'] for l,o in target])
        target_offset=np.concatenate([o[l['roles']=='held_frequency'] for l,o in target])
        raw=float(np.mean(target_offset[np.arange(len(target_y)),target_y]))
        assert abs(raw-old['later_score_per_window'])<1e-10
        scores={'causal':raw};fits={}
        for arm,dimension in [('P',2),('U',4),('O',5)]:
            bounds=[(-5.,5.)]*dimension
            if arm=='O': bounds[-1]=(0.,5.)
            fit=minimize(objective,np.zeros(dimension),args=(x,offset,y),jac=True,
                         method='L-BFGS-B',bounds=bounds,options={'maxiter':200,'ftol':1e-14,'gtol':1e-7})
            gradient=objective(fit.x,x,offset,y)[1]
            projected=fit.x-np.clip(fit.x-gradient,[b[0] for b in bounds],[b[1] for b in bounds])
            qualified=bool(fit.success and np.max(abs(projected))<1e-4)
            fits[arm]={'beta':fit.x.tolist(),'success':bool(fit.success),'qualified':qualified,
                       'message':str(fit.message),'projected_gradient':float(np.max(abs(projected)))}
            for control in ([None,'swap','reverse','permute'] if arm=='O' else [None]):
                tx=np.concatenate([design(l,control)[l['roles']=='held_frequency'] for l,o in target])
                lp=log_probabilities(fit.x,tx,target_offset)
                scores[arm if control is None else 'O_'+control]=float(np.mean(lp[np.arange(len(target_y)),target_y]))
        records.append({'session':receipt['held_session'],'windows':len(target_y),'fits':fits,'scores':scores})
    contrasts=[('O','U'),('O','P'),('O','O_swap'),('O','O_reverse'),('O','O_permute')]+[(a,'causal') for a in ('P','U','O')]
    summary={}
    for a,b in contrasts:
        values=[r['scores'][a]-r['scores'][b] for r in records]
        summary[a+'-'+b]={'mean_gain':math.fsum(values)/6,'positive_records':sum(v>1e-6 for v in values),'values':values}
    sources=[path,previous_path,dataset,here/'core.py',here/'run.py',here/'PROTOCOL.md',Path.cwd()/'tools/rx_paired_state_cv.py']
    result={'records':records,'summary':summary,'qualified_fits':sum(f['qualified'] for r in records for f in r['fits'].values()),
            'source_sha256':{str(p.relative_to(Path.cwd())):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    with (here/'results.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({'qualified_fits':result['qualified_fits'],'summary':summary},indent=2))


if __name__=='__main__':main()
