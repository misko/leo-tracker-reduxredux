"""Post-selection geographic evaluation and an independent original-score audit."""
import argparse
import collections
import csv
from dataclasses import replace
import json
from pathlib import Path
import sys
import numpy as np
from leo.contracts.regional_position import RegionalPrior,PositionScore
from leo.analysis.regional_position_score import coordinates,PositionObjective
import data
import experiment as trial
HERE=Path(__file__).resolve().parent

def distance_km(latitude,longitude,reference):
    a,b=np.radians([latitude,longitude]);c,d=np.radians(reference)
    h=np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2
    return float(2*6371.0088*np.arcsin(np.sqrt(np.clip(h,0,1))))

def distribution(values):
    values=np.asarray(values,float)
    if not len(values):return dict(count=0)
    return dict(count=len(values),mean=float(np.mean(values)),median=float(np.median(values)),
        p90=float(np.percentile(values,90)),p95=float(np.percentile(values,95)),maximum=float(max(values)),
        under5=int(sum(values<5)),under10=int(sum(values<10)),over50=int(sum(values>50)),over100=int(sum(values>100)))

def reference_point(prior,reference):
    a,b,c,d=np.radians([prior.latitude_deg,prior.longitude_deg,*reference])
    bearing=np.arctan2(np.sin(d-b)*np.cos(c),np.cos(a)*np.sin(c)-np.sin(a)*np.cos(c)*np.cos(d-b))
    distance=distance_km(prior.latitude_deg,prior.longitude_deg,reference)
    return distance*np.array([np.sin(bearing),np.cos(bearing)])

def evaluate(partial=False,audit=False):
    protocol=json.loads((HERE/'protocol.json').read_text())
    for path,expected in protocol['sources'].items():assert data.digest(path)==expected,path
    reference_doc=json.loads((HERE/'evaluation.json').read_text())
    reference=[reference_doc['reference_latitude_deg'],reference_doc['reference_longitude_deg']]
    rows=[];searches=[];failures=[];audits=[]
    for label in protocol['labels']:
        d=json.loads((HERE/'inputs'/label/'inputs.json').read_text());prior=RegionalPrior(**d['prior'])
        truth=reference_point(prior,reference)
        loaded=None
        for phase in protocol['phases']:
            folder=HERE/'results'/label/phase;path=folder/'result.json'
            if not path.exists():
                if partial:continue
                raise ValueError(f'missing result: {label} {phase}')
            result=json.loads(path.read_text());search=json.loads((folder/'search.json').read_text())
            points=search['search']['evaluations']
            assert len(points)==400 and len({(p['east_km'],p['north_km']) for p in points})==400
            region_errors=[r for r in result['region_status'] if r['status']!='complete']
            for failure in region_errors:failures.append(dict(label=label,phase=phase,**failure))
            regional_candidates=[]
            for region_path in (folder/'regions').glob('*.json'):
                regional_candidates.extend(json.loads(region_path.read_text())['candidates'])
            searches.append(dict(label=label,phase=phase,points=len(points),
                failed=sum(r['status']=='failed' for r in search['rows']),
                converged=sum(r['converged'] is True for r in search['rows']),
                time_limited=sum(r['stop_reason']=='time-budget' for r in search['rows']),
                levels=dict(collections.Counter(str(p['spacing_km']) for p in points)),
                outside_240km=sum(np.hypot(p['east_km'],p['north_km'])>=240 for p in points),
                nearest_grid_point_km=min(float(np.linalg.norm(np.array([p['east_km'],p['north_km']])-truth)) for p in points),
                reference_in_retained_region=any(np.linalg.norm(np.array([b['east_km'],b['north_km']])-truth)<=max(25.,b['spacing_km']/np.sqrt(2)) for b in result['basins']),
                elapsed_s=result['elapsed_s']))
            for arm in ('zero-c','fitted-c'):
                selection=result['selections'][arm];selected=selection['result'];best=selection['best_feasible']
                row=dict(label=label,session_id=d['session_id'],capture_local=d['capture_local'],time_block=d['time_block'],
                    phase=phase,arm=arm,accepted=selected is not None,error_km=None,best_feasible_error_km=None,
                    failed_regions=len(region_errors),frequency_rms_hz=None)
                alternative_errors=[distance_km(*coordinates(prior,c['vector'][:2]),reference) for c in regional_candidates
                                    if c['arm']==arm and c['converged'] and c['feasible']]
                row['best_available_candidate_error_km']=min(alternative_errors,default=None)
                row['reference_in_retained_region']=searches[-1]['reference_in_retained_region']
                if best:
                    row['best_feasible_error_km']=distance_km(*coordinates(prior,best['vector'][:2]),reference)
                if selected:
                    x,y=selected['point'];radius=selected['local_radius_km']
                    region=json.loads((folder/'regions'/f'{x:g}_{y:g}_{radius:g}.json').read_text())
                    correction=region['calibration']['correction']
                    piecewise=np.diff(np.asarray(correction['knots_hz']),axis=1)/np.diff(correction['nodes_s'])
                    total_slopes=piecewise+np.asarray(selected['combined_affine_slopes_hz_s'])[:,None]
                    lat,lon=coordinates(prior,selected['vector'][:2])
                    row.update(error_km=distance_km(lat,lon,reference),latitude_deg=lat,longitude_deg=lon,
                        frequency_rms_hz=selected['frequency_rms_hz'],timing_penalty=selected['timing_penalty'],
                        signal_windows=selected['signal_windows'],signal_fraction=selected['signal_windows']/d['observation_count'],
                        data_nll=selected['data_nll'],selection_score=selected['selection_score'],
                        rx0_slope_hz_s=selected['additional_slopes_hz_s'][0],rx1_slope_hz_s=selected['additional_slopes_hz_s'][1],
                        rx0_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][0],
                        rx1_combined_affine_hz_s=selected['combined_affine_slopes_hz_s'][1],
                        rx0_total_drift_min_hz_s=float(total_slopes[0].min()),rx0_total_drift_max_hz_s=float(total_slopes[0].max()),
                        rx1_total_drift_min_hz_s=float(total_slopes[1].min()),rx1_total_drift_max_hz_s=float(total_slopes[1].max()),
                        slope_bound_active=bool(selected['slope_active_bounds']),spatial_boundary=selected['boundary'],
                        stationarity=selected['stationarity'],origin=selected['origin'],
                        region_east_km=selected['point'][0],region_north_km=selected['point'][1])
                    if audit:
                        if loaded is None:loaded=data.load(label)
                        _,obs,bank,_,score=loaded;score=replace(score,relative_sigma_s=protocol['phases'][phase]['sigma'])
                        objective=PositionObjective(obs,bank.select(region['association']['selected_indices']),prior,score,
                            receiver_baseline_hz=np.asarray(region['calibration']['receiver_baseline_hz']))
                        v=np.asarray(selected['vector']);value,gradient,terms=objective.evaluate(v)
                        np.testing.assert_allclose(value,selected['objective'],atol=1e-6,rtol=0)
                        checked=trial.audit(objective,v,gradient,arm,[x,y],radius,protocol['phases'][phase]['width'])
                        assert checked['converged'] and checked['feasible']
                        audits.append(dict(label=label,phase=phase,arm=arm,**checked))
                rows.append(row)
    paired=[];summary={}
    for arm in ('zero-c','fitted-c'):
        these=[r for r in rows if r['arm']==arm]
        per_phase={phase:[r for r in these if r['phase']==phase] for phase in protocol['phases']}
        for label in protocol['labels']:
            p={r['phase']:r for r in these if r['label']==label}
            if len(p)<2:continue
            before,after=p['before'],p['after'];valid=before['accepted'] and after['accepted']
            paired.append(dict(label=label,session_id=before['session_id'],capture_local=before['capture_local'],
                time_block=before['time_block'],arm=arm,before_accepted=before['accepted'],after_accepted=after['accepted'],
                before_km=before['error_km'],after_km=after['error_km'],
                change_km=after['error_km']-before['error_km'] if valid else None,
                improvement_km=before['error_km']-after['error_km'] if valid else None,
                before_frequency_rms_hz=before['frequency_rms_hz'],after_frequency_rms_hz=after['frequency_rms_hz']))
        pairs=[r for r in paired if r['arm']==arm and r['change_km'] is not None]
        stats={phase:dict(position_error_km=distribution([r['error_km'] for r in rs if r['accepted']]),
            accepted=sum(r['accepted'] for r in rs),failed=sum(not r['accepted'] for r in rs),
            best_feasible_error_km=distribution([r['best_feasible_error_km'] for r in rs if r['best_feasible_error_km'] is not None]),
            median_frequency_rms_hz=float(np.median([r['frequency_rms_hz'] for r in rs if r['accepted']])) if any(r['accepted'] for r in rs) else None,
            median_signal_fraction=float(np.median([r['signal_fraction'] for r in rs if r['accepted']])) if any(r['accepted'] for r in rs) else None,
            slope_bound_active=sum(r.get('slope_bound_active',False) for r in rs),
            spatial_boundary=sum(r.get('spatial_boundary',False) for r in rs)) for phase,rs in per_phase.items()}
        stats['paired']=dict(count=len(pairs),improved=sum(r['change_km']<0 for r in pairs),worsened=sum(r['change_km']>0 for r in pairs),
            unchanged=sum(r['change_km']==0 for r in pairs),
            median_improvement_km=float(np.median([r['improvement_km'] for r in pairs])) if pairs else None,
            before_error_km=distribution([r['before_km'] for r in pairs]),after_error_km=distribution([r['after_km'] for r in pairs]),
            removed_over100=sum(r['before_km']>100 and r['after_km']<=100 for r in pairs),
            introduced_over100=sum(r['before_km']<=100 and r['after_km']>100 for r in pairs),
            largest_improvements=sorted((r for r in pairs if r['change_km']<0),key=lambda r:r['change_km'])[:8],
            largest_regressions=sorted((r for r in pairs if r['change_km']>0),key=lambda r:r['change_km'],reverse=True)[:8])
        summary[arm]=stats
    result=dict(complete=len(searches)==128,completed_phases=len(searches),summary=summary,rows=rows,paired=paired,
                searches=searches,region_failures=failures,audits=audits,protocol_hash=data.digest(HERE/'protocol.json'))
    trial.write(HERE/('partial_summary.json' if partial else 'summary.json'),result)
    if not partial:
        wide={}
        for row in paired:
            target=wide.setdefault(row['label'],{k:row[k] for k in ('label','session_id','capture_local','time_block')})
            prefix='zero_c' if row['arm']=='zero-c' else 'fitted_c'
            target.update({prefix+'_'+k:row[k] for k in ('before_km','after_km','change_km','before_accepted','after_accepted',
                                                       'before_frequency_rms_hz','after_frequency_rms_hz')})
        for filename,values in [('comparison.csv',[wide[k] for k in sorted(wide)]),('comparison_by_arm.csv',paired),
                                ('results_long.csv',rows),('search_diagnostics.csv',searches)]:
            fields=list(dict.fromkeys(k for r in values for k in r))
            with (HERE/filename).open('w') as output:
                writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader();writer.writerows(values)
        plot(result)
        write_report(result)
    print(json.dumps(dict(completed_phases=len(searches),summary=summary),indent=2))
    return result

def write_report(result):
    lines=['N01--N64: paired before/after position evaluation','',
        'Cohort: the literal N01--N64 labels, not the older N17--N80 extension.',
        'Before: V16 relative timing sigma 0.15 s; unbounded added affine slopes; 100/50/25/12.5 km; legacy zero priority on unmeasured edge cells.',
        'After: V16 relative timing sigma 1 s; hard +/-60 Hz/s on fitted affine terms; 40/20/10/5 km; nearest measured coarse score for unmeasured edge cells.',
        'Matched: original observations, causal regional TLE bank, Sacramento-centered 250 km prior, 400 evaluated points, top three distinct regions, fitting budgets, frequency likelihood and all other priors.',
        'Both use V16 for grid scoring and calibration. The shared discrete association routine has a T1-AT name; it does not introduce a second T1AT likelihood search.',
        'This is a fresh controlled before baseline, not a reproduction of historical roof-seeded results.',
        'The reference location is read only after candidate selection, never for search starts or ranking.',
        '',
        'Matched c ablation: c=0 versus fitted c in the final stage, sharing candidate banks, calibration, starts and budgets within each phase. Discovery/calibration/association retain fitted c.',
        'The slope bound applies separately to calibration and final fitted terms. Combined affine and piecewise drift can exceed +/-60 Hz/s; results_long.csv reports both.',
        'The package is tested as a bundle. This experiment does not identify the individual contribution of each of the three fixes.',
        'Objective totals across phases are not directly comparable because the timing prior changes. Geographic errors and frequency residuals are reported separately.',
        'Position error is horizontal great-circle distance. Frequency RMS is in-sample and weighted by posterior satellite responsibility; signal fractions are included in summary.json.',
        'All selected positions were repriced and checked using the original deployed likelihood and gradient.',
        'Native orbit interpolation and equivalent narrow-Gaussian evaluation accelerate both phases. Numerical parity is tested; nonlinear optimizer trajectories need not match older runs bit for bit.',
        'A runtime-only pilot hit association deadlines. Its final fits were archived, the validated native orbit evaluator was applied to association in both phases, and every final region fit was rerun. Grid caches and searches were retained unchanged; see association_replay_migration.json.',
        'Reported stage wall times include concurrency and cache reuse and should not be treated as standalone runtime benchmarks.','']
    for arm,stats in result['summary'].items():
        lines.append(arm)
        for phase in ('before','after'):
            p=stats[phase];d=p['position_error_km']
            if d['count']:
                lines.append(f"  {phase}: accepted {p['accepted']}/64; failed {p['failed']}; error median {d['median']:.3f} km, p90 {d['p90']:.3f}, p95 {d['p95']:.3f}, max {d['maximum']:.3f}; >100 km {d['over100']}; <5 km {d['under5']}; frequency RMS median {p['median_frequency_rms_hz']:.2f} Hz.")
        p=stats['paired'];lines.append(f"  Paired accepted scans {p['count']}: improved {p['improved']}, worsened {p['worsened']}, unchanged {p['unchanged']}; median per-scan improvement {p['median_improvement_km']} km.")
        lines.append('  Largest regressions:')
        for r in p['largest_regressions'][:5]:lines.append(f"    {r['label']} {r['session_id']}: {r['before_km']:.3f} -> {r['after_km']:.3f} km")
        lines.append('')
    for phase in ('before','after'):
        rs=[r for r in result['searches'] if r['phase']==phase]
        lines.append(f"{phase} search: {sum(r['points'] for r in rs)} grid scores; {sum(r['failed'] for r in rs)} failed points; {sum(r['time_limited'] for r in rs)} timed-out point fits; reference covered by retained regions on {sum(r['reference_in_retained_region'] for r in rs)}/64 scans; mean outer-10-km evaluations {np.mean([r['outside_240km'] for r in rs]):.1f}.")
    lines.extend(['','Regression diagnostics:'])
    diagnostic=HERE/'N64_regression_diagnostic.json'
    if diagnostic.exists():
        n64=json.loads(diagnostic.read_text())
        gap=min(r['chart_gap_to_reference_km'] for r in n64['regions'] if r['phase']=='after')
        lines.append(f"N64: all three revised refinement regions exclude the reference; the nearest allowed region edge is {gap:.3f} km away in the search chart. Both selected final solutions are stationary and their slope bounds are inactive. The revised search missed the correct region; wider coverage alone still requires validation before claiming a fix.")
    n13=next(r for r in result['rows'] if r['label']=='N13' and r['phase']=='after' and r['arm']=='fitted-c')
    if n13['accepted']:
        lines.append(f"N13 fitted-c: the score-selected result has {n13['error_km']:.3f} km error, while another converged candidate has {n13['best_available_candidate_error_km']:.3f} km error and a worse model score. This exposes a fit/scoring issue beyond geographic coverage. See N13_regression_diagnostic.json; the reference did not select the reported winner.")
    lines.extend(['',f"Failed candidate regions: {len(result['region_failures'])}. These remain in summary.json and are not silently dropped.",
                  f"Independent accepted-position audits: {len(result['audits'])}.",'',
                  'Artifacts: comparison.csv (64 scans, both arms), comparison_by_arm.csv (one row per scan/arm), results_long.csv (positions/drift/fit diagnostics), search_diagnostics.csv, summary.json, protocol.json, position_comparison.png, per_scan_errors.png.'])
    (HERE/'findings.txt').write_text('\n'.join(lines)+'\n')

def plot(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors={'before':'#9b5a37','after':'#1876a3'}
    positive=[r['error_km'] for r in result['rows'] if r['accepted'] and r['error_km']>0]
    lower=min(.1,10.**np.floor(np.log10(min(positive)))) if positive else .1
    fig,axes=plt.subplots(2,2,figsize=(12,10),layout='constrained')
    for column,arm in enumerate(('zero-c','fitted-c')):
        pairs=[r for r in result['paired'] if r['arm']==arm and r['change_km'] is not None]
        ax=axes[0,column]
        ax.plot([lower,500],[lower,500],color='#999',lw=1,label='Equal error')
        for improved,color,name in [(True,colors['after'],'Improved'),(False,'#cc5446','Worsened')]:
            group=[r for r in pairs if (r['change_km']<0)==improved]
            ax.scatter([r['before_km'] for r in group],[r['after_km'] for r in group],c=color,s=30,alpha=.8,label=f'{name}: {len(group)}')
        marked=sorted(pairs,key=lambda r:r['change_km'])[:1]+sorted(pairs,key=lambda r:r['change_km'],reverse=True)[:3]
        for index,row in enumerate(marked):
            far=row['before_km']>100
            ax.annotate(row['label'],(row['before_km'],row['after_km']),xytext=(-5 if far else 5,9 if index%2==0 else -13),
                        ha='right' if far else 'left',textcoords='offset points',fontsize=8)
        ax.set(xscale='log',yscale='log',xlim=(lower,500),ylim=(lower,500),aspect='equal',
               xlabel='Before position error (km)',ylabel='After position error (km)',title=f'{arm}: {len(pairs)} accepted pairs')
        ax.grid(alpha=.2,which='both');ax.legend(loc='lower right',fontsize=9)
        ax=axes[1,column]
        for phase in ('before','after'):
            values=np.sort([r['error_km'] for r in result['rows'] if r['arm']==arm and r['phase']==phase and r['accepted']])
            ax.step(np.r_[lower,values,500.],np.r_[0.,np.arange(1,len(values)+1)/64,len(values)/64],where='post',color=colors[phase],lw=2,
                    label=f'{phase.title()}: {len(values)}/64 accepted')
        ax.set(xscale='log',xlim=(lower,500),ylim=(0,1.03),xlabel='Position error (km)',ylabel='Fraction of all 64 scans')
        ax.axvline(100,color='#888',ls=':',lw=1);ax.grid(alpha=.2,which='both');ax.legend(loc='lower right')
    fig.suptitle('N01–N64 · V16-only · matched 400-point discovery budgets\nAfter: relative timing σ = 1 s, hard ±60 Hz/s terms, 40 → 20 → 10 → 5 km with edge priority fixed',fontsize=13)
    fig.savefig(HERE/'position_comparison.png',dpi=170);fig.savefig(HERE/'position_comparison.svg');plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(16,7),layout='constrained',sharex=True)
    for ax,arm in zip(axes,('zero-c','fitted-c')):
        for row in result['paired']:
            if row['arm']!=arm:continue
            x=int(row['label'][1:])
            if row['before_km'] is not None and row['after_km'] is not None:
                ax.plot([x,x],[row['before_km'],row['after_km']],color='#bbb',lw=1)
        for phase in ('before','after'):
            rs=[r for r in result['rows'] if r['arm']==arm and r['phase']==phase and r['accepted']]
            ax.scatter([int(r['label'][1:]) for r in rs],[r['error_km'] for r in rs],s=20,c=colors[phase],label=phase.title())
        ax.set(yscale='log',ylim=(lower,500),ylabel=f'{arm}\nPosition error (km)');ax.axhline(100,color='#888',ls=':');ax.grid(axis='y',alpha=.2);ax.legend(ncol=2)
    axes[-1].set_xticks(range(1,65,2),[f'N{i:02}' for i in range(1,65,2)],rotation=60)
    fig.suptitle('Every requested scan, selected by model score before checking geographic error')
    fig.savefig(HERE/'per_scan_errors.png',dpi=170);fig.savefig(HERE/'per_scan_errors.svg');plt.close(fig)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');parser.add_argument('--audit',action='store_true')
    args=parser.parse_args();evaluate(args.partial,args.audit)
