"""Training-only coherent offset proposals; initialization, not associations."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks
from training_bootstrap import training_view
from adaptive_discovery import coherent_segments


def wrap(value):return (np.asarray(value)+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2


def rank_offsets(score,centers):
    work=np.asarray(score,float).copy();choices=[]
    for _ in range(5):
        i=int(np.argmax(work))
        if work[i]<=0:break
        choices.append(dict(offset_hz=float(centers[i]),score=float(work[i])))
        work[np.abs(wrap(centers-centers[i]))<2500]=-np.inf
    return choices


def local_offset_seeds(residual,groups,edges,maximum=5):
    """Probe/bin-deduplicated retrieval modes; final segments deduplicate probes."""
    bins=np.clip(np.searchsorted(edges,residual,side='right')-1,0,len(edges)-2)
    pairs=np.unique(np.column_stack((bins,groups)),axis=0)
    hist=np.bincount(pairs[:,0],minlength=len(edges)-1)
    votes=sum(np.roll(hist,k) for k in range(-2,3)).astype(float)
    centers=(edges[:-1]+edges[1:])/2;seeds=[]
    for _ in range(maximum):
        best=int(np.argmax(votes))
        if votes[best]<10:break
        seeds.append(float(centers[best]));votes[np.abs(wrap(centers-centers[best]))<1500]=0
    return seeds


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True)
    parser.add_argument('--control',type=int,choices=range(20));args=parser.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,circular_residual
    data=load_expanded_scan(SESSIONS[args.scan]);source=ROOT/'frozen'/f'{args.scan}-observations.npz'
    if args.control is not None:
        from control_data import with_control_observations
        source=ROOT/'validation-inputs'/f'{args.scan}-control-{args.control:02d}.npz'
        with np.load(source) as archive:control={k:archive[k] for k in archive.files}
        data=with_control_observations(data,control)
    with np.load(source) as a:
        train,_=split_masks(a['times_s'],a['group'],args.fold)
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    view=training_view(data,train&canonical)
    manifest=json.loads((ROOT/'frozen/manifest.json').read_text())
    parameters=np.zeros(6+len(data.numbers));parameters[:2]=manifest['scans'][args.scan]['known_position_km']
    edges=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,911);centers=(edges[:-1]+edges[1:])/2
    proposals=[];scores=np.zeros((2,len(centers)))
    lanes=[(rx,ch,np.flatnonzero((view.receiver==rx)&(view.channel==ch))) for rx in (0,1) for ch in np.unique(view.channel)]
    for begin in range(0,len(data.numbers),32):
        ids=np.arange(begin,min(begin+32,len(data.numbers)))
        prediction,visible,_=SharedPredictionPlan(view,ids).predict(parameters)
        residual=circular_residual(view.measured[:,None],prediction.reshape(len(view.times),-1),ALIAS_HZ)
        visible=visible.reshape(residual.shape)
        for col,index in enumerate(ids):
            for rx,ch,lane in lanes:
                rows=lane[visible[lane,col]]
                if len(rows)<10:continue
                for seed in local_offset_seeds(residual[rows,col],view.group[rows],edges):
                    delta=wrap(residual[:,col]-seed);near=rows[np.abs(delta[rows])<=600]
                    segments=coherent_segments(near,view.times,view.group,view.receiver,view.channel,delta)
                    for segment in segments:
                        rr=np.array(segment['rows']);offset=float(wrap(seed+np.median(delta[rr])))
                        centered=wrap(residual[rr,col]-offset);rms=float(np.sqrt(np.mean(centered**2)))
                        # Offset votes are only a ranking heuristic. They can
                        # reuse peaks between candidates and never count as coverage.
                        weight=len(rr)*max(0.,1-rms/600)
                        scores[rx]+=weight*np.exp(-.5*(wrap(centers-offset)/1000)**2)
                        proposals.append(dict(catalog_number=int(data.numbers[index]),receiver=rx,channel=int(ch),
                            offset_hz=offset,groups=len(rr),start_s=segment['start_s'],end_s=segment['end_s'],
                            centered_rms_hz=rms,rows=view.original_rows[rr].tolist(),weight=weight))
        if (begin//32)%5==0:print(args.scan,'coherent bootstrap',int(ids[-1])+1,'/',len(data.numbers),flush=True)
    modes=[]
    for rx in (0,1):
        choices=rank_offsets(scores[rx],centers);modes.append(choices)
        if choices:parameters[2+2*rx]=choices[0]['offset_hz']
    output=ROOT/'training-coherent-bootstrap'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    if args.control is not None:
        output=ROOT/'control-coherent-bootstrap'/f'replicate-{args.control:02d}'/f'fold-{args.fold}'
        output.mkdir(parents=True,exist_ok=True)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,parameters=parameters.tolist(),modes=modes,
        control=args.control,receiver_has_support=[bool(np.max(scores[rx])>0) for rx in (0,1)],
        status='seed_proposals' if proposals else 'abstain_no_coherent_seed',
        rf_coefficient_hz_per_ghz=[0.],proposals=proposals,train_rows=view.original_rows.tolist(),
        source_sha256=digest(source),elapsed_s=time.monotonic()-started,
        limitations=['Zero timing/slope/RF are initial hypotheses; later training-only fitting must refine them.',
            'Votes are nonexclusive and not likelihoods, posterior probabilities or assigned coverage.',
            'Training gaps conservatively split segments; no held-out observations fill them.'])
    name=f'{args.scan}.json' if args.control is None else f'{args.scan}-checked.json'
    (output/name).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:result[k] for k in ('scan','fold','modes','elapsed_s')}),flush=True)


if __name__=='__main__':main()
