import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'results.json').read_text());protocol=json.loads((HERE/'protocol.json').read_text());assert data['complete'];hyp=protocol['baselines'];posterior=np.array(data['scores']['baseline_mixture']['baseline_posterior']);best=int(np.argmax(posterior))
old=json.loads((HERE.parent/'2026_09_27_ds6_likelihood_association/results.json').read_text());cfo=[s['scores']['cfo_only']['held_cfo_log_predictive'] for s in old['scans']];scores={}
inputs=json.loads((HERE.parent/'2026_09_27_ds6_likelihood_association/inputs.json').read_text());zero_log_evidence=0.
for scan,prepared in zip(old['scans'],inputs['scans']):
    train=sum(np.array(g['arms']['cfo_only']['train'])[0]+np.log(.81*p['offset_correlation'][0]+.19) for g,p in zip(scan['groups'],prepared['groups']))
    zero_log_evidence+=float(logsumexp(train)-np.log(len(train)))
training_total=sum(logsumexp(s['train'],axis=-1)-np.log(len(protocol['timing_s'])) for s in data['scans'])
mixture_log_evidence=float(logsumexp(training_total)-np.log(len(hyp)))
for name,result in data['scores'].items():scores[name]=dict(held_by_scan=result['held_by_scan'],gains_vs_cfo=(np.array(result['held_by_scan'])-cfo).tolist(),joint_gain_vs_cfo=float(result['joint_held']-sum(cfo)))
out=dict(scores=scores,largest_training_weight=dict(**hyp[best],probability=float(posterior[best])),length_mass={str(length):float(sum(p for p,b in zip(posterior,hyp) if b['length_m']==length)) for length in [.04,.08,.12]},
    effective_hypotheses=float(np.exp(-np.sum(posterior*np.log(posterior)))),training_mixture_minus_zero_geometry=mixture_log_evidence-zero_log_evidence,elapsed_s=data['elapsed_s']);(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
fig,axes=plt.subplots(1,2,figsize=(12,4.5));x=np.arange(len(hyp));axes[0].bar(x,posterior,label='Both scans training')
for s in data['scans']:
    lt=logsumexp(s['train'],axis=-1);p=np.exp(lt-logsumexp(lt));axes[0].plot(x,p,'.',label=s['session_id'][-8:])
axes[0].axhline(1/len(hyp),color='gray',ls='--',label='Uniform grid prior');axes[0].set_xlabel('Baseline hypothesis: 14 directions × 3 lengths');axes[0].set_ylabel('Conditional training weight');axes[0].legend(fontsize=8)
for i,(name,s) in enumerate(scores.items()):axes[1].bar(np.arange(2)+i*.3,s['gains_vs_cfo'],.3,label=name)
axes[1].set_xticks([.15,1.15],[s['session_id'][-8:] for s in data['scans']]);axes[1].axhline(0,color='gray',lw=1);axes[1].set_ylabel('Held CFO log-score gain versus CFO only');axes[1].legend(fontsize=8);fig.suptitle('DS6 baseline sensitivity: one baseline shared across scans\nDiscrete conditional screen; no calibrated baseline or location estimate');fig.tight_layout();fig.savefig(HERE/'baseline-sensitivity.png',dpi=180)
print(json.dumps(out,indent=2))
