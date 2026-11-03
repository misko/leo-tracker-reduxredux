"""Independent RF/gate replay before report-only geographic evaluation."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_converter_drift import change_scan
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import summary
from probe_ds23_converter_drift import OUT,ARMS,LAWS,prepare,valid
from run_algo01_ds23_sample import ROOT,read,write,sha


def verify_case(case):
    path=OUT/(case+'_result.json');saved=read(path)
    metadata_path=OUT/(case+'_converter.json');metadata=read(metadata_path);geometry=metadata['geometry']
    if sha(metadata_path)!=saved['metadata_sha256']:raise ValueError('recorded converter metadata changed')
    if metadata['source_sha256']!=sha(ROOT/'tools/export_ds23_converter_geometry.py'):
        raise ValueError('metadata export implementation changed')
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    if binding!=saved['incumbent_binding'] or signed['policy_arms']!=saved['incumbent_arms']:
        raise ValueError('signed incumbent changed')
    np.testing.assert_array_equal(keep,saved['original_mask'])
    checks=[];fresh_methods={};null_valid=None
    for law in ('RF',)+LAWS:
        changed,receipt=change_scan(scan,geometry,law)
        if changed.tracks is not scan.tracks:raise ValueError('converter experiment changed observations')
        if law!='RF' and receipt!=saved['methods'][law]['receiver_loading_receipt']:
            raise ValueError('receiver covariance loading changed')
        # Independently reconstruct each physical design loading, including
        # the fixed-target RMS normalization; no fitted coefficient is used.
        targets=geometry['targets'];rf=np.array([t['rf_center_hz'] for t in targets],float)
        frequencies=np.array([t['lnb_lo_hz'] if law=='LNB' else t['if_center_hz'] if law=='tuner' else t['rf_center_hz'] for t in targets],float)
        norm=1/11.5e9 if law=='RF' else np.sqrt(np.mean((rf/11.5e9)**2)/np.mean(frequencies**2))
        by_channel={t['channel']:t['lnb_lo_hz'] for t in targets}
        for track,before,after in zip(scan.tracks,scan.rx_basis,changed.rx_basis,strict=True):
            f=track['rf_hz'] if law=='RF' else by_channel[track['channel']] if law=='LNB' else track['rf_hz']-by_channel[track['channel']]
            np.testing.assert_allclose((track['rf_hz']/11.5e9)*after,f*norm*before,atol=1e-12,rtol=1e-12)
            if after.shape!=before.shape:raise ValueError('nuisance count changed')
        pair={}
        for arm in ARMS:
            r=saved['cold_RF_null_arms'][arm] if law=='RF' else saved['methods'][law]['arms'][arm]
            p=make_event_problem(changed,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,[])
            attach_event_predictive(p,entries,powers)
            np.testing.assert_array_equal(p.q,base.q)
            x=np.asarray(r['endpoint_east_north_km']);fresh=summary(p,x,entries)
            fresh['final_phase_change_s']=r['final_phase_change_s']
            difference=fresh['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(difference)>1e-3:raise ValueError('RF objective replay failed')
            actual=[g['compatible'] for g in fresh['gates']['tracks']+fresh['linear_gates']]
            expected=[g['compatible'] for g in r['gates']['tracks']+r['linear_gates']]
            if actual!=expected:raise ValueError('original residual or predictive gates changed')
            if fresh['linear_calibration_max_difference']>1e-10:raise ValueError('predictive points teach radio calibration')
            pair[arm]=fresh;checks.append(dict(law=law,arm=arm,RF_difference=difference,
                curved_points=int(p.keep.sum()),predictive_points=sum(e['points'] for e in entries)))
        accepted=valid(pair,base.labels)
        if law=='RF':
            null_valid=accepted
            if null_valid!=saved['cold_RF_null_paired_valid']:raise ValueError('cold null acceptance changed')
        else:
            if accepted!=saved['methods'][law]['accepted']:raise ValueError('law acceptance changed')
            if saved['methods'][law]['policy_arms']!=(saved['methods'][law]['arms'] if accepted else saved['incumbent_arms']):
                raise ValueError('fixed-law policy fallback changed')
            fresh_methods[law]=pair
    reference={a:min(saved['incumbent_arms'][a]['negative_twice_elbo'],saved['cold_RF_null_arms'][a]['negative_twice_elbo'])
               if null_valid else saved['incumbent_arms'][a]['negative_twice_elbo'] for a in ARMS}
    if reference!=saved['reference_costs']:raise ValueError('control reference changed')
    eligible=[]
    for law,pair in fresh_methods.items():
        gains={a:reference[a]-pair[a]['negative_twice_elbo'] for a in ARMS}
        np.testing.assert_allclose(list(gains.values()),list(saved['methods'][law]['RF_gains'].values()),atol=1e-3,rtol=0)
        if saved['methods'][law]['accepted'] and min(gains.values())>2*np.log(3):eligible.append(law)
    selected=min(eligible,key=lambda law:fresh_methods[law]['c0']['negative_twice_elbo']) if eligible else None
    if selected!=saved['RF_selected_law'] or saved['RF_selected_policy_arms']!=(saved['methods'][selected]['arms'] if selected else saved['incumbent_arms']):
        raise ValueError('RF-selected law or exact fallback changed')
    return dict(case=case,result_sha256=sha(path),checks=checks,no_GPS_used=True)


def verify(part):
    p=prepare();cases=p['pilot_cases'] if part=='pilot' else p['development_cases']+p['confirmation_cases']
    rows=[];errors=[]
    with ProcessPoolExecutor(max_workers=min(16,len(cases))) as pool:
        jobs={pool.submit(verify_case,c):c for c in cases}
        for f in as_completed(jobs):
            try:rows.append(f.result())
            except Exception as exc:errors.append(dict(case=jobs[f],error=repr(exc)))
    write(OUT/(part+'_verification.json'),dict(all_terminal=True,qualified=not errors and len(rows)==len(cases),
        receipts=rows,errors=errors,no_GPS_used=True))
    print('Verified',len(rows),'errors',errors,flush=True)


def stats(values):
    v=np.asarray(values)
    return dict(count=len(v),mean_km=float(np.mean(v)),median_km=float(np.median(v)),p90_km=float(np.quantile(v,.9)),below_half_km=int(np.sum(v<=.5)))


def evaluate():
    protocol=prepare();audit=read(OUT/'cohort_verification.json')
    if not audit['qualified'] or len(audit['receipts'])!=40:raise ValueError('all RF replays required before geographic evaluation')
    from report_algo02_ds23 import position_error
    bindings={r['case']:r for r in audit['receipts']};results={};rows=[]
    figure,axes=plt.subplots(2,2,figsize=(14,9))
    for row,cohort in enumerate(('development','confirmation')):
        results[cohort]={}
        for col,arm in enumerate(ARMS):
            values={k:[] for k in ('incumbent','cold_RF','LNB','tuner','RF_selected')}
            for case in protocol[cohort+'_cases']:
                path=OUT/(case+'_result.json')
                if sha(path)!=bindings[case]['result_sha256']:raise ValueError('verified fit changed')
                r=read(path);original=r['incumbent_arms'][arm];before=position_error(original['endpoint_latlon'])
                values['incumbent'].append(before)
                null=r['cold_RF_null_arms'][arm] if r['cold_RF_null_paired_valid'] else original
                values['cold_RF'].append(position_error(null['endpoint_latlon']))
                for method in ('LNB','tuner','RF_selected'):
                    after=r['RF_selected_policy_arms'][arm] if method=='RF_selected' else r['methods'][method]['policy_arms'][arm]
                    error=position_error(after['endpoint_latlon']);values[method].append(error)
                    rows.append(dict(case=case,cohort=cohort,arm=arm,method=method,
                        accepted=r['RF_selected_law'] is not None if method=='RF_selected' else r['methods'][method]['accepted'],
                        format=read(OUT/(case+'_converter.json'))['format'],incumbent_error_km=before,policy_error_km=error,
                        RF_bound_gain=original['negative_twice_elbo']-after['negative_twice_elbo'],
                        RF_RMS_before_hz=original['RMS_hz'],RF_RMS_after_hz=after['RMS_hz']))
            results[cohort][arm]={k:stats(v) for k,v in values.items()}
            for method in ('LNB','tuner','RF_selected'):
                results[cohort][arm][method]['mean_and_median_improve']=bool(np.mean(values[method])<np.mean(values['incumbent']) and np.median(values[method])<np.median(values['incumbent']))
            ax=axes[row,col]
            for method,color,label in (('incumbent','black','Signed RF-scaled incumbent'),('LNB','#4778ab','LNB-scaled drift'),('tuner','#bd793c','Tuner-IF-scaled drift'),('RF_selected','#8a62a4','RF-selected law')):
                a=np.sort(values[method]);ax.step(np.r_[0,a],np.r_[0,np.arange(1,len(a)+1)/len(a)],where='post',color=color,label=label)
            ax.axvline(.5,color='gray',ls=':');ax.grid(alpha=.15);ax.legend(fontsize=8)
            ax.set(title=cohort+' · '+arm,xlabel='Position error (km)',ylabel='Fraction of complete cohort',ylim=(0,1.02))
    figure.suptitle('DS23 · recorded converter frequency law for receiver nonlinear drift\nSame nuisance count, fixed-grid prior variance, observations, satellite Doppler scales and original gates')
    figure.tight_layout(rect=(0,0,1,.92));figure.savefig(OUT/'position_error_distribution.png',dpi=175);plt.close(figure)
    primary=all(results[c]['fitted_c']['LNB']['mean_and_median_improve'] for c in results)
    secondary={m:all(results[c]['fitted_c'][m]['mean_and_median_improve'] for c in results) for m in ('tuner','RF_selected')}
    write(OUT/'evaluation.json',dict(results=results,primary_confirmed=primary,secondary_confirmed=secondary,
        count=40,goal_population=413,goal_achieved=False,GPS_used_only_here=True,
        RF_score_and_position_changes_reported_separately=True,
        conditional_on_recorded_reference_hypotheses=True,verification_sha256=sha(OUT/'cohort_verification.json')))
    with (OUT/'position_comparison.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    print('Primary',primary,'secondary',secondary,'results',results,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('verify-pilot','verify-cohort','evaluate'),required=True)
    stage=parser.parse_args().stage
    evaluate() if stage=='evaluate' else verify('pilot' if stage=='verify-pilot' else 'cohort')
