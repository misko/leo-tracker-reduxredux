"""Conditional one/two-tone pilot-template prediction, not satellite identity.

Fit independent complex amplitudes per frame on half the 64 pilot symbols;
score the untouched other half, then reverse. One-source CFO is searched on
training samples only. Two-source CFOs use stored tracking frequencies after
residual correction, not the pre-residual acquired CFO basin.
Epoch and hypotheses were originally detected using the complete probe, so
this is a conditional diagnostic, NOT independent detector validation.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from benchmark import ROOT,OLD,digest


def fit_predict(y,design,train):
    """Frame-wise complex least squares; no test samples in amplitude fitting."""
    coefficients=[];train_sse=0.;test_sse=0.
    for frame in range(len(y)):
        x=design[frame];beta=np.linalg.lstsq(x[train],y[frame,train],rcond=None)[0]
        coefficients.append(beta)
        train_sse+=float(np.sum(np.abs(y[frame,train]-x[train]@beta)**2))
        test_sse+=float(np.sum(np.abs(y[frame,~train]-x[~train]@beta)**2))
    return train_sse,test_sse,np.array(coefficients)


def compare(y,reference,times,train,frequencies):
    def design(freq):return reference[None,:,None]*np.exp(2j*np.pi*times[:,:,None]*np.array(freq)[None,None,:])
    center=float(np.mean(frequencies));best=None
    # Search a continuous-like local grid for the one-source model, not just
    # the two stored candidate CFOs. The test SSE never chooses the frequency.
    for freq in center+np.arange(-1000.,1000.001,10.):
        fitted=fit_predict(y,design([freq]),train)
        if best is None or fitted[0]<best[0]:best=(*fitted,float(freq))
    two=design(frequencies);two_train,two_test,beta=fit_predict(y,two,train)
    normalized=two[0,train]/np.linalg.norm(two[0,train],axis=0)
    correlation=float(abs(np.vdot(normalized[:,0],normalized[:,1])))
    return dict(one_train_sse=best[0],one_test_sse=best[1],one_cfo_hz=best[3],
        one_frequency_grid_boundary=abs(best[3]-center)>=999.9,two_train_sse=two_train,two_test_sse=two_test,
        two_over_one_test_sse=two_test/best[1],template_correlation=correlation,
        normalized_design_condition=float(np.linalg.cond(normalized)),
        one_amplitude_median=float(np.median(np.abs(best[2]))),
        two_amplitude_medians=np.median(np.abs(beta),axis=0).tolist())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expanded',action='store_true');parser.add_argument('--coherent',action='store_true');parser.add_argument('--coherent-blocked',action='store_true');args=parser.parse_args();started=time.monotonic()
    if args.coherent_blocked:args.coherent=True
    sys.path.insert(0,str(OLD));import exhaustive_subset
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.analysis.starlink.templates import qin_edge_pilot_frame,FRAME_RATE_HZ,OFDM_SYMBOL_DURATION_S
    from leo.analysis.starlink.fractional_epoch import fractional_take,fractional_take_bounds
    folder=ROOT/('raw-peak-expanded' if args.expanded else 'raw-peak-replay')
    replay_path=folder/'replay.json';replay=json.loads(replay_path.read_text())
    output=folder/('coherent-frame-comparison.json' if args.coherent else 'two-source-tracking-cfo.json')
    if args.coherent_blocked:output=folder/'coherent-blocked-frame-comparison.json'
    if output.exists():raise FileExistsError(output)
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);results=[]
    try:
        for item in replay['results']:
            if time.monotonic()-started>300:raise TimeoutError('Pilot diagnostic exceeded five-minute budget')
            if not item['replay_matches_persisted']:raise ValueError('Replay not verified')
            session=item['session_id'];published=store.inspect(session)
            if published.manifest_sha256!=item['input_manifest_sha256']:raise ValueError('IQ binding changed')
            path=ROOT.parent/'2026_10_02_ds13_timing_em/scans'/session/'bundle.json'
            if digest(path)!=item['source_sha256'][str(path)]:raise ValueError('Metadata changed')
            row=json.loads(path.read_text())['alias_grouping']['representative_rows'][item['pair']['row_index']]
            vi,rx,_=item['probe_key'];visit,iq=store.read_visit_ci16(published,vi);fs=item['sample_rate_hz']
            samples=(iq[:fs//50,rx,0].astype(float)+1j*iq[:fs//50,rx,1].astype(float))/32768.
            frame=qin_edge_pilot_frame(fs,visit.event.target.edge)
            local=[];symbols=[]
            for symbol in range(2,66):
                rr=np.arange(round(symbol*fs*OFDM_SYMBOL_DURATION_S),round((symbol+1)*fs*OFDM_SYMBOL_DURATION_S))
                local.extend(rr);symbols.extend([symbol]*len(rr))
            local=np.array(local);symbols=np.array(symbols);fraction=row['fractional_epoch_offset_samples']
            lg,rg=fractional_take_bounds(fraction);absolute=[]
            for k in range(16):
                positions=row['integer_epoch_sample']+round(k*fs/FRAME_RATE_HZ)+local+fraction
                if positions.min()>=lg and positions.max()<len(samples)-rg:absolute.append(positions)
            absolute=np.array(absolute);received=fractional_take(samples,absolute)
            reference=np.asarray(frame[local],complex);times=absolute/fs
            frequencies=[r['tracking_cfo_hz'] for r in item['replayed']]
            if args.coherent:
                from coherent_pilot import compare_frames
                train_frames=np.arange(len(received))<len(received)//2 if args.coherent_blocked else np.arange(len(received))%2==0
                forward=compare_frames(received,reference,times,train_frames,frequencies,refine=args.coherent_blocked)
                reverse=compare_frames(received,reference,times,~train_frames,frequencies,refine=args.coherent_blocked)
            else:
                forward=compare(received,reference,times,symbols<34,frequencies)
                reverse=compare(received,reference,times,symbols>=34,frequencies)
            results.append(dict(scan=item['scan'],probe_key=item['probe_key'],frames=len(received),samples_per_frame=len(local),
                within_frame_span_s=float(np.ptp(times[0])),frequency_separation_hz=abs(np.diff(frequencies)[0]),
                tracking_frequencies_hz=frequencies,
                split=('contiguous frame blocks; training-only continuous frequency refinement' if args.coherent_blocked else 'alternating complete frames; common amplitudes across frames') if args.coherent else 'half symbols per frame; independent frame amplitudes',
                forward=forward,reverse=reverse))
            print(json.dumps(results[-1]),flush=True)
    finally:store.close()
    scope='Conditional common-amplitude phase-coherent pilot prediction across held-out frame splits (see per-result split). Not independent detector validation.' if args.coherent else __doc__
    with output.open('x') as stream:json.dump(dict(scope=scope,results=results,source_sha256=digest(replay_path),elapsed_s=time.monotonic()-started,
        limitations=['Raw-pilot least squares is not the original normalized GLRT likelihood.',
            'Assumes one common epoch and flat source gains; coherent variant further shares gains across frames. Multipath or frame-varying phase can invalidate this model.',
            'Nearly collinear templates cannot establish separate physical sources or satellite identities.',
            'No changes to coverage, denominator or assignments.']),stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
