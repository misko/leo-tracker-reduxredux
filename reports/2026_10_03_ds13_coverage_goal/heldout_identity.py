"""Conservative local identity challenges on held-out-only coherent segments.

Alternatives come from the union of both training-only timing searches. No
parameters are refitted on test peaks. This is not a global reassignment or
calibrated posterior probability, and does not certify defensible coverage.
"""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest
from training_union import union_modes
from training_bootstrap import training_view
from compare_decoders import coherence_filter
from audit_identity_modes import challenge


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True);args=parser.parse_args();start=time.monotonic()
    output=ROOT/'heldout-identity'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    selection_path=ROOT/'training-union'/f'fold-{args.fold}'/f'{args.scan}.json'
    decoding_path=ROOT/'heldout-decoding'/f'fold-{args.fold}'/f'{args.scan}.json'
    sources=[ROOT/'training-discovery'/f'fold-{args.fold}'/arm/f'{args.scan}-proposals.json' for arm in ('fitted-c','zero-c')]
    discoveries=[json.loads(p.read_text()) for p in sources];modes=union_modes(discoveries)
    selection=json.loads(selection_path.read_text());decoding=json.loads(decoding_path.read_text())
    if decoding['source_sha256']!=digest(selection_path):raise ValueError('Decoder source changed')
    for path in sources:
        if selection['source_sha256'][str(path)]!=digest(path):raise ValueError('Discovery source changed')
    if discoveries[0]['original_rows']!=selection['original_train_rows']:raise ValueError('Training lineage mismatch')
    if selection['original_test_rows']!=decoding['original_test_rows']:raise ValueError('Test lineage mismatch')
    if set(selection['original_test_rows']) & set(discoveries[0]['original_rows']):raise ValueError('Test leakage')
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual
    data=load_expanded_scan(SESSIONS[args.scan]);mask=np.zeros(len(data.times),bool)
    mask[selection['original_test_rows']]=True;d=training_view(data,mask)
    lookup={int(r):i for i,r in enumerate(d.original_rows)}
    _,features=rf_features(d.rf,d.receiver,False)
    numbers=np.array([p['catalog_number'] for p in modes]);arms={}
    for ai,arm in enumerate(('fitted-c','zero-c')):
        baseline=selection['arms'][arm];params=np.array(baseline['parameters']);coeff=np.array(baseline['coefficient'])
        correction=features@coeff;residual=np.empty((len(d.times),len(modes)));visible=np.empty(residual.shape,bool)
        offset=np.array([p['total_timing_s']-discoveries[ai]['common_timing_s'] for p in modes])
        for col,mode in enumerate(modes):
            index=mode['satellite_index'];params[6+index]=mode['total_timing_s']
            pred,vis,_=SharedPredictionPlan(d,[index]).predict(params)
            residual[:,col]=circular_residual(d.measured,pred+correction,ALIAS_HZ);visible[:,col]=vis
        own_offsets={p['catalog_number']:p['offset_s'] for p in baseline['chosen_modes']}
        methods={}
        for method in ('activity','history','tracklet'):
            assignments=decoding['arms'][arm]['methods'][method]['assignments']
            pairs=[(lookup[r['row_index']],r['catalog_number']) for r in assignments]
            if len({(int(d.group[r]),n) for r,n in pairs})!=len(pairs):raise ValueError('Duplicate satellite/probe')
            errors={lookup[r['row_index']]:r['residual_native_hz'] for r in assignments}
            _,segments=coherence_filter(pairs,d.times,d.receiver,d.channel)
            accepted=[];ambiguous=[];details=[]
            for number,rows in segments:
                scores=-.5*np.sum((residual[rows]/200)**2,axis=0)-.5*offset**2
                scores[~np.all(visible[rows],axis=0)]=-np.inf
                own=-.5*sum((errors[int(r)]/200)**2 for r in rows)-.5*own_offsets[number]**2
                best,margin,passed=challenge(own,number,scores,numbers)
                original=d.original_rows[rows].tolist()
                (accepted if passed else ambiguous).extend(original)
                details.append(dict(catalog_number=number,rows=original,margin=margin,passes=passed,
                    alternative=None if best is None else dict(catalog_number=int(numbers[best]),total_timing_s=modes[best]['total_timing_s']),
                    receiver=int(d.receiver[rows[0]]),channel=int(d.channel[rows[0]]),
                    start_s=float(d.times[rows[0]]),end_s=float(d.times[rows[-1]])))
            untested=sorted(set(r['row_index'] for r in assignments)-set(accepted)-set(ambiguous))
            methods[method]=dict(coherent_decoded=len(assignments),local_identity_pass=len(accepted),
                locally_ambiguous=len(ambiguous),insufficient_test_only_segment_support=len(untested),
                accepted_rows=accepted,ambiguous_rows=ambiguous,untested_rows=untested,segments=details)
            print(args.scan,args.fold,arm,method,len(accepted),len(ambiguous),len(untested),flush=True)
        arms[arm]=methods
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,modes=len(modes),arms=arms,
        test_denominator=len(d.times),elapsed_s=time.monotonic()-start,
        source_sha256={str(p):digest(p) for p in [selection_path,decoding_path,*sources]},
        limitations=['Test-only segments require their own ten-group/five-second support; shorter portions are untested, not failed identities.',
            'Competing timing modes are training-discovered, not exhaustive continuous alternatives.',
            'Local alternatives need not be globally feasible and use fixed training calibration.',
            'No full end-to-end negative-control or additional-scan certification.'])
    with target.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
