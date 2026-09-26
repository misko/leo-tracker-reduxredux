"""Whole-visit phase prediction: constant versus marginalized slow angular rate.

All visits retained. This tests continuity, not orbital identities. A rate model
must never be subtracted as calibration when studying satellite geometry.
"""
from pathlib import Path
import json
import numpy as np
from scipy.special import logsumexp
from phase_factor import phase_evidence

HERE=Path(__file__).resolve().parent/'long-overlap'

def score(y,t,train,kappa,limit_deg_s):
    rates=np.radians(np.linspace(-limit_deg_s,limit_deg_s,401))
    prediction=rates[:,None]*(t-t.mean())[None,:]
    kt=np.full(train.sum(),kappa);ka=np.full(len(y),kappa)
    a=phase_evidence(y[train],prediction[:,train],kt)
    b=phase_evidence(y,prediction,ka)
    slow=float(logsumexp(b)-logsumexp(a))
    constant=float(phase_evidence(y,np.zeros(len(y)),ka)-phase_evidence(y[train],np.zeros(train.sum()),kt))
    weights=np.exp(a-logsumexp(a))
    return dict(slow_held_log_evidence=slow,constant_held_log_evidence=constant,gain_vs_constant=slow-constant,training_mean_rate_deg_s=float(weights@np.degrees(rates)))

def main():
    plan=json.loads((HERE/'plan.json').read_text());out=[]
    protocol=dict(seed=20260929,partition='Random half of occupied visit-start seconds; complementary whole-group folds',rates_deg_s=[2,5,10],kappas=[.5,1,2],selection='All selected visits, no held quality filtering',model='One circular intercept integrated analytically; uniform angular-rate grid integrated; equal per-dwell illustrative concentration',control='Mode 1 shifted by one visit in metadata order before forming differences; its parameters trained separately',meaning='Exploratory phase continuity; neither a causal forecast nor evidence of a particular satellite')
    (HERE/'prediction-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    for scan in plan['scans']:
        if not scan['selected']:continue
        rows=json.loads((HERE/(scan['session_id']+'.json')).read_text())['rows'];a=[];b=[];times=[];bins=[]
        first=min(v['valid_start_counter'] for v in scan['selected'])
        for visit in scan['selected']:
            modes=[sorted([r for r in rows if r['visit']==visit['visit'] and r['mode']==m],key=lambda r:r['start_ms']) for m in (0,1)]
            assert [r['start_ms'] for r in modes[0]]==[r['start_ms'] for r in modes[1]]==plan['starts_ms']
            a.append([r['coefficients']['full']['phase_rad'] for r in modes[0]])
            b.append([r['coefficients']['full']['phase_rad'] for r in modes[1]])
            times.append((visit['valid_start_counter']-first)/1e7)
            # Capture counter seconds bind the entire dwell, including windows
            # crossing a second boundary, to one group.
            bins.append(visit['valid_start_counter']//10_000_000)
        a=np.array(a);b=np.array(b);times=np.array(times);bins=np.array(bins)
        y=np.angle(np.mean(np.exp(1j*(b-a)),axis=1))
        wrong=np.angle(np.mean(np.exp(1j*(np.roll(b,1,axis=0)-a)),axis=1))
        unique=np.unique(bins);rng=np.random.default_rng(protocol['seed']);chosen=rng.choice(unique,len(unique)//2,replace=False);mask=np.isin(bins,chosen)
        experiments=[]
        for fold in (0,1):
            train=mask^bool(fold)
            for k in protocol['kappas']:
                for limit in protocol['rates_deg_s']:
                    experiments.append(dict(fold=fold,train_visits=int(train.sum()),held_visits=int((~train).sum()),kappa=k,rate_limit_deg_s=limit,matched=score(y,times,train,k,limit),wrong_visit=score(wrong,times,train,k,limit)))
        result=dict(session_id=scan['session_id'],visit_ids=[v['visit'] for v in scan['selected']],time_s=times.tolist(),phase_rad=y.tolist(),fold0_training=mask.tolist(),experiments=experiments)
        out.append(result)
        print(scan['session_id'],json.dumps([e for e in experiments if e['kappa']==1 and e['rate_limit_deg_s']==5]),flush=True)
    (HERE/'prediction.json').write_text(json.dumps(dict(protocol=protocol,scans=out),indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for ax,scan,label in zip(axes,out,['09:50 UTC','12:00 UTC']):
        selected=[e for e in scan['experiments'] if e['kappa']==1 and e['rate_limit_deg_s']==5]
        x=np.arange(2)
        for offset,key,field,name,color in [(-.25,'matched','slow_held_log_evidence','Matched slow rate','tab:blue'),(0,'matched','constant_held_log_evidence','Matched constant','tab:green'),(.25,'wrong_visit','slow_held_log_evidence','Wrong-visit slow rate','gray')]:
            ax.bar(x+offset,[e[key][field] for e in selected],width=.24,label=name,color=color)
        ax.axhline(0,color='black',lw=.7);ax.set_xticks(x,['Fold 0','Fold 1']);ax.set_title(label);ax.set_ylabel('Held phase evidence vs uniform (nats)');ax.legend(fontsize=8)
    fig.suptitle('All selected dwells retained; illustrative κ=1, rate prior ±5°/s')
    fig.savefig(HERE/'prediction.png',dpi=160);plt.close(fig)

if __name__=='__main__':main()
