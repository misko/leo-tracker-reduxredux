"""Measure the unchanged bootstrap's bounded work on automatically extracted segments."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import replay
from local_segments import extract
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_bootstrap import bootstrap_position
from fast_bootstrap import bootstrap_position as batched_bootstrap

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True);p.add_argument('--tle-root',type=Path,required=True)
p.add_argument('--fold',choices=['early_to_late','late_to_early'],required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--samples-per-track',type=int,choices=[6,12],default=12)
p.add_argument('--engine',choices=['original','batched'],default='original')
args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new pilot receipt')
ctx=replay(args,return_context=True)
full,_=build_regional_bank(ctx.catalogue,[ctx.catalogue_lookup[n] for n in ctx.regional_candidate_numbers],
                          ctx.origin_utc_ns,ctx.training_observations,ctx.prior)
segments=extract(ctx.training_observations);tracks=[s['rows'] for s in segments['selected']]
receipt=dict(fold=args.fold,derived_input_sha256=ctx.derivation['derived_input_sha256'],
    configuration=segments['configuration'],tracks=len(tracks),candidates=len(full.numbers),
    point_km=[0.,0.],maximum_seconds=5.,samples_per_track=args.samples_per_track,engine=args.engine,
    maximum_workers=4 if args.engine=='batched' else 1,
    scope='Training-only runtime/shape proposal pilot. Not a fit or held evaluation.')
begun=time.monotonic()
try:
    function=bootstrap_position if args.engine=='original' else batched_bootstrap
    result=function(ctx.training_observations,full,ctx.prior,[0.,0.],tracks,
                              maximum_seconds=5.,samples_per_track=args.samples_per_track)
    receipt.update(status='complete',result=asdict(result))
except (ValueError,TimeoutError) as error:
    receipt.update(status='unavailable',error_type=type(error).__name__,reason=str(error))
receipt['elapsed_seconds']=time.monotonic()-begun
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(receipt,stream,indent=2,default=lambda a:a.tolist());stream.write('\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='result'}),flush=True)
