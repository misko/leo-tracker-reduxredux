"""Replay unchanged decoders in an isolated namespace with training refits."""
import argparse,copy,json,sys
import numpy as np
from benchmark import ROOT,digest
import heldout_decoders


def inputs(original,refit):
    for key in ('original_train_rows','original_test_rows'):
        if original[key]!=refit[key]:raise ValueError('Refit row lineage mismatch')
    result={key:copy.deepcopy(original[key]) for key in ('original_train_rows','original_test_rows')};result['arms']={}
    for arm in ('fitted-c','zero-c'):
        old=original['arms'][arm];new=refit['arms'][arm];chosen=copy.deepcopy(old['chosen_modes'])
        if new['catalog_numbers']!=[m['catalog_number'] for m in chosen]:raise ValueError('Refit candidate mismatch')
        for m in chosen:
            common=m['total_timing_s']-m['offset_s'];m['total_timing_s']=new['parameters'][6+m['satellite_index']]
            m['offset_s']=m['total_timing_s']-common
            # Segments must be regenerated from the new physical residuals.
            m.pop('segments',None)
        result['arms'][arm]=dict(chosen_modes=chosen,parameters=new['parameters'],coefficient=new['coefficient'])
    result['scope']='Decoder input adapter only; training refit parameters with fixed selected catalog identities. No old training assignments or segments reused.'
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--fold',type=int,choices=range(5),required=True);args=p.parse_args()
    namespace=ROOT/'refit-replay';namespace.mkdir(exist_ok=True)
    frozen=namespace/'frozen'
    if not frozen.exists():
        try:frozen.symlink_to(ROOT/'frozen',target_is_directory=True)
        except FileExistsError:pass
    if frozen.resolve()!=(ROOT/'frozen').resolve():raise ValueError('Unexpected frozen-data link')
    origin=ROOT/'training-union'/f'fold-{args.fold}'/f'{args.scan}.json'
    rp=ROOT/'expanded-training-refit'/f'fold-{args.fold}'/f'{args.scan}.json'
    original=json.loads(origin.read_text());refit=json.loads(rp.read_text())
    if refit['source_sha256']!=digest(origin):raise ValueError('Refit provenance mismatch')
    result=inputs(original,refit);result['source_sha256']={str(s):digest(s) for s in (origin,rp,ROOT/'heldout_decoders.py',ROOT/'refit_decoder_replay.py')}
    target=namespace/'training-union'/f'fold-{args.fold}'/f'{args.scan}.json';target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x') as f:json.dump(result,f,indent=2)
    oldroot=heldout_decoders.ROOT;oldargv=sys.argv
    try:
        heldout_decoders.ROOT=namespace;sys.argv=['heldout_decoders.py','--scan',args.scan,'--fold',str(args.fold)]
        heldout_decoders.main()
    finally:heldout_decoders.ROOT=oldroot;sys.argv=oldargv


if __name__=='__main__':main()
