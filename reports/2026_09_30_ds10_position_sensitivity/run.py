import hashlib
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
from scipy.linalg import eigvalsh


def profile(j,w):
    p=j[:,:2];t=j[:,2]
    fixed=p.T@(w[:,None]*p)
    denominator=float(np.dot(w*t,t))
    shift=-(t@(w[:,None]*p))/denominator if denominator>0 else np.zeros(2)
    residual=p+t[:,None]*shift
    return fixed,residual.T@(w[:,None]*residual),shift


def main():
    start=time.monotonic();here=Path(__file__).resolve().parent
    helper_path=here.parent/'2026_09_29_receiver_holdout/run.py'
    spec=importlib.util.spec_from_file_location('sensitivity_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    planpath=here.parent/'2026_09_30_ds10_scale_weighting/plan.json'
    plan=json.loads(planpath.read_text())
    for name,digest in plan['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
    docs=helper.baseline.load_documents(dict(config=plan['config'],inputs=plan['inputs']))
    model=helper.TrendMixturePosition(docs,plan['config'],helper.baseline.Stationary,.2)
    x=np.array(plan['baseline']['x']);evaluation=model.evaluate(x,gradient=False,held=True)
    assert abs(evaluation['score']-plan['baseline']['score'])<1e-7
    metadata={(r['session_id'],r['track_id']):r for r in evaluation['rows']}
    scans=[];full=[]
    for factor in (1.,.5):
        total_fixed=np.zeros((2,2));total_profile=np.zeros((2,2));total_weight=0
        for i,doc in enumerate(docs):
            js=[];ws=[]
            for track in doc['tracks']:
                row=metadata[(doc['session_id'],track['track_id'])]
                k=int(np.argmax(row['weights_given_signal']))
                weight=float(row['signal_responsibility']*row['weights_given_signal'][k])
                z=np.array([x[0],x[1],x[i+2]]);columns=[]
                for axis,step in enumerate(np.array([.001,.001,.00001])*factor):
                    plus=z.copy();minus=z.copy();plus[axis]+=step;minus[axis]-=step
                    a,va=model.models[i].prediction(track,plus);b,vb=model.models[i].prediction(track,minus)
                    assert np.array_equal(va,vb)
                    columns.append((a[k]-b[k])/(2*step))
                j=np.stack(columns,axis=1)[track['mask']]
                j-=j.mean(axis=0);js.append(j);ws.append(np.full(len(j),weight))
            j=np.concatenate(js);w=np.concatenate(ws);fixed,profiled,shift=profile(j,w)
            total_fixed+=fixed;total_profile+=profiled;total_weight+=sum(w)
            if factor==1:
                scans.append({'session':doc['session_id'],'tracks':len(doc['tracks']),
                              'training_observations':len(w),'effective_weight':float(sum(w)),
                              'timing_shift_s_per_km_east_north':shift.tolist(),
                              'fixed_timing_rms_hz_per_km':np.sqrt(np.diag(fixed)/sum(w)).tolist(),
                              'free_timing_rms_hz_per_km':np.sqrt(np.diag(profiled)/sum(w)).tolist()})
        full.append({'fixed':total_fixed,'profiled':total_profile,'weight':total_weight})
    change={key:float(np.linalg.norm(full[0][key]-full[1][key])/np.linalg.norm(full[1][key])) for key in ('fixed','profiled')}
    assert max(change.values())<.01
    first=full[0];summary={'tracks':sum(s['tracks'] for s in scans),
        'fixed_timing_rms_hz_per_km_east_north':np.sqrt(np.diag(first['fixed'])/first['weight']).tolist(),
        'free_timing_rms_hz_per_km_east_north':np.sqrt(np.diag(first['profiled'])/first['weight']).tolist(),
        'free_timing_weak_strong_rms_hz_per_km':np.sqrt(np.linalg.eigvalsh(first['profiled'])/first['weight']).tolist(),
        'timing_information_retention_eigenvalues':eigvalsh(first['profiled'],first['fixed']).tolist(),
        'step_halving_relative_change':change,'elapsed_seconds':time.monotonic()-start}
    sources=[planpath,helper_path,Path(__file__),here/'PROTOCOL.md']
    result={'summary':summary,'scans':scans,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    with (here/'results.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
