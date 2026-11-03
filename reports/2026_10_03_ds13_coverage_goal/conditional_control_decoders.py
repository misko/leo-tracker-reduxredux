"""Conditional null: re-discovery and all decoders, real-data calibration fixed."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,ALIAS_HZ,digest
from control_data import with_control_observations
from training_union import union_modes
from adaptive_discovery import coherent_segments
from feasible_tracklets import select,compile_proposals,evaluate_mode
from sparse_activity import decode
from compare_decoders import coherence_filter
from heldout_decoders import load_history,checked_test_pairs


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--control',type=int,choices=range(20),required=True);args=parser.parse_args();started=time.monotonic()
    history=load_history();sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,SharedPredictionPlan,rf_features,circular_residual
    source=ROOT/'validation-inputs'/f'{args.scan}-control-{args.control:02d}.npz'
    with np.load(source) as archive:a={k:archive[k] for k in archive.files}
    discoveries=[];sources=[source]
    for arm in ('fitted-c','zero-c'):
        path=ROOT/'control-discovery'/f'replicate-{args.control:02d}'/arm/f'{args.scan}-proposals.json'
        d=json.loads(path.read_text());assert d['control_sha256']==digest(source)
        discoveries.append(d);sources.append(path)
    modes=union_modes(discoveries);case=Case(args.scan);data=with_control_observations(case.data,a)
    calibration_path=OLD/'exhaustive-subset'/f'{args.scan}-receipt.json';calibration=json.loads(calibration_path.read_text())
    assert all(d['source_sha256']==digest(calibration_path) for d in discoveries)
    _,features=rf_features(data.rf,data.receiver,False);reps=a['canonical_rows'];canonical=np.zeros(len(data.times),bool);canonical[reps]=True
    output=ROOT/'conditional-controls'/f'replicate-{args.control:02d}';output.mkdir(parents=True,exist_ok=True)
    target=output/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    arms={};pdet=.8/(13 if args.scan=='A' else 15)
    for arm,discovery in zip(('fitted-c','zero-c'),discoveries):
        fit=calibration['arms'][arm]['fit'];params=np.array(fit['parameters']);coeff=np.array(fit['rf_coefficient_hz_per_ghz']);proposals=[]
        for mode in modes:
            index=mode['satellite_index'];params[6+index]=mode['total_timing_s']
            pred,vis,_=SharedPredictionPlan(data,[index]).predict(params)
            residual=circular_residual(data.measured,pred+features@coeff,ALIAS_HZ)
            good=np.flatnonzero(vis&canonical&(np.abs(residual)<=600))
            segments=coherent_segments(good,data.times,data.group,data.receiver,data.channel,residual)
            for s in segments:
                rr=good[(data.receiver[good]==s['receiver'])&(data.channel[good]==s['channel'])
                    &(data.times[good]>=s['start_s']-1e-7)&(data.times[good]<=s['end_s']+1e-7)]
                s['eligible_rows']=rr.tolist();s['eligible_residual_native_hz']=residual[rr].tolist()
            proposals.append({**mode,'offset_s':mode['total_timing_s']-discovery['common_timing_s'],'segments':segments})
        initial=select(proposals,data.group,data.times,pdet)
        compiled=compile_proposals(proposals,data.group,pdet);chosen=dict(initial['selected_modes']);empty=np.zeros(len(data.times),bool)
        for number in sorted({p['catalog_number'] for p in proposals}-set(chosen)):
            options=[evaluate_mode(m,empty,data.group,data.times) for m in compiled if m['number']==number]
            chosen[number]=max(options,key=lambda x:x['score'])['proposal']
        numbers=np.array(sorted(chosen),int);bank=[proposals[chosen[int(n)]] for n in numbers];methods={}
        if len(bank):
            indices=np.array([p['satellite_index'] for p in bank])
            for p in bank:params[6+p['satellite_index']]=p['total_timing_s']
            pred,vis,_=SharedPredictionPlan(data,indices).predict(params)
            pred=pred.reshape(len(data.times),-1)+(features@coeff)[:,None];vis=vis.reshape(pred.shape)
            residual=circular_residual(data.measured[:,None],pred,ALIAS_HZ)
            gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(residual/200)**2-np.log(2/ALIAS_HZ)
            allowed=np.zeros(gain.shape,bool)
            for col,p in enumerate(bank):
                for s in p['segments']:allowed[s['eligible_rows'],col]=True
            gain[~allowed|~vis|(np.abs(residual)>600)]=-np.inf
        for method in ('activity','history','tracklet'):
            t0=time.monotonic()
            if not len(bank):pairs=[]
            elif method=='activity':pairs=decode(data.times,data.group,data.receiver,data.channel,gain,vis,pdet,beam_width=16)
            elif method=='history':
                hs,_=history.track(data.times,data.group,residual,gain,lanes=4*data.receiver+data.channel-1,
                    beam=16,group_cap=16,top_per_row=3,state=True)
                pairs=[(r,c) for group in hs[0].assignments for r,c in group if c>=0]
            else:
                selected=select(bank,data.group,data.times,pdet);lookup={int(n):i for i,n in enumerate(numbers)}
                pairs=[(r['row_index'],lookup[r['catalog_number']]) for r in selected['assignments']]
            checked_test_pairs(pairs,data.group,canonical)
            assert all(canonical[r] for r,c in pairs)
            retained,_=coherence_filter(pairs,data.times,data.receiver,data.channel)
            methods[method]=dict(raw_assigned=len(pairs),coherent_assigned=len(retained),
                denominator=len(reps),coherent_fraction=len(retained)/len(reps),decoding_s=time.monotonic()-t0)
        arms[arm]=dict(candidate_catalogs=len(bank),methods=methods)
        print(args.scan,args.control,arm,json.dumps(arms[arm]),flush=True)
    result=dict(scope=__doc__,scan=args.scan,control=args.control,union_modes=len(modes),arms=arms,
        elapsed_s=time.monotonic()-started,source_sha256={str(p):digest(p) for p in [*sources,calibration_path]},
        limitations=['Calibration held fixed from real data; end-to-end re-estimation on null data still required.',
            'Raw/coherent assignments are before identity rejection and bound accepted null counts from above.',
            'One replicate is not the required 20-control average.'])
    target.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
