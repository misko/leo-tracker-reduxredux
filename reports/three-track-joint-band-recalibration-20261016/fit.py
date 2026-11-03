"""Matched frozen/free band-contrast continuations after generic timing search."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-coordinate-timing-20261016'))
from run import context
from evaluate import audit,observations,classify_frozen_endpoint
from band_transport import unfreeze,freeze
from leo.application.channel_group_refinement import objective
from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.shared_scan_model import CountedObjective
from leo.cli.shared_fast_position import load_input


def run(args):
    if args.output.exists():raise FileExistsError('Use a new matched fit namespace')
    ctx=context(args);parent=json.loads(args.parent.read_text())
    if not parent['audit']['accepted'] or not parent['profile']['complete']:
        raise ValueError('Complete accepted timing-search donor required')
    if parent['arm']!=args.arm or parent['derived_input_sha256']!=ctx.derivation['derived_input_sha256']:
        raise ValueError('RF arm or training donor differs')
    for name,digest in parent['source_sha256'].items():
        if hashlib.sha256((HERE.parent/'three-track-coordinate-timing-20261016'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Executed coordinate source differs')
    checked=audit(ctx.model,parent['fit'],parent['options'])
    if not checked['accepted'] or abs(checked['objective']-parent['audit']['objective'])>1e-7:
        raise ValueError('Timing-search donor failed strict replay')
    joint=objective(SimpleNamespace(observations=ctx.obs),ctx.bank,ctx.prior,ctx.nodes)
    model,v,n,transport=unfreeze(ctx.model,parent['fit'],ctx.shift,joint)
    args.output.mkdir(parents=True,exist_ok=False)
    result=dict(arm=args.arm,parent_sha256=hashlib.sha256(args.parent.read_bytes()).hexdigest(),
        derived_input_sha256=ctx.derivation['derived_input_sha256'],donor_audit=checked,transport=transport,
        source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ['fit.py','band_transport.py']},
        scope='Research matched continuation after generic all-candidate timing search. Frozen control and free receiver-band contrast arm use identical observations, retained candidates, priors, common clocks, initial physical corrections, timing values, detectability, spatial domain and 60s/65s fit budgets. Only the two existing receiver high-minus-low offsets become free, retaining their original 50kHz Gaussian prior. Both fitted-c and c=0 cases inherit their corresponding previously matched timing-search donor. No target membership, target identity or held measurement enters fitting. Actual frozen classifier is evaluated after both continuations. No independent identity or position truth.',variants=[])
    variants=[('frozen',ctx.model,np.array(parent['fit']['vector']),np.array(parent['fit']['nuisance'])),
              ('joint',model,v,n)]
    for variant,training,seed_v,seed_n in variants:
        options=dict(parent['options'],arm=args.arm,seconds=60.,iterations=600)
        counted=CountedObjective(training,seconds=65.,maximum=4999);begun=time.monotonic()
        row=dict(variant=variant,options=options,fit={},audit=dict(accepted=False))
        try:
            fitted=fit_group_calibration(counted,seed_v,seed_n,**options)
            counted.maximum=5000;checked=audit(counted,fitted,options)
            row.update(fit=fitted,audit=checked)
        except (ValueError,TimeoutError) as error:
            row['audit']=dict(accepted=False,reason=str(error),error_type=type(error).__name__)
        row.update(elapsed_seconds=time.monotonic()-begun,actual_objective_calls=counted.calls)
        if row['elapsed_seconds']>65:row['audit'].update(accepted=False,reason='65s total allowance exceeded')
        result['variants'].append(row)
        (args.output/(variant+'.json')).write_text(json.dumps(row,indent=2,default=lambda a:a.tolist())+'\n')
        print(json.dumps(dict(event='fit-complete',arm=args.arm,variant=variant,audit=row['audit'],
                              elapsed_seconds=row['elapsed_seconds'])),flush=True)
    # Original held carrier values are not even loaded until both fits finish.
    payload=args.input.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=ctx.derivation['parent_input_sha256']:raise ValueError('Original input differs')
    full=observations(load_input(json.loads(payload)))
    for row in result['variants']:
        if not row['fit']:continue
        if row['variant']=='joint':
            frozen,frozen_fit,shift,closure=freeze(model,row['fit'])
            row['prediction_transport']=closure
        else:
            frozen,frozen_fit,shift=ctx.model,row['fit'],ctx.shift
        row['pipeline_classification']=classify_frozen_endpoint(frozen,frozen_fit,shift,full,ctx.derivation,ctx.nodes)
        (args.output/(row['variant']+'.json')).write_text(json.dumps(row,indent=2,default=lambda a:a.tolist())+'\n')
    (args.output/'result.json').write_text(json.dumps(result,indent=2,default=lambda a:a.tolist())+'\n')
    print(json.dumps(dict(arm=args.arm,variants=[dict(variant=r['variant'],audit=r['audit'],
        tracks=[{k:t[k] for k in ['track','training_satellite','test_matches_training_satellite','test_count','test_rms_hz']}
                for t in r.get('pipeline_classification',{}).get('tracks',[])]) for r in result['variants']])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['attempt','parent','tle-root','input','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--arm',choices=['fitted-c','zero-c'],required=True);run(p.parse_args())
