"""Report sealed transfer outputs; no inference, propagation or selection."""

import csv
import json
import os
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(HERE/'.mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Same fixed reporter-only evaluation position and distance as sealed R2.
SITE=(37.849061591561885, -122.48574968092912)
CENTER=(37.906, -122.545)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distance(x):
    east,north=x
    ll=[CENTER[0]+north/111., CENTER[1]+east/(111.32*np.cos(np.radians(CENTER[0])))]
    a,b=np.radians([ll,SITE]); h=np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def save(fig,name,caption):
    fig.text(.5,.012,caption,ha='center',va='bottom',fontsize=8)
    fig.tight_layout(rect=(0,.07,1,.96))
    for suffix in ('.png','.pdf'):
        fig.savefig(HERE/'figures'/(name+suffix),dpi=160)
    plt.close(fig)


def main():
    seal=read(HERE/'RF_seal.json')
    for path,digest in seal['files'].items():
        if sha(path)!=digest: raise ValueError('RF output changed: '+path)
    panel=read(HERE/'panel.json')['panel']; result=read(HERE/'execution_result.json')
    rows=[]; coordinate_checks=[]
    (HERE/'figures').mkdir(exist_ok=False)
    for target in panel:
        case=target['case']; parent=read(target['parent_ledger_path'])
        for arm in ('c0','fitted_c'):
            fit=next((v for v in result['fits']+result['skipped'] if v['case']==case and v['arm']==arm),None)
            base=parent['original_positions_and_references'][arm]
            rawpath=HERE/'fits'/case/arm/'raw_endpoint.json'
            raw=read(rawpath) if rawpath.exists() else {}
            x=fit.get('endpoint_east_north_km',raw.get('endpoint_east_north_km'))
            error=distance(x) if x is not None else None
            base_error=distance(base['endpoint_east_north_km'])
            gatespath=HERE/'fits'/case/arm/'parent_gates.json'
            gates=read(gatespath) if gatespath.exists() else {}
            summary=gates.get('original_summary',{})
            accepted=set(parent['coverage'][arm]['accepted_observation_ids'])
            endpoint=set(gates.get('endpoint_compatible_IDs_after_target_exclusion',[]))
            rows.append(dict(case=case,arm=arm,model_family=target['candidate_norad'],
                experimental_target_points=target['points'],status=fit['status'],
                parent_qualified=fit.get('parent_qualified',False),
                numerical_qualified=fit.get('numerical_qualified',False),
                baseline_error_km=base_error,diagnostic_error_km=error,
                error_change_km=error-base_error if error is not None else None,
                baseline_curved_RMS_hz=base['RMS_hz'],diagnostic_curved_RMS_hz=summary.get('RMS_hz'),
                original_parent_likelihood_IDs_preserved=gates.get('exact_original_parent_likelihood_IDs'),
                original_parent_accepted_IDs_preserved=gates.get('original_parent_accepted_IDs_preserved'),
                missing_original_accepted_IDs=len(accepted-endpoint) if gates else None,
                parent_gate_pass=gates.get('original_single_arm_valid'),
                RF_position_shift_km=float(np.linalg.norm(np.asarray(x)-base['endpoint_east_north_km'])) if x is not None else None,
                target_accepted_association_points=0,target_association_qualified=False,
                operational_policy='saved_baseline',operational_error_km=base_error,
                seconds=fit.get('seconds')))
    with (HERE/'evaluation.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,arm in zip(axes,('c0','fitted_c')):
        rr=[v for v in rows if v['arm']==arm]
        at=np.arange(len(rr));ax.bar(at-.18,[v['baseline_error_km'] for v in rr],.36,label='Saved baseline',color='0.6')
        bars=ax.bar(at+.18,[v['diagnostic_error_km'] or 0 for v in rr],.36,label='Diagnostic predictive prior',color='#0072B2')
        for bar,row in zip(bars,rr):
            if not(row['parent_qualified'] and row['numerical_qualified']):bar.set_hatch('///');bar.set_alpha(.45)
        ax.set_xticks(at,[v['case'].replace('DS24-','') for v in rr]);ax.set(title=arm,ylabel='Geographic error (km)');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=9);fig.suptitle('Chronological transfer panel: every attempted outcome retained')
    save(fig,'geographic_transfer','Hatchets mark unqualified diagnostics. New target associations remain unqualified in every row; operational errors equal baseline.\nGeography was evaluated after RF sealing; four previously exposed same-site scans, no new-location claim.')

    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,arm in zip(axes,('c0','fitted_c')):
        for index,branch in enumerate(('predictive_shape_zero','predictive_shape_prior')):
            values=[]
            for target in panel:
                preflight=read(HERE/'preflight'/target['case']/'result.json')
                ctx=next((v for v in preflight['contexts'] if v['arm']==arm and v['branch']==branch),None)
                values.append(float(np.linalg.norm(ctx['frozen_gradient'])) if ctx else 0.)
            ax.bar(np.arange(len(panel))+(index-.5)*.36,values,.36,label=branch.replace('predictive_shape_',''))
        ax.set_xticks(np.arange(len(panel)),[v['case'].replace('DS24-','') for v in panel]);ax.set(title=arm,ylabel='Target NLL gradient norm (objective/km)');ax.grid(axis='y',alpha=.2)
    axes[0].legend();fig.suptitle('Zero versus physical-prior influence at each fixed saved baseline')
    save(fig,'fixed_target_gradients','Exact same observations, candidate, phase prior and saved parent reference; central differences at +/-10m.\nGradient magnitude is conditional model influence, not position accuracy or calibrated information.')

    nativefig,nativeaxes=plt.subplots(len(panel),2,figsize=(12,3*len(panel)),squeeze=False)
    residualfig,residualaxes=plt.subplots(len(panel),2,figsize=(12,3*len(panel)),squeeze=False)
    for rowindex,target in enumerate(panel):
        case=target['case']; observations=read(Path('/srv/bulk/leo/research/ds25-20261024')/case/'observations.json')
        lookup={v['observation_id']:v for v in observations}; native=np.array([lookup[i]['measured_cfo_hz'] for i in target['observation_ids']])
        tracks=read(Path('/srv/bulk/leo/research/ds25-20261024')/case/'tracks.json');track=next(v for v in tracks if v['key']==target['component'])
        times=np.asarray(track['times'])
        for col,arm in enumerate(('c0','fitted_c')):
            ax=nativeaxes[rowindex,col];rx=residualaxes[rowindex,col]
            ax.scatter(times,native/1000,s=12,color='0.3',label='Unqualified native source')
            path=HERE/'fits'/case/arm/'rf_diagnostics.json'
            if path.exists():
                d=read(path)
                if d['target_observation_ids']!=target['observation_ids']:raise ValueError('plot target IDs changed')
                residual=np.asarray(d['target_phase_marginal_mean_residual_hz']);prediction=native-residual
                breaks=np.r_[False,(abs(np.diff(native))>1/(4.4e-6)/2)|(np.diff(times)>10)]
                tt=[];ff=[]
                for index in range(len(times)):
                    if breaks[index]:tt.append(np.nan);ff.append(np.nan)
                    tt.append(times[index]);ff.append(prediction[index]/1000)
                ax.plot(tt,ff,color='#0072B2',label='Descriptive phase-marginal mean')
                rx.plot(times,residual,'.-',color='#0072B2')
                coordinate_checks.append(dict(case=case,arm=arm,points=len(times),
                    maximum_native_prediction_plus_residual_error_hz=float(max(abs(prediction+residual-native)))))
            else:rx.text(.5,.5,'No qualified fit attempted',ha='center',transform=rx.transAxes)
            ax.set(title=f'{case} / {arm} / model {target["candidate_norad"]}',ylabel='Native CFO (kHz)',xlabel='Scan time(s)')
            rx.set(title=f'{case} / {arm}',ylabel='Descriptive residual (Hz)',xlabel='Scan time(s)');rx.axhline(0,color='0.5',lw=.8)
            ax.grid(alpha=.2);rx.grid(alpha=.2)
    nativeaxes[0,0].legend(fontsize=8)
    save(nativefig,'target_native_cfo','Observed source and prediction share exact native IDs/gauge; alias jumps and long gaps are broken. No target identity validation.\nPrediction omits target-local constant/shape posterior mean corrections; target data condition phase.')
    save(residualfig,'target_residuals','Source minus parent radio/E-conditional mean and target phase-posterior orbit mean. Target constant/shape adjustments omitted.\nThese are descriptive residuals, not held-out prediction, full-fit RMS or calibrated orbit corrections.')

    aggregates={}
    for arm in ('c0','fitted_c'):
        rr=[v for v in rows if v['arm']==arm and v['diagnostic_error_km'] is not None]
        aggregates[arm]=dict(attempted_endpoint_count=len(rr),all_attempted_baseline_mean_km=float(np.mean([v['baseline_error_km'] for v in rr])),
            all_attempted_diagnostic_mean_km=float(np.mean([v['diagnostic_error_km'] for v in rr])),
            baseline_median_km=float(np.median([v['baseline_error_km'] for v in rr])),
            diagnostic_median_km=float(np.median([v['diagnostic_error_km'] for v in rr])),
            baseline_max_km=max(v['baseline_error_km'] for v in rr),diagnostic_max_km=max(v['diagnostic_error_km'] for v in rr),
            geographic_regressions=sum(v['error_change_km']>0 for v in rr),
            parent_qualification_failures=sum(not v['parent_qualified'] for v in rr)) if rr else dict(attempted_endpoint_count=0)
    summary=dict(RF_seal_sha256=sha(HERE/'RF_seal.json'),source_sha256=sha(Path(__file__)),
        evaluation_position=SITE,existing_R2_reporter_source_sha256=sha(Path('/srv/bulk/leo/research/ds24-uncertain-new-family-r01/evaluation/evaluate.py')),
        no_new_fits_or_propagation=True,rows=rows,all_attempted_endpoint_aggregates=aggregates,
        plot_native_ID_coordinate_checks=coordinate_checks,
        operational_policy='saved_baseline',target_association_qualified=False)
    with (HERE/'evaluation_summary.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
    files=[HERE/'evaluation.csv',HERE/'evaluation_summary.json',Path(__file__),*sorted((HERE/'figures').iterdir())]
    with (HERE/'report_seal.json').open('x') as stream:json.dump(dict(files={str(p):sha(p) for p in files},RF_seal_sha256=sha(HERE/'RF_seal.json')),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(rows=rows,aggregates=aggregates),indent=2))


if __name__=='__main__':main()
