"""Replay fixed catalogue banks with increasing CFO-offset mixture resolution."""
import argparse,json,time
from pathlib import Path
import numpy as np
from quality_mixture import run_mixture
from causal_quality_trial import SIDS
from segment_catalogue_trial import SCALES

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-mixture'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,required=True,choices=[0,1]);parser.add_argument('--components',type=int,default=2);args=parser.parse_args();OUT.mkdir(exist_ok=True);sid=SIDS[args.scan];started=time.monotonic()
    bank=dict(np.load(HERE/'causal-quality'/f'{sid}-bank.npz'));results=[]
    for kind in ('generic','timing_informed'):
        rows=run_mixture(bank['residuals'],bank['logprior'],SCALES,bank['times'],bank['pilot_flags'],kind,components=args.components)
        score=sum(r['log_predictive'] for r in rows if r['held']);results.append(dict(model=kind,held_log_predictive=score,rows=rows));print(sid,args.components,kind,score,'elapsed',time.monotonic()-started,flush=True)
        (OUT/f'{sid}-k{args.components}.json').write_text(json.dumps(dict(protocol='Same frozen .05s banks, quality scales and transition hazards; update each offset history before posterior compression; retain K offset-ordered equal-mass groups per quality state. No observation or parameter changes.',session_id=sid,components=args.components,models=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
