"""Training-only receiver-offset bootstrap, with no fitted full-scan nuisance.

Zero orbit timing, receiver slope and RF coefficient are initial hypotheses,
not fitted values. A periodic residual histogram over the complete visible
bank proposes receiver offsets. Later training-only fitting must refine them.
"""
import argparse,copy,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest,split_masks


def training_view(data,mask):
    mask=np.asarray(mask,bool)
    if mask.shape!=data.times.shape or not mask.any():raise ValueError('Invalid training mask')
    view=copy.copy(data)
    for field in ('times','measured','rf','receiver','channel','group','margin'):
        setattr(view,field,np.asarray(getattr(data,field))[mask].copy())
    view.original_rows=np.flatnonzero(mask)
    view.initial=np.zeros(6+len(data.numbers))
    return view


def histogram_modes(hist,centers,maximum=5):
    # Circular smoothing respects the CFO alias seam. Width is fixed, not
    # selected using the held-out fold or the previous full-scan calibration.
    kernel=np.exp(-.5*(np.arange(-6,7)/2.)**2);kernel/=kernel.sum()
    smooth=sum(w*np.roll(hist,int(k)) for k,w in zip(range(-6,7),kernel))
    remaining=smooth.copy();modes=[]
    for _ in range(maximum):
        index=int(np.argmax(remaining));distance=(centers-centers[index]+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2
        modes.append(dict(offset_hz=float(centers[index]),smoothed_votes=float(smooth[index])))
        remaining[np.abs(distance)<2000]=-np.inf
    return modes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--fold',type=int,choices=range(5),required=True);args=parser.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,circular_residual
    data=load_expanded_scan(SESSIONS[args.scan])
    source=ROOT/'frozen'/f'{args.scan}-observations.npz'
    with np.load(source) as a:
        train,test=split_masks(a['times_s'],a['group'],args.fold)
        # Use frozen representatives, with whole-probe folds.
        canonical=np.zeros(len(train),bool);canonical[a['canonical_rows']]=True
    view=training_view(data,train&canonical)
    manifest=json.loads((ROOT/'frozen/manifest.json').read_text())
    parameters=np.zeros(6+len(data.numbers));parameters[:2]=manifest['scans'][args.scan]['known_position_km']
    edges=np.linspace(-ALIAS_HZ/2,ALIAS_HZ/2,911);centers=(edges[:-1]+edges[1:])/2
    hist=np.zeros((2,len(centers)),int)
    for begin in range(0,len(data.numbers),32):
        indices=np.arange(begin,min(begin+32,len(data.numbers)))
        prediction,visible,_=SharedPredictionPlan(view,indices).predict(parameters)
        residual=circular_residual(view.measured[:,None],prediction.reshape(len(view.times),-1),ALIAS_HZ)
        visible=visible.reshape(residual.shape)
        for rx in (0,1):
            eligible=visible&(view.receiver[:,None]==rx)
            hist[rx]+=np.histogram(residual[eligible],bins=edges)[0]
    modes=[histogram_modes(h,centers) for h in hist]
    for rx in (0,1):parameters[2+2*rx]=modes[rx][0]['offset_hz']
    output=ROOT/'training-bootstrap'/f'fold-{args.fold}';output.mkdir(parents=True,exist_ok=True)
    result=dict(scope=__doc__,scan=args.scan,fold=args.fold,parameters=parameters.tolist(),
        rf_coefficient_hz_per_ghz=[0.],modes=modes,train_rows=view.original_rows.tolist(),
        bank_candidates=len(data.numbers),elapsed_s=time.monotonic()-started,
        source_sha256=digest(source),histogram_centers_hz=centers.tolist(),histogram=hist.tolist(),
        limitations=['Histogram modes can be false or timing-biased; this is initialization, not calibrated evidence.',
            'No held-out frequencies, previous assignments or previous nuisance estimates enter the histogram.'])
    (output/f'{args.scan}.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('scan','fold','modes','bank_candidates','elapsed_s')}),flush=True)


if __name__=='__main__':main()
