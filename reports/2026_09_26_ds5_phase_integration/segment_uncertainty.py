"""Disentangle resetting a CFO intercept from changing its residual scale."""
import json
import numpy as np
from scipy.special import logsumexp
from segment_catalogue_trial import HERE,OUT,SCALES,mixture
from cfo_scale_mixture import refine_bank
from catalogue_trial import constant_log_evidence

def common_offset_evidence(a,b,sigma_a,sigma_b,prior_sigma=1e6):
    n,m=a.shape[-1],b.shape[-1];va,vb=sigma_a**2,sigma_b**2
    ma,mb=a.mean(axis=-1),b.mean(axis=-1);wa,wb=n/va,m/vb;w=wa+wb;mean=(wa*ma+wb*mb)/w
    sse=np.sum((a-ma[...,None])**2,axis=-1)/va+np.sum((b-mb[...,None])**2,axis=-1)/vb+wa*(ma-mean)**2+wb*(mb-mean)**2
    return -.5*((n+m)*np.log(2*np.pi)+n*np.log(va)+m*np.log(vb)+np.log1p(prior_sigma**2*w)+sse+mean**2/(prior_sigma**2+1/w))

def evidence_arms(a,b):
    shared_both=mixture(np.concatenate([a,b],axis=-1))
    separate_offsets=logsumexp(np.stack([constant_log_evidence(a,s)+constant_log_evidence(b,s) for s in SCALES]),axis=0)-np.log(len(SCALES))
    separate_scales=np.full_like(shared_both,-np.inf)
    for sa in SCALES:
        for sb in SCALES:
            separate_scales=np.logaddexp(separate_scales,common_offset_evidence(a,b,sa,sb))
    separate_scales-=2*np.log(len(SCALES))
    return dict(shared_offset_shared_scale=shared_both,separate_offsets_shared_scale=separate_offsets,shared_offset_separate_scales=separate_scales,separate_offsets_separate_scales=mixture(a)+mixture(b))

def main():
    model=json.loads((HERE/'timing-calibration.json').read_text())['model'];rows=[]
    for fold in (0,1):
        banks=[]
        for name in ('before','after'):
            b=dict(np.load(OUT/f'f{fold}-{name}.npz'));b['projection']=np.zeros((*b['logprior'].shape,1));banks.append(refine_bank(b,model,.025))
        a,b=banks;np.testing.assert_allclose(a['logprior'],b['logprior']);lp=a['logprior']
        tr=evidence_arms(a['train_residual'],b['train_residual']);full=evidence_arms(np.concatenate([a['train_residual'],a['held_residual']],axis=-1),np.concatenate([b['train_residual'],b['held_residual']],axis=-1))
        for arm in tr:
            score=float(logsumexp(full[arm]+lp)-logsumexp(tr[arm]+lp));prob=logsumexp(tr[arm]+lp,axis=-1);prob=np.exp(prob-logsumexp(prob));best=int(np.argmax(prob))
            row=dict(fold=fold,arm=arm,mode0_held_log_predictive=score,top_candidate_id=str(a['candidate_ids'][best]),top_probability=float(prob[best]));rows.append(row);print(row,flush=True)
        (OUT/'uncertainty-ablation.json').write_text(json.dumps(dict(protocol='Same identity and orbit time across episodes; factorial CFO-only offset and residual-scale comparison. Every arm uses identical block coverage and candidate bank.',results=rows),indent=2)+'\n')

if __name__=='__main__':main()
