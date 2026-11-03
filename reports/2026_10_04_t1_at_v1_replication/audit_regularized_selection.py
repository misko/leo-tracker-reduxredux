"""Verify selection controls, exclusive coverage, matched RF fits and stationarity."""
import csv
import json
from pathlib import Path
import numpy as np
from regularized_associations import OUT,SCANS,ARMS,MODES,OLD_INPUTS
from regularized_localization import read_input,make_objective,diagnostics,SOURCE,BUDGET
from timing_selection_score import timing_cost
from timing_bound_comparison import digest
from subset_positions import serial


def selection_changes(old,new):
    a={int(x['catalog_number']):x for x in old['final']['selected']}
    b={int(x['catalog_number']):x for x in new['final']['selected']}
    assignments=[{int(x['row_index']):int(x['catalog_number']) for x in r['final']['assignments']} for r in (old,new)]
    return dict(removed=[a[n] for n in sorted(a.keys()-b.keys())],
        added=[b[n] for n in sorted(b.keys()-a.keys())],
        changed_timing=[dict(satellite=n,old_offset_s=a[n]['offset_s'],new_offset_s=b[n]['offset_s'],
            old_windows=a[n]['count'],new_windows=b[n]['count']) for n in sorted(a.keys()&b.keys())
            if a[n]['offset_s']!=b[n]['offset_s']],
        lost_windows=len(assignments[0].keys()-assignments[1].keys()),
        gained_windows=len(assignments[1].keys()-assignments[0].keys()),
        relabeled_windows=sum(assignments[0][i]!=assignments[1][i] for i in assignments[0].keys()&assignments[1].keys()))


def audit(position_root=OUT):
    rows=[];associations=[];changes=[];controls=0
    for scan in SCANS:
        old_meta=json.loads((OLD_INPUTS/scan/'input.json').read_text())
        anchor={}
        for arm in ARMS:
            selections={}
            old_path=Path(old_meta['association_source']).with_name(f'{arm}.json')
            old=json.loads(old_path.read_text())
            for mode,weight in MODES.items():
                path=OUT/scan/f'{arm}-{mode}.json';r=json.loads(path.read_text());last=r['final']
                assert r['baseline_source_sha256']==digest(old_path)
                assert r['source_sha256']==digest(old_path.with_name('candidate-pool.json'))
                assert r['heldout_original_rows']==[]
                assert len(r['original_rows'])==last['denominator']
                chosen=last['selected'];assignments=last['assignments']
                assert len(assignments)==last['assigned']==len({a['row_index'] for a in assignments})
                assert set(a['row_index'] for a in assignments)<=set(r['original_rows'])
                assert len(chosen)==last['satellites']==len({x['catalog_number'] for x in chosen})
                assert {a['catalog_number'] for a in assignments}=={x['catalog_number'] for x in chosen}
                timing=np.array([x['offset_s'] for x in chosen]);prior=float(timing_cost(len(timing),sum(timing),timing@timing))
                assert abs(prior-last['timing_prior_nll'])<1e-7
                assert abs(last['objective']-(last['assigned']-10*len(timing)-weight*prior))<1e-7
                for x in chosen:
                    assert x['count']==sum(a['catalog_number']==x['catalog_number'] for a in assignments)
                assert max(abs(a['residual_hz']) for a in assignments)<=600.+1e-7
                if weight==0:
                    for stage in ('initial','final'):
                        for key in ('assignments','selected','objective'):assert r[stage][key]==old[stage][key]
                    controls+=1
                selections[mode]=r
                associations.append(dict(scan=scan,arm=arm,mode=mode,windows=last['assigned'],
                    denominator=last['denominator'],coverage=last['coverage'],satellites=len(chosen),
                    relative_timing_rms_s=float(np.std(timing)),timing_prior_nll=prior,
                    rms_hz=r['rms_hz'],gaussian_residual_cost=float(.5*sum(a['residual_hz']**2 for a in assignments)/200.**2),
                    primary_selection_score=last['objective'],converged=r['converged']))
            changes.append(dict(scan=scan,arm=arm,**selection_changes(*selections.values())))
        for mode in MODES:
            data,meta=read_input(scan,mode)
            for arm in ARMS:
                path=position_root/scan/f'{arm}-{mode}-position.json';r=json.loads(path.read_text())
                assert r['input_sha256']==meta['input_sha256']
                assert r['fit_original_rows']==r['evaluation_original_rows']==data.original_rows.tolist()
                assert r['heldout_original_rows']==[] and r['numbers']==data.numbers.tolist()
                assert r['maximum_budgets_s']==BUDGET
                if position_root!=OUT:assert r['extra_polish_budget_s']==20.
                assert r['radius_km']==4. and r['total_timing_bound_s']==20.
                obj=make_objective(data,meta,arm);values=diagnostics(obj,data,r['best'])
                for key in ('objective','kkt','distance_m'):
                    assert abs(values[key]-r[key])<1e-7,(scan,arm,mode,key)
                assert values['converged']==r['converged']
                if arm=='zero-c':assert abs(r['best']['coefficient'])<1e-10
                prior=json.loads((SOURCE/f'{scan}-{arm}-original.json').read_text())
                regression=values['objective']-prior['objective'] if mode=='count-control' else None
                if regression is not None:assert regression<1e-6,(scan,arm,'lost known minimum',regression)
                rows.append(dict(scan=scan,arm=arm,mode=mode,windows=len(data.times),satellites=len(data.numbers),
                    coverage=len(data.times)/meta['full_top_window_denominator'],**values,
                    previous_control_score_change=regression,receipt_sha256=digest(path)))
    cohort=[]
    for arm in ARMS:
        for mode in MODES:
            subset=[r for r in rows if r['arm']==arm and r['mode']==mode]
            errors=np.array([r['distance_m'] for r in subset])
            cohort.append(dict(arm=arm,mode=mode,scans=len(subset),below_1km=int(sum(errors<1000)),
                median_error_m=float(np.median(errors)),mean_error_m=float(np.mean(errors)),
                unconverged=sum(not r['converged'] for r in subset),boundary=sum(r['boundary'] for r in subset)))
    report=dict(status='passed',exact_association_controls=controls,position_cases=len(rows),
        converged=sum(r['converged'] for r in rows),cohort=cohort,rows=rows,associations=associations,changes=changes,
        notes=['Fixed timing weight 1 in coverage units; not the downstream NLL.',
            'All original top windows available for selection; all selected windows used for localization.',
            'RF position arms share fitted-c-selected inputs. Existing fold-derived RX baseline unchanged.',
            'Absolute NLL cannot be compared across changed data/banks; no global minimum certificate.',
            'No truth-based satellite removal or per-scan model selection.'])
    (position_root/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    for name,values in [('position-summary.csv',rows),('association-summary.csv',associations)]:
        with (position_root/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    print(json.dumps(dict(controls=controls,cases=len(rows),cohort=cohort),indent=2))
    return report


def render(report,position_root=OUT):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    rows=report['rows'];association=report['associations']
    fig,axes=plt.subplots(3,1,figsize=(15,12),sharex=True)
    for ax,arm in zip(axes[:2],ARMS):
        for i,scan in enumerate(SCANS):
            pair=[next(r for r in rows if (r['scan'],r['arm'],r['mode'])==(scan,arm,m)) for m in MODES]
            ax.plot([i-.12,i+.12],[r['distance_m'] for r in pair],color='.65',lw=1)
            for dx,r,color in zip([-.12,.12],pair,['#888888','#0072b2']):
                ax.scatter(i+dx,r['distance_m'],s=50,c=color,marker='^' if r['boundary'] else 'o')
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],s=55,c='black',marker='x')
            ax.annotate(f"{pair[1]['distance_m']:.0f}",(i+.12,pair[1]['distance_m']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=8)
        summaries=[next(r for r in report['cohort'] if r['arm']==arm and r['mode']==m) for m in MODES]
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+
            f" · median {summaries[0]['median_error_m']:.0f} → {summaries[1]['median_error_m']:.0f} m; below 1 km: {summaries[0]['below_1km']} → {summaries[1]['below_1km']} of 16")
        ax.set_ylabel('Position error (m)');ax.axhline(1000,c='.4',ls='--');ax.axhline(4000,c='.5',ls=':');ax.set_ylim(0,4480)
    ax=axes[2]
    for mode,color,label in zip(MODES,['#888888','#0072b2'],['Count control','Timing-regularized selection']):
        values=[next(r for r in association if (r['scan'],r['arm'],r['mode'])==(s,'fitted-c',mode)) for s in SCANS]
        ax.plot(range(16),[100*r['coverage'] for r in values],'o-',color=color,label=label)
    ax.set_title('Coverage of the fitted-c association set used by BOTH localization arms')
    ax.set_ylabel('All passing top windows assigned (%)');ax.set_ylim(60,100);ax.legend(loc='lower right')
    ax.set_xticks(range(16),SCANS)
    for ax in axes:ax.grid(axis='y',alpha=.18)
    handles=[Line2D([],[],marker=m,color=c,ls='none',label=l) for m,c,l in
        [('o','#888888','Count control'),('o','#0072b2','Timing-regularized'),('x','black','Unconverged'),('^','.4','4 km boundary')]]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.063),ncol=4,frameon=False)
    fig.suptitle('Does penalizing timing shifts during satellite selection reduce position bias?',fontsize=17)
    fig.text(.5,.014,'Primary selection score: assigned windows − 10 × satellites − timing cost (weight 1). Same archived candidate pool/calibration.\n'
        'Independent 4 km searches; original likelihood and priors; ±20 s total satellite timing. No truth-position prior.\n'
        'Matched RF inputs/search budgets within each selection case. In-sample association evidence; local best-found positions.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.105,1,.96));fig.savefig(position_root/'position-coverage-comparison.png',dpi=165);plt.close(fig)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--polished',action='store_true');args=parser.parse_args()
    root=OUT/'polished' if args.polished else OUT
    render(audit(root),root)
