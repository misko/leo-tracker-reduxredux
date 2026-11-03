"""Audit frequency-regularized selection against both preserved prior controls."""
import csv
import json
from pathlib import Path
import numpy as np
from frequency_associations import OUT,PREVIOUS,SCANS,ARMS,MODE,OLD_INPUTS
from frequency_localization import read_input,BUDGET,make_objective,diagnostics
from timing_selection_score import timing_cost
from audit_regularized_selection import selection_changes
from timing_bound_comparison import digest
from subset_positions import serial
from regularized_localization import read_input as read_previous


def validate_selection(r):
    assert r['zero_frequency_control_exact'] and not r['heldout_original_rows']
    v=r['final'];a=v['assignments'];selected=v['selected']
    assert len(a)==v['assigned']==len({x['row_index'] for x in a})
    assert len(r['original_rows'])==v['denominator']
    assert set(x['row_index'] for x in a)<=set(r['original_rows'])
    assert len(selected)==v['satellites']==len({x['catalog_number'] for x in selected})
    assert {x['catalog_number'] for x in a}=={x['catalog_number'] for x in selected}
    errors=np.array([x['residual_hz'] for x in a]);timing=np.array([x['offset_s'] for x in selected])
    assert np.max(abs(errors))<=600.+1e-7 and np.max(abs(timing))<=20.+1e-7
    for x in selected:assert x['count']==sum(y['catalog_number']==x['catalog_number'] for y in a)
    frequency=float(.5*np.sum((errors/200.)**2));prior=float(timing_cost(len(timing),timing.sum(),timing@timing))
    score=len(a)-10*len(timing)-prior-frequency
    assert abs(score-v['objective'])<1e-7
    assert abs(frequency-v['frequency_cost'])<1e-7
    assert abs(prior-v['timing_prior_nll'])<1e-7
    assert abs(np.sqrt(np.mean(errors**2))-r['rms_hz'])<1e-7
    return dict(scan=r['scan'],arm=r['arm'],mode=MODE,windows=len(a),denominator=v['denominator'],
        coverage=v['coverage'],satellites=len(selected),rms_hz=r['rms_hz'],
        timing_prior_nll=prior,gaussian_residual_cost=frequency,primary_selection_score=score,
        converged=r['converged'])


def main(polished=False):
    report_root=OUT/'polished' if polished else OUT
    old_report=json.loads((PREVIOUS/'polished/audit.json').read_text())
    rows=old_report['rows'].copy();associations=old_report['associations'].copy();changes=[]
    if polished:
        for row in rows:
            scan,arm,mode=row['scan'],row['arm'],row['mode']
            path=report_root/scan/f'{arm}-{mode}-position.json';r=json.loads(path.read_text())
            data,meta=read_previous(scan,mode)
            assert r['input_sha256']==meta['input_sha256'] and r['final_polish_budget_s']==10.
            assert r['pre_final_source_sha256']==digest(PREVIOUS/'polished'/scan/f'{arm}-{mode}-position.json')
            values=diagnostics(make_objective(data,meta,arm),data,r['best'])
            for key in ('objective','kkt','distance_m'):assert abs(r[key]-values[key])<1e-7
            row.update(values,receipt_sha256=digest(path))
    for scan in SCANS:
        data,meta=read_input(scan)
        assert meta['control_input_reproduced']
        assert meta['association_sha256']==digest(OUT/scan/'fitted-c.json')
        parent_meta=json.loads((OLD_INPUTS/scan/'input.json').read_text())
        pool_path=Path(parent_meta['association_source']).with_name('candidate-pool.json')
        pool=json.loads(pool_path.read_text());lookup={int(r):i for i,r in enumerate(pool['original_rows'])}
        for arm in ARMS:
            selection=json.loads((OUT/scan/f'{arm}.json').read_text())
            assert selection['source_sha256']==digest(pool_path)
            assert selection['previous_source_sha256']==digest(PREVIOUS/scan/f'{arm}-timing-regularized.json')
            associations.append(validate_selection(selection))
            # Reconstruct every exported residual from the unmodified input mode.
            for track in selection['final']['selected']:
                m=pool['arms'][arm][track['mode_index']]
                assert (m['catalog_number'],m['offset_s'])==(track['catalog_number'],track['offset_s'])
                expected=dict(zip(m['eligible_rows'],m['residual_hz']))
                for a in selection['final']['assignments']:
                    if a['catalog_number']==track['catalog_number']:
                        assert abs(a['residual_hz']-expected[lookup[a['row_index']]])<1e-7
            baseline=json.loads((PREVIOUS/scan/f'{arm}-count-control.json').read_text())
            changes.append(dict(scan=scan,arm=arm,**selection_changes(baseline,selection)))
            path=report_root/scan/f'{arm}-{MODE}-position.json' if polished else OUT/scan/f'{arm}-position.json'
            r=json.loads(path.read_text())
            assert r['input_sha256']==meta['input_sha256']
            assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
            assert r['heldout_original_rows']==[] and r['numbers']==data.numbers.tolist()
            control_path=report_root/scan/f'{arm}-count-control-position.json' if polished else PREVIOUS/'polished'/scan/f'{arm}-count-control-position.json'
            control=json.loads(control_path.read_text())
            for key in ('maximum_budgets_s','extra_polish_budget_s','roof_starts','spatial_starts','radius_km','total_timing_bound_s'):
                assert r[key]==control[key],(scan,arm,key)
            if polished:
                assert r['final_polish_budget_s']==control['final_polish_budget_s']==10.
                assert r['pre_final_source_sha256']==digest(OUT/scan/f'{arm}-position.json')
            values=diagnostics(make_objective(data,meta,arm),data,r['best'])
            for key in ('objective','kkt','distance_m'):assert abs(r[key]-values[key])<1e-7
            assert r['converged']==values['converged']
            if arm=='zero-c':assert abs(r['best']['coefficient'])<1e-10
            rows.append(dict(scan=scan,arm=arm,mode=MODE,windows=len(data.times),satellites=len(data.numbers),
                coverage=len(data.times)/meta['full_top_window_denominator'],**values,receipt_sha256=digest(path)))
    cohort=[]
    modes=('count-control','timing-regularized',MODE)
    for arm in ARMS:
        for mode in modes:
            part=[r for r in rows if r['arm']==arm and r['mode']==mode]
            errors=np.array([r['distance_m'] for r in part])
            coverage=[a for a in associations if a['arm']==arm and a['mode']==mode]
            total=sum(r['windows'] for r in coverage);denominator=sum(r['denominator'] for r in coverage)
            cohort.append(dict(arm=arm,mode=mode,scans=len(part),below_1km=int(sum(errors<1000)),
                converged_below_1km=int(sum(r['distance_m']<1000 and r['converged'] for r in part)),
                median_error_m=float(np.median(errors)),mean_error_m=float(np.mean(errors)),
                unconverged=sum(not r['converged'] for r in part),boundary=sum(r['boundary'] for r in part),
                associated_windows=total,all_passing_top_windows=denominator,coverage=total/denominator,
                pooled_association_rms_hz=float(np.sqrt(sum(r['windows']*r['rms_hz']**2 for r in coverage)/total))))
    report=dict(status='passed',scope=__doc__,prior_audit_sha256=digest(PREVIOUS/'polished/audit.json'),
        new_position_cases=32,new_association_controls=32,cohort=cohort,rows=rows,associations=associations,changes=changes,
        notes=['One fixed residual weight 1 and sigma 200 Hz across all scans, no truth-selected deletions.',
            'Original coherent 600 Hz support and archived candidate/RX/TLE pool retained.',
            'All selected windows used for position fit; no new holdouts. Both RF position arms share fitted-c membership.',
            'Matched maximum search budgets with preserved count control. No global-minimum certificate.',
            'Changing the data/bank prevents absolute NLL comparisons across selection methods.'])
    (report_root/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    for name,values in [('position-summary.csv',rows),('association-summary.csv',associations)]:
        keys=list(dict.fromkeys(k for r in values for k in r))
        with (report_root/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(values)
    print(json.dumps(cohort,default=serial,indent=2));render(report,report_root)


def render(report,report_root=OUT):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    colors=['#777777','#e69f00','#0072b2'];modes=['count-control','timing-regularized',MODE]
    labels=['Count control','Timing cost only','Timing + frequency cost']
    fig,axes=plt.subplots(3,1,figsize=(15,12),sharex=True)
    for ax,arm in zip(axes[:2],ARMS):
        for i,scan in enumerate(SCANS):
            part=[next(r for r in report['rows'] if (r['scan'],r['arm'],r['mode'])==(scan,arm,m)) for m in modes]
            ax.plot(np.arange(3)*.16+i-.16,[r['distance_m'] for r in part],color='.8',lw=1)
            for dx,r,color in zip([-.16,0,.16],part,colors):
                ax.scatter(i+dx,r['distance_m'],s=48,c=color,marker='^' if r['boundary'] else 'o')
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],s=55,c='black',marker='x')
            ax.annotate(f"{part[-1]['distance_m']:.0f}",(i+.16,part[-1]['distance_m']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=8,color=colors[-1])
        summaries=[next(c for c in report['cohort'] if c['arm']==arm and c['mode']==m) for m in modes]
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+' · below 1 km: '+' → '.join(str(c['below_1km']) for c in summaries)+' of 16')
        ax.set_ylabel('Position error (m)');ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.5',ls=':');ax.set_ylim(0,4480)
    ax=axes[2]
    for m,color,label in zip(modes,colors,labels):
        values=[next(a for a in report['associations'] if (a['scan'],a['arm'],a['mode'])==(s,'fitted-c',m)) for s in SCANS]
        ax.plot(range(16),[100*r['coverage'] for r in values],'o-',color=color,label=label)
    ax.set_title('Fitted-c association coverage; same selected windows used in BOTH position RF arms')
    ax.set_ylabel('All passing top windows assigned (%)');ax.set_ylim(45,100);ax.legend(loc='lower right')
    ax.set_xticks(range(16),SCANS)
    for ax in axes:ax.grid(axis='y',alpha=.18)
    handles=[Line2D([],[],marker='o',color=c,ls='none',label=l) for c,l in zip(colors,labels)]
    handles += [Line2D([],[],marker=m,color='.3',ls='none',label=l) for m,l in [('x','Unconverged'),('^','4 km boundary')]]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.064),ncol=5,frameon=False)
    fig.suptitle('Does continuous Doppler quality improve satellite selection and localization?',fontsize=17)
    fig.text(.5,.013,'New primary score = assigned windows − 10 × satellites − timing cost − ½Σ(residual / 200 Hz)². Weights fixed at 1.\n'
        'Identical archived candidate pool, RX/TLE calibration and 600 Hz coherence gate. Independent 4 km position searches.\n'
        'Original localization likelihood/priors; matched search budgets. No truth-position prior or per-scan truth-selected model.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.105,1,.96));fig.savefig(report_root/'position-coverage-comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--polished',action='store_true');args=parser.parse_args()
    main(args.polished)
