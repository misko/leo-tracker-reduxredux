"""Bounded direct-offset replay of the original full candidate/time banks."""
from pathlib import Path
import argparse,json,time,hashlib
import numpy as np
from scipy.special import logsumexp
from quality_quadrature_batch import batch_evidence
from causal_quality_trial import SIDS
from segment_catalogue_trial import SCALES

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-quadrature'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,required=True,choices=[0,1]);parser.add_argument('--nodes',type=int,default=32);parser.add_argument('--benchmark',action='store_true');args=parser.parse_args();OUT.mkdir(exist_ok=True);sid=SIDS[args.scan];path=HERE/'causal-quality'/f'{sid}-bank.npz';bank=dict(np.load(path));c,t,n=bank['residuals'].shape;flat=bank['residuals'].reshape(c*t,n);prior=bank['logprior'].ravel();prior-=logsumexp(prior);started=time.monotonic();acc=np.full((2,c,n),-np.inf)
    protocol=dict(session_id=sid,nodes_per_proposal_component=args.nodes,offset_proposal='Mean and median of first8 blocks, each crossed with all10 quality widths; deterministic Gaussian quadrature with prior/proposal correction',models=['generic','timing_informed'],recursion='Scaled exact quality-state forward recursion conditional on each fixed offset; no Gaussian history compression',source_bank_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),warmup=8,limits='No new catalogue search; .05s orbit-time grid unchanged; quadrature convergence must be checked; conditional offline track membership, no identity truth')
    if not args.benchmark:(OUT/f'{sid}-n{args.nodes}-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    stop=min(128,c*t) if args.benchmark else c*t
    for begin in range(0,stop,64):
        end=min(begin+64,stop);value=batch_evidence(flat[begin:end],SCALES,bank['times'],bank['pilot_flags'],nodes=args.nodes)
        value+=prior[None,begin:end,None];owners=np.arange(begin,end)//t
        for owner in np.unique(owners):acc[:,owner]=np.logaddexp(acc[:,owner],logsumexp(value[:,owners==owner],axis=1))
        if begin%8192==0:print(sid,args.nodes,begin,'/',stop,'elapsed',round(time.monotonic()-started,1),flush=True)
    elapsed=time.monotonic()-started
    if args.benchmark:
        result=dict(protocol=protocol,hypotheses=stop,total_hypotheses=c*t,elapsed_s=elapsed,estimated_full_s=elapsed*c*t/stop)
        (OUT/f'{sid}-n{args.nodes}-benchmark.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True);return
    totals=logsumexp(acc,axis=1);models=[]
    for m,name in enumerate(protocol['models']):
        probabilities=np.exp(acc[m]-totals[m][None,:]);score=float(totals[m,-1]-totals[m,7]);rows=[]
        for i in range(8,n):rows.append(dict(index=i,time_s=float(bank['times'][i]),log_predictive=float(totals[m,i]-totals[m,i-1]),identity_probabilities=probabilities[:,i].tolist()))
        models.append(dict(model=name,held_log_predictive=score,rows=rows));print(sid,args.nodes,name,score,flush=True)
    (OUT/f'{sid}-n{args.nodes}.json').write_text(json.dumps(dict(protocol=protocol,models=models,elapsed_s=elapsed,candidate_ids=list(map(str,bank['candidate_ids'])),all_hypotheses_integrated=c*t),indent=2)+'\n')

if __name__=='__main__':main()
