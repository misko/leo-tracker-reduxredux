"""Evaluation-only reader: reference coordinates never enter the experiment driver."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import run_variants as run
from summarize import distance_km, reference_point
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

ARMS=('zero-c','fitted-c')
PHASES=('hard60','two_starts','calibration_retry','rf_offsets')
NAMES=dict(hard60='Hard60',two_starts='Two coarse starts',calibration_retry='Calibration recovery',rf_offsets='RF offsets')


def stats(values):
    if not values:return {}
    a=np.asarray(values)
    return dict(count=len(a),median=float(np.median(a)),p90=float(np.percentile(a,90)),
        p95=float(np.percentile(a,95)),maximum=float(a.max()),mean=float(a.mean()),
        under5=int((a<5).sum()),over10=int((a>10).sum()),over50=int((a>50).sum()))


def gather():
    reference_doc=run.read(run.OLD/'evaluation.json')
    reference=[reference_doc['reference_latitude_deg'],reference_doc['reference_longitude_deg']]
    rows=[];stages=[]
    for label in run.LABELS:
        metadata=run.read(run.OLD/'inputs'/label/'inputs.json')
        prior=RegionalPrior(**metadata['prior'])
        truth=reference_point(prior,reference)
        for phase in PHASES:
            folder=run.control_folder(label) if phase=='hard60' else run.HERE/'results'/label/phase
            if not (folder/'result.json').exists():continue
            result=run.read(folder/'result.json')
            search=run.read(folder/'search.json')
            covered=any(np.linalg.norm(truth-[b['east_km'],b['north_km']])<=max(25.,b['spacing_km']/np.sqrt(2)) for b in result['basins'])
            regions=[run.read(folder/'regions'/f"{b['east_km']:g}_{b['north_km']:g}_{max(25.,b['spacing_km']/np.sqrt(2)):g}.json") for b in result['basins']]
            point_folder=folder/'points' if phase in ('hard60','two_starts') else run.control_folder(label)/'points'
            points=[run.read(point_folder/f"{p['east_km']:g}_{p['north_km']:g}.json") for p in search['search']['evaluations']]
            coarse=[s for p in points for s in p.get('two_start_runs',[p['fit']] if p.get('fit') else [])]
            stage=dict(label=label,phase=phase,grid_points=len(points),reference_covered=covered,
                failed_grid_points=sum(p['status']!='complete' for p in points),
                coarse_fit_attempts=len(coarse),coarse_fit_seconds=sum(p['elapsed_s'] for p in coarse),
                coarse_timeouts=sum(p['stop_reason']=='time-budget' for p in coarse),
                failed_regions=sum(r['status']!='complete' for r in regions),
                recovered_regions=sum(r.get('control_region_status')=='failed' and r['status']=='complete' for r in regions),
                final_fit_seconds=sum(c.get('elapsed_s',0) for r in regions for c in r['runs']),
                final_timeouts=sum(c.get('stop_reason')=='time-budget' for r in regions for c in r['runs']),
                no_accepted_zero_c_regions=sum(not any(c['arm']=='zero-c' and c['converged'] and c['feasible'] for c in r['candidates']) for r in regions),
                no_accepted_fitted_c_regions=sum(not any(c['arm']=='fitted-c' and c['converged'] and c['feasible'] for c in r['candidates']) for r in regions),
                region_seconds=sum(r['elapsed_s'] for r in regions),case_wall_seconds=result['elapsed_s'])
            if phase=='two_starts':
                paired=[p['two_start_runs'] for p in points if len(p.get('two_start_runs',[]))==2]
                stage['second_start_wins']=sum(r[1]['objective']<r[0]['objective']-1e-6 for r in paired)
                stage['coarse_paired_starts']=len(paired)
                stage['second_start_score_gain']=sum(max(0.,r[0]['objective']-r[1]['objective']) for r in paired)
                old_basins=run.read(run.control_folder(label)/'result.json')['basins']
                old_points={(b['east_km'],b['north_km']) for b in old_basins}
                stage['new_retained_regions']=sum((b['east_km'],b['north_km']) not in old_points for b in result['basins'])
            stages.append(stage)
            for arm in ARMS:
                selected=result['selections'][arm]['result']
                row=dict(label=label,session_id=metadata['session_id'],capture_local=metadata['capture_local'],
                    phase=phase,arm=arm,accepted=selected is not None,error_km=None,
                    frequency_rms_hz=None,selection_score=None,data_nll=None,timing_penalty=None,rf_penalty=0.,
                    reference_covered=covered,failed_regions=stage['failed_regions'])
                if selected:
                    lat,lon=coordinates(prior,selected['vector'][:2])
                    row.update(error_km=distance_km(lat,lon,reference),latitude_deg=lat,longitude_deg=lon,
                        **{k:selected.get(k) for k in ('frequency_rms_hz','selection_score','data_nll','timing_penalty','stationarity')},
                        rf_penalty=selected.get('rf_penalty',0.),signal_fraction=selected['signal_windows']/metadata['observation_count'],
                        rf_max_offset_hz=max(map(abs,selected.get('rf_offsets_hz',[])),default=0.),
                        rx0_slope_hz_s=selected['additional_slopes_hz_s'][0],rx1_slope_hz_s=selected['additional_slopes_hz_s'][1],
                        region_east_km=selected['point'][0],region_north_km=selected['point'][1],origin=selected['origin'])
                rows.append(row)
    baseline={(r['label'],r['arm']):r for r in rows if r['phase']=='hard60'}
    for row in rows:
        b=baseline[row['label'],row['arm']]
        row['change_from_hard60_km']=row['error_km']-b['error_km'] if row['accepted'] and b['accepted'] else None
        row['paired_frequency_rms_change_hz']=row['frequency_rms_hz']-b['frequency_rms_hz'] if row['accepted'] and b['accepted'] else None
    summary={}
    for arm in ARMS:
        summary[arm]={}
        for phase in PHASES:
            group=[r for r in rows if r['phase']==phase and r['arm']==arm]
            accepted=[r for r in group if r['accepted']]
            delta=[r['change_from_hard60_km'] for r in accepted]
            summary[arm][phase]=dict(completed=len(group),accepted=len(accepted),
                position_error_km=stats([r['error_km'] for r in accepted]),
                median_frequency_rms_hz=float(np.median([r['frequency_rms_hz'] for r in accepted])) if accepted else None,
                median_signal_fraction=float(np.median([r['signal_fraction'] for r in accepted])) if accepted else None,
                paired_improved=sum(d<-.001 for d in delta),paired_worsened=sum(d>.001 for d in delta),
                paired_unchanged=sum(abs(d)<=.001 for d in delta),
                median_paired_change_km=float(np.median(delta)) if delta else None,
                median_paired_frequency_rms_change_hz=float(np.median([r['paired_frequency_rms_change_hz'] for r in accepted])) if accepted else None,
                worst_scan=max(accepted,key=lambda r:r['error_km'])['label'] if accepted else None,
                largest_regressions=sorted(accepted,key=lambda r:-r['change_from_hard60_km'])[:5])
    return dict(complete=len(rows)==512,rows=rows,stages=stages,summary=summary)


def export(result,partial):
    run.engine.write(run.HERE/('partial_summary.json' if partial else 'summary.json'),result)
    if partial:return
    for name,rows in [('results_long.csv',result['rows']),('stage_diagnostics.csv',result['stages'])]:
        fields=list(dict.fromkeys(k for r in rows for k in r))
        with (run.HERE/name).open('w') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter,NullFormatter
    plt.rcParams.update({'font.size':11})
    colors=['#333333','#2479b7','#269363','#c96035']
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for phase,color,style in zip(PHASES,colors,['-','-','--',':']):
            group=[r for r in result['rows'] if r['phase']==phase and r['arm']==arm and r['accepted']]
            values=np.sort([r['error_km'] for r in group])
            ax.step(values,np.arange(1,len(values)+1)/64,where='post',
                label=f'{NAMES[phase]} ({len(values)}/64)',color=color,linestyle=style,
                linewidth=2.2 if phase=='hard60' else 1.8)
        ax.set(xlabel='Position error (km; log scale)',ylabel='Fraction of all 64 scans',title=arm,ylim=(0,1.01),xscale='log')
        ax.set_xticks([.1,.3,1,3,10,30,100,300]);ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.suptitle('Hard60 variants: score-selected position error; timing σ = 2 s')
    fig.savefig(run.HERE/'position_error_cdf.png',dpi=170);fig.savefig(run.HERE/'position_error_cdf.svg')
    plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(15,7),layout='constrained')
    for i,arm in enumerate(ARMS):
        for j,phase in enumerate(PHASES[1:]):
            ax=axes[i,j]
            group=[r for r in result['rows'] if r['phase']==phase and r['arm']==arm and r['accepted']]
            x=np.array([r['error_km']-r['change_from_hard60_km'] for r in group]);y=np.array([r['error_km'] for r in group])
            ax.scatter(x,y,s=18,alpha=.7,color=colors[j+1]);limit=max(6,float(max(x.max(initial=0),y.max(initial=0)))*1.05)
            ax.plot([0,limit],[0,limit],'--',color='.5',lw=1)
            for r,a,b in zip(group,x,y):
                if abs(a-b)>2 or r['label']=='N29':
                    right=a>.85*limit
                    ax.annotate(r['label'],(a,b),fontsize=8,xytext=(-3 if right else 3,-10 if b>.85*limit else 3),
                        textcoords='offset points',ha='right' if right else 'left')
            ax.set(xlim=(.1,limit),ylim=(.1,limit),xlabel='Hard60 error (km; log scale)',ylabel=f'{arm}: variant error (km)',title=NAMES[phase],xscale='log',yscale='log')
            ticks=[t for t in (.1,.3,1,3,10,30,100,300) if t<=limit]
            ax.set_xticks(ticks);ax.set_yticks(ticks)
            ax.xaxis.set_major_formatter(ScalarFormatter());ax.yaxis.set_major_formatter(ScalarFormatter())
            ax.xaxis.set_minor_formatter(NullFormatter());ax.yaxis.set_minor_formatter(NullFormatter())
            ax.grid(alpha=.2)
    fig.suptitle('Paired scans: below the diagonal improves position accuracy')
    fig.savefig(run.HERE/'paired_position_errors.png',dpi=170);fig.savefig(run.HERE/'paired_position_errors.svg')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');args=parser.parse_args()
    result=gather()
    if not args.partial:assert result['complete'],'Missing scan/variant results'
    export(result,args.partial)
    compact={a:{p:{k:v for k,v in d.items() if k!='largest_regressions'} for p,d in s.items()} for a,s in result['summary'].items()}
    print(json.dumps(compact,indent=2))


if __name__=='__main__':main()
