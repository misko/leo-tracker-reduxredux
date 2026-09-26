"""Learn one physical-baseline prior from the other scan, preserving phase shape."""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.special import logsumexp
from phase_factor import phase_evidence
from timing_trial import options,evaluate
from joint_phase_score import shift_geometry

HERE=Path(__file__).resolve().parent
OUT=HERE/'joint-phase'
SESSIONS=['scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3']

def load(sid,fold):
    prior=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());scored=json.loads((OUT/(sid+'-scores.json')).read_text());obs=next(r for r in scored['observation_sets'] if r['fold']==fold and r['arm']=='joint_qualified')
    banks=[shift_geometry(dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{tid[7:19]}.npz')),obs['phase_epoch_offsets_s']) for tid in prior['track_ids']]
    return prior,obs,banks

def donor_banks(sid):
    prior,obs,a=load(sid,0);_,_,b=load(sid,1);result=[]
    for left,right in zip(a,b):
        ids=sorted(set(map(int,left['indices']))|set(map(int,right['indices'])));out={k:[] for k in ('indices','candidate_ids','train_residual','held_residual','logprior','projection')}
        for index in ids:
            entries=[(bank,int(np.flatnonzero(bank['indices']==index)[0])) for bank in (left,right) if index in bank['indices']];bank,i=entries[0]
            full=np.concatenate([bank['train_residual'][i],bank['held_residual'][i]],axis=-1)
            out['indices'].append(index);out['candidate_ids'].append(bank['candidate_ids'][i]);out['train_residual'].append(full);out['held_residual'].append(full[...,:0]);out['projection'].append(bank['projection'][i]);out['logprior'].append(np.max(np.stack([bb['logprior'][ii] for bb,ii in entries]),axis=0))
        out={k:np.asarray(v) for k,v in out.items()};out['taus']=left['taus'];result.append(out)
    return prior,obs,result

def baseline_posterior(left,right,y,k,f0,f1,n_baseline=81):
    B=np.linspace(-2,2,n_baseline);values=[];lp=[]
    for a in left:
        for b in right:
            geom=2*np.pi*(b['projection'][None,:,:]*f1-a['projection'][:,None,:]*f0)/299792458.
            model=B[:,None,None,None]*geom[None,:,:,:]
            evidence=phase_evidence(y,model,k)
            values.append(logsumexp(evidence,axis=(1,2))-np.log(evidence.shape[1]*evidence.shape[2]));lp.append(a['train']+b['train'])
    lp=np.array(lp);lp-=logsumexp(lp);posterior=logsumexp(lp[:,None]+np.array(values),axis=0);posterior-=logsumexp(posterior)
    return posterior

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);parser.add_argument('--quantiles',type=int,default=33);parser.add_argument('--baseline-points',type=int,default=81);args=parser.parse_args();sid=SESSIONS[args.scan];donor=SESSIONS[1-args.scan]
    suffix='' if (args.quantiles,args.baseline_points)==(33,81) else f'-q{args.quantiles}-b{args.baseline_points}'
    source,dobs,dbanks=donor_banks(donor);priors={};summaries=[]
    for sigma in (100,200):
        a,b=[options(bank,sigma,args.quantiles) for bank in dbanks];lp=baseline_posterior(a,b,np.array(dobs['phase_rad']),np.array(dobs['kappa']),np.array([o['f0'] for o in source['observations']]),np.array([o['f1'] for o in source['observations']]),args.baseline_points)
        priors[sigma]=lp;B=np.linspace(-2,2,args.baseline_points);prob=np.exp(lp)
        summaries.append(dict(sigma=sigma,baseline_m=B.tolist(),probabilities=prob.tolist(),mean_m=float(prob@B),sd_m=float(np.sqrt(prob@(B-prob@B)**2)),left_candidate_ids=[r['candidate_id'] for r in a],right_candidate_ids=[r['candidate_id'] for r in b]))
    protocol=dict(target_scan=sid,donor_scan=donor,selection='All CFO and qualified phase from other scan only; union both donor-fold proposals then top4 under full donor CFO. No target phase trains transferred baseline.',baseline='One signed physical length along assumed 79-degree horizontal axis; separate phase intercept per track pair; initial uniform -2..2m',meaning='Offline leave-one-scan-out transfer, assumes unchanged physical baseline. Catalogue identity and timing remain marginalized; not an external survey or independent DS5 confirmation.')
    protocol.update(timing_quantiles=args.quantiles,baseline_points=args.baseline_points)
    (OUT/(sid+'-baseline'+suffix+'-protocol.json')).write_text(json.dumps(dict(protocol=protocol,donor_priors=summaries),indent=2)+'\n');results=[]
    for fold in (0,1):
        target,obs,banks=load(sid,fold)
        for sigma in (100,200):
            a,b=[options(bank,sigma,args.quantiles) for bank in banks]
            score=evaluate(a,b,np.array(obs['phase_rad']),np.array(obs['training_mask'],bool),np.array([o['f0'] for o in target['observations']]),np.array([o['f1'] for o in target['observations']]),np.array(obs['kappa']),n_baseline=args.baseline_points,baseline_log_prior=priors[sigma]);score.update(fold=fold,sigma=sigma);results.append(score)
            print(sid,fold,sigma,'shared baseline gain',score['cfo_gain'],flush=True)
    (OUT/(sid+'-baseline'+suffix+'-scores.json')).write_text(json.dumps(dict(protocol=protocol,donor_priors=summaries,experiments=results),indent=2)+'\n')

if __name__=='__main__':main()
