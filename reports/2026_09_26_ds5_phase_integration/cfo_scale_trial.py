"""Evaluate phase without selecting a favorable CFO uncertainty scenario."""
from pathlib import Path
import argparse,json,time
import numpy as np
from cfo_scale_mixture import mixed_options,refine_bank
from shared_baseline_trial import load,donor_banks,baseline_posterior,SESSIONS
from timing_trial import evaluate

HERE=Path(__file__).resolve().parent
OUT=HERE/'cfo-scale-mixture'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);parser.add_argument('--quantiles',type=int,default=33);parser.add_argument('--prior',choices=['broad','previous','extended'],default='broad');parser.add_argument('--tau-step',type=float,default=.2);args=parser.parse_args();OUT.mkdir(exist_ok=True);started=time.monotonic()
    sid=SESSIONS[args.scan];donor=SESSIONS[1-args.scan];scales={'broad':[25,50,100,200,400,800,1600],'previous':[100,200],'extended':[3.125,6.25,12.5,25,50,100,200,400,800,1600]}[args.prior]
    stem=f'{sid}-{args.prior}-q{args.quantiles}'+(f'-t{args.tau_step:g}' if args.tau_step!=.2 else '');protocol=dict(target=sid,donor=donor,scales_hz=scales,scale_prior='Equal probability on declared discrete log-spaced grid; independent scale per track; shared across its train and held blocks',selection='All candidates already in each frozen proposal bank, no new scale-dependent top-four truncation. Banks were proposed at 100/200 Hz; full-catalogue completeness for other scales is not established.',phase='Qualified joint-source evaluation phases; unsupported dwell slots neutral; same earlier folds',baseline='Uniform +/-2m versus learned from other scan with identities, CFO scales and orbit times marginalized',quantiles=args.quantiles,tau_step_s=args.tau_step,refinement='Cubic interpolation of CFO residuals and phase projections; historical timing density recomputed on refined grid; requires finite original visibility support',meaning='Retrospective conditional predictive comparison, not independent identity truth')
    model=json.loads((HERE/'timing-calibration.json').read_text())['model']
    (OUT/(stem+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    source,dobs,dbanks=donor_banks(donor)
    if args.tau_step!=.2:dbanks=[refine_bank(bank,model,args.tau_step) for bank in dbanks]
    donor_options=[mixed_options(bank,scales,args.quantiles) for bank in dbanks];a,b=[r[0] for r in donor_options]
    bp=baseline_posterior(a,b,np.array(dobs['phase_rad']),np.array(dobs['kappa']),np.array([o['f0'] for o in source['observations']]),np.array([o['f1'] for o in source['observations']]))
    print(sid,'donor baseline ready; candidates',len(a),len(b),flush=True)
    results=[];diagnostics=[]
    for fold in (0,1):
        target,obs,banks=load(sid,fold)
        if args.tau_step!=.2:banks=[refine_bank(bank,model,args.tau_step) for bank in banks]
        mixed=[mixed_options(bank,scales,args.quantiles) for bank in banks];a,b=[r[0] for r in mixed]
        diagnostics.append(dict(fold=fold,tracks=[r[1] for r in mixed],candidate_scale_probabilities=[[{k:v for k,v in c.items() if k in ('candidate_id','train','held','scale_probabilities')} for c in options] for options in (a,b)]))
        print(sid,'fold',fold,'training scale probabilities',[r[1]['training_scale_probabilities'] for r in mixed],flush=True)
        for name,prior in [('uniform_baseline',None),('transferred_baseline',bp)]:
            score=evaluate(a,b,np.array(obs['phase_rad']),np.array(obs['training_mask'],bool),np.array([o['f0'] for o in target['observations']]),np.array([o['f1'] for o in target['observations']]),np.array(obs['kappa']),baseline_log_prior=prior);score.update(fold=fold,arm=name);results.append(score)
            print(sid,fold,name,'CFO gain',score['cfo_gain'],'phase vs constant',score['phase_gain_vs_constant'],flush=True)
        (OUT/(stem+'.json')).write_text(json.dumps(dict(protocol=protocol,donor_scale_diagnostics=[r[1] for r in donor_options],donor_baseline_probabilities=np.exp(bp).tolist(),target_diagnostics=diagnostics,experiments=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
