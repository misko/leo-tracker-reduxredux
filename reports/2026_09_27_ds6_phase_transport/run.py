"""Test individual-source phase transfer with explicit mixer time references."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def transport(z,midpoint,seed_hz):
    return z*np.exp(-2j*np.pi*seed_hz*midpoint)


def fit(t,z,labels):
    modes=np.unique(labels)
    def loss(f):
        v=z*np.exp(-2j*np.pi*f*t)
        return -sum(abs(v[labels==m].sum()) for m in modes)
    grid=np.linspace(-375,375,3001)
    # Profile source intercepts, never constrain their difference to zero.
    score=np.zeros(len(grid))
    for mode in modes:
        take=labels==mode;score+=abs(np.exp(-2j*np.pi*grid[:,None]*t[take])@z[take])
    k=int(np.argmax(score));candidates=[grid[k]]
    candidates.append(minimize_scalar(loss,bounds=(grid[max(0,k-1)],grid[min(len(grid)-1,k+1)]),method='bounded').x)
    f=min(candidates,key=loss)
    phases={int(m):float(np.angle(np.sum(z[labels==m]*np.exp(-2j*np.pi*f*t[labels==m])))) for m in modes}
    return dict(rate_hz=float(f),source_phases_rad=phases)


def arrays(w,label,seed,correct):
    d=w['data'][label];z=np.array(d['z']['real'])+1j*np.array(d['z']['imag'])
    return np.array(d['t'])+w['midpoint'],transport(z,w['midpoint'],seed) if correct else z,np.array(d['s'])


def errors(model,t,z,labels):
    pred=np.array([model['source_phases_rad'][int(m)] for m in labels])+2*np.pi*model['rate_hz']*t
    return np.angle(z*np.exp(-1j*pred))


def main():
    src=ROOT/'2026_09_27_ds6_dwell_phase';oldpath=src/'results.json';old=json.loads(oldpath.read_text())
    planpath=ROOT/'2026_09_27_latest_ten_phase/plan.json';plan=json.loads(planpath.read_text());plans={s['session_id']:s for s in plan['scans']}
    members={s['session_id'] for s in json.loads((ROOT/'2026_09_27_ds6_roof/manifest.json').read_text())['captures']}
    hashes={'partitions':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'seeds':hashlib.sha256(planpath.read_bytes()).hexdigest()}
    for row in old['results']:hashes[row['session_id']]=hashlib.sha256((src/(row['session_id']+'-frames.json')).read_bytes()).hexdigest()
    protocol=dict(source_hashes=hashes,rate_search_hz=[-375,375],grid_step_hz=.25,
        training='Original whole-window split; only fit samples from training windows estimate source intercepts and common rate',
        held='Original qualified held windows, evaluation phasors only; global arms adapt no parameters on held windows',
        transport='z_global = z_window * exp(-2*pi*i*common_delta_seed*window_midpoint); global time = midpoint + local centroid',
        scope='One cached dwell per ten DS6 scans; within-dwell transfer, not cross-retune stability or position fitting')
    (HERE/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
    for row in old['results']:
        sid=row['session_id'];assert sid in members;windows=json.loads((src/(sid+'-frames.json')).read_text())
        v=next(v for v in plans[sid]['selected'] if v['visit']==row['visit'])
        delta=float(np.median([m['seeds'][1]['cfo_hz']-m['seeds'][0]['cfo_hz'] for m in v['modes']]))
        train=row['train_windows'];held=row['held_windows'];out=dict(session_id=sid,visit=row['visit'],delta_seed_hz=delta,train_windows=train,held_windows=held)
        if len(train)<2 or not held:
            out['unavailable_reason']='Original split has fewer than two qualified training windows or no qualified held window';rows.append(out);continue
        out['arms']={}
        for name,correct in [('untransported',False),('transported',True)]:
            parts=[arrays(windows[i],'fit',delta,correct) for i in train];t,z,s=[np.concatenate([p[j] for p in parts]) for j in range(3)];model=fit(t,z,s);err=[];window_rows=[]
            for i in held:
                t,z,s=arrays(windows[i],'evaluation',delta,correct);e=errors(model,t,z,s);err.extend(e.tolist())
                source_errors={int(label):float(np.angle(np.sum(np.exp(1j*e[s==label])))) for label in [-1,1]}
                dd_error=float(np.angle(np.exp(1j*(source_errors[1]-source_errors[-1]))))
                window_rows.append(dict(window=i,errors_rad=e.tolist(),times_s=t.tolist(),source_labels=s.tolist(),source_mean_errors_rad=source_errors,dd_error_rad=dd_error))
            out['arms'][name]=dict(model=model,held_rms_deg=float(np.degrees(np.sqrt(np.mean(np.square(err))))),held_count=len(err),windows=window_rows,
                held_window_dd_rms_deg=float(np.degrees(np.sqrt(np.mean([w['dd_error_rad']**2 for w in window_rows])))))
        # Conditional reference: each held window may use its own fit samples.
        local=[];source_rows=[]
        for i,w in enumerate(windows):
            if not w['result']['both_qualified']:continue
            t,z,s=arrays(w,'fit',delta,True);model=fit(t-w['midpoint'],z,s)
            te,ze,se=arrays(w,'evaluation',delta,True);e=errors(model,te-w['midpoint'],ze,se)
            if i in held:local.extend(e.tolist())
            source_rows.append(dict(window=i,midpoint_s=w['midpoint'],rate_hz=model['rate_hz'],transported_midpoint_phases_rad=model['source_phases_rad'],
                evaluation_rms_deg=float(np.degrees(np.sqrt(np.mean(e**2))))))
        out['local_fit_reference_rms_deg']=float(np.degrees(np.sqrt(np.mean(np.square(local)))))
        out['individual_source_estimates']=source_rows;rows.append(out)
    result=dict(complete=True,protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),rows=rows)
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    valid=[r for r in rows if 'arms' in r];fig,ax=plt.subplots(figsize=(10,4.8));x=np.arange(len(valid))
    for k,name in enumerate(['untransported','transported']):ax.bar(x+(k-1)*.25,[r['arms'][name]['held_rms_deg'] for r in valid],.25,label=name)
    ax.bar(x+.25,[r['local_fit_reference_rms_deg'] for r in valid],.25,label='Local fit on each held window')
    ax.set_xticks(x,[r['session_id'][-8:] for r in valid]);ax.set_ylabel('Held pilot phase RMS (degrees)');ax.legend();ax.set_title('DS6 within-dwell source phase transfer\nGlobal arms fit only training windows; local reference uses held-window fit samples');fig.tight_layout();fig.savefig(HERE/'transfer.png',dpi=180)
    print(json.dumps([dict(session_id=r['session_id'],**{a:r['arms'][a]['held_rms_deg'] for a in r['arms']},local=r['local_fit_reference_rms_deg'],dd_rms=r['arms']['transported']['held_window_dd_rms_deg']) for r in valid],indent=2))


if __name__=='__main__':main()
