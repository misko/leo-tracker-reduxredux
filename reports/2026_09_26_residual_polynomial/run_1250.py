"""All-track constant/quadratic comparison at independent fixed DS5 sites."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from polynomial_core import fit_residual

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_26_reno_track_audit'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,
    prepare_adaptive_tle_position_inputs,build_prediction_banks,
    RegionalTrackPredictionEvaluator,point_factory)
from probabilistic_core import fit_profiles,prior_weights,scale_at


def main():
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    history_path=HERE.parent/'2026_09_26_reno_track_audit/probabilistic_history.json'
    old=next(s for s in json.loads(source.read_text())['scans'] if s['session_id']=='scan-fw-d86e8f23c0624bac')
    history=json.loads(history_path.read_text())
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(old['session_id'],inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==old['evidence_sha256'] and p.snapshot_digest==old['snapshot_digest']
    lookup={str(cid):i for i,cid in enumerate(p.catalogue.satellite_numbers)}
    epochs=p.catalogue.element_epoch_utc_ns()
    taus=np.round(np.arange(-600,601)/10,1)
    rows=[]
    for track in p.tracks:
        ids={site:old['fixed_identities'][site][track.track_id]['candidate_id'] for site in ('sacramento','reno')}
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in sorted(set(ids.values()))],p.start_utc_ns,[track],taus_s=taus)
        for site,cid in ids.items():
            loc=old['sites'][site]
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=taus)(0,0):
                for i,c in enumerate(b.candidate_ids):
                    if str(c)!=cid:continue
                    assert b.visible[i]
                    age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12
                    profile=fit_profiles(b.measured_hz,b.predictions_hz[i],b.training_mask,100.)
                    j=int(np.argmax(profile['train']+prior_weights(taus,scale_at(age,history['bins']))))
                    residual=b.measured_hz-b.predictions_hz[i,j]
                    fits={str(d):fit_residual(track.times_s,residual,b.training_mask,d) for d in (0,2)}
                    rows.append({'site':site,'track_id':track.track_id,'satellite_id':cid,
                        'span_s':float(np.ptp(track.times_s)),'tau_s':float(taus[j]),
                        'timing_boundary':bool(j in (0,len(taus)-1)),
                        'training_count':int(np.sum(b.training_mask)),
                        'evaluation_count':int(np.sum(~np.asarray(b.training_mask,bool))), 'fits':fits})
    assert len(rows)==92 and len({(r['site'],r['track_id']) for r in rows})==92
    summary={}
    for site in ('sacramento','reno'):
        rr=[r for r in rows if r['site']==site]
        a=np.array([r['fits']['0']['evaluation_rms_hz'] for r in rr])
        b=np.array([r['fits']['2']['evaluation_rms_hz'] for r in rr])
        summary[site]={'tracks':len(rr),'improved':int(np.sum(b<a)),
            'timing_boundary_count':sum(r['timing_boundary'] for r in rr),
            'constant':dict(zip(('median','p90','max'),map(float,np.quantile(a,[.5,.9,1])))),
            'quadratic':dict(zip(('median','p90','max'),map(float,np.quantile(b,[.5,.9,1])))),
            'median_paired_reduction_percent':float(np.median(100*(1-b/a))),
            'median_quadratic_correction_range_hz':float(np.median([r['fits']['2']['training_shape_peak_to_peak_hz'] for r in rr]))}
    out={'session_id':old['session_id'],'sites':{s:old['sites'][s] for s in summary},
        'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'history_sha256':hashlib.sha256(history_path.read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'core_sha256':hashlib.sha256((HERE/'polynomial_core.py').read_bytes()).hexdigest(),
        'protocol':'92 track/site fits. DS5 training-only zero-timing IDs frozen independently per site. '
            'Independent per-track timing MAP on +/-60s grid step0.1 using previous age t4 prior and robust100Hz likelihood. '
            'Timing then frozen; degree0 and degree2 OLS corrections training-only; no quadratic retiming/reassignment. '
            'Original reused evaluation masks, equal track weights, uncapped RMS. Not production assignments, '
            'not shared-satellite timing, not empirical-prior model, not independent validation or a geographic search.',
        'summary':summary,'rows':rows}
    (HERE/'results_1250.json').write_text(json.dumps(out,indent=2)+'\n')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    colors={'sacramento':'#2369ad','reno':'#ce6525'}
    all_values=[]
    for site in summary:
        rr=[r for r in rows if r['site']==site]
        a=np.array([r['fits']['0']['evaluation_rms_hz'] for r in rr])
        b=np.array([r['fits']['2']['evaluation_rms_hz'] for r in rr])
        for values,label,style in ((a,'constant','-'),(b,'quadratic','--')):
            x=np.sort(values)
            axs[0].step(x,np.arange(1,len(x)+1)/len(x)*100,where='post',color=colors[site],ls=style,label=f'{site.title()} — {label}')
        axs[1].scatter(a,b,color=colors[site],marker='o' if site=='sacramento' else '^',alpha=.75,label=site.title())
        all_values.extend(a);all_values.extend(b)
    lo=min(all_values)*.8;hi=max(all_values)*1.2
    axs[1].plot([lo,hi],[lo,hi],color='gray',ls=':',label='No change')
    axs[0].set(xscale='log',xlabel='Evaluation RMS (Hz)',ylabel='Tracks at or below RMS (%)',title='Distribution across all 46 tracks')
    axs[1].set(xscale='log',yscale='log',xlim=(lo,hi),ylim=(lo,hi),xlabel='Constant residual RMS (Hz)',ylabel='Quadratic residual RMS (Hz)',title='Each track: below diagonal = improvement')
    for ax in axs:ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.suptitle('12:50 UTC • Sacramento error 13.4 km; Reno error 706.8 km\nTraining-fitted corrections; original evaluation observations; fixed IDs and timing')
    fig.savefig(HERE/'distribution_1250.png',dpi=170)
    plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
