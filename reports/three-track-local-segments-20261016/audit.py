"""Audit orbit-blind segments against fixed target membership, after extraction."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import replay, verified_json
from rerun_cold import prepare
from local_segments import extract
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views


def run(args):
    if args.output.exists():
        raise FileExistsError('Use a new audit namespace')
    ctx=replay(args,return_context=True)
    prepared_args=argparse.Namespace(**vars(args))
    prepared_args.output=args.output/'preparation';prepared_args.run=False
    prepare(prepared_args)
    views,_=prepare_views(load_input(verified_json(prepared_args.output/'training-input.json',
        ctx.derivation['derived_input_sha256'])))
    begun=time.monotonic()
    result=extract(ctx.training_observations)
    result['elapsed_seconds']=time.monotonic()-begun
    result['fold']=args.fold
    result['derived_input_sha256']=ctx.derivation['derived_input_sha256']
    lookup={key:i for i,key in enumerate(ctx.training_observations.window_ids)}
    result['target_coverage']=[]
    for target in ctx.derivation['targets']:
        rows={lookup[ctx.observations.window_ids[i]] for i in target['training_rows']}
        entry=dict(track=target['track'],training_count=len(rows))
        for name,groups in [('proposals',[p['rows'] for p in result['proposals']]),
                            ('selected',[p['rows'] for p in result['selected']]),
                            ('original_bootstrap',views['all'].bootstrap_tracks)]:
            overlaps=[dict(count=len(rows&set(group)),total=len(group),
                           purity=len(rows&set(group))/len(group),rows=list(group))
                      for group in groups if rows&set(group)]
            represented=set().union(*(set(g) for g in groups)) if groups else set()
            entry[name]=dict(covered=len(rows&represented),groups=overlaps)
        result['target_coverage'].append(entry)
    result['scope']='All extraction and ranking use cold training observations only, without target membership, satellite labels, TLEs, receiver calibration or position. Target membership is inspected only after extraction. Segment recovery is not satellite recovery; the full cold pipeline and held temporal tests remain necessary.'
    path=args.output/'audit.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(fold=args.fold,elapsed_seconds=result['elapsed_seconds'],
        proposals=len(result['proposals']),selected=len(result['selected']),
        coverage=[dict(track=t['track'],n=t['training_count'],
                       **{key:t[key]['covered'] for key in ['original_bootstrap','proposals','selected']})
                  for t in result['target_coverage']]),indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--tle-root',type=Path,required=True)
    p.add_argument('--fold',choices=['early_to_late','late_to_early'],required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
