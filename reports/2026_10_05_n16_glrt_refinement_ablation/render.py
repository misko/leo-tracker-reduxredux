"""Reconstruct all metrics, then visualize paired GLRT-refinement experiments."""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

import pipeline as p

COLORS={'raw':'#888888','pass1':'#0072B2','pass2':'#009E73'}
LABELS={'raw':'Unrefined','pass1':'Existing refinement','pass2':'+ Additional refinement'}


def table_write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def collect(stages,scans,polished=False):
    rows=[];coverage=[]
    for scan in scans:
        groups=None
        for stage in stages:
            folder=p.HERE/stage/scan
            meta=json.loads((folder/'position-input.json').read_text())
            assert meta['input_sha256']==p.digest(folder/'position-input.npz')
            with np.load(folder/'position-input.npz') as z:d=SimpleNamespace(**{k:z[k].copy() for k in z.files})
            raw=p.load_stage(scan,stage)
            if groups is None:groups=set(raw.group)
            assert set(raw.group)==groups
            cal=json.loads((folder/'calibration.json').read_text());p.calibration.validate_scope(cal,raw)
            for arm in p.ARMS:
                assoc=json.loads((folder/'associations'/f'{arm}.json').read_text())
                a=assoc['final'];assert a['denominator']==len(groups)
                assert a['assigned']==len(a['assignments'])==len(set(r['row_index'] for r in a['assignments']))
                assert set(r['row_index'] for r in a['assignments'])<=set(raw.original_rows)
                coverage.append(dict(scan=scan,stage=stage,arm=arm,windows=len(groups),assigned=a['assigned'],
                    coverage_percent=100*a['assigned']/len(groups),satellites=a['satellites'],
                    greedy_assigned=assoc['initial']['assigned'],replacement_converged=assoc['converged'],
                    calibration_converged=cal['converged'],association_rms_hz=assoc['rms_hz']))
                result_folder=folder/'polished' if polished else folder
                r=json.loads((result_folder/f'position-{arm}.json').read_text())
                assert r['fit_original_rows']==r['evaluation_original_rows']==d.original_rows.tolist()
                assert not r['heldout_original_rows'];assert r['budgets']==p.BUDGET
                assert r['metadata']==meta
                if arm=='zero-c':assert r['best']['coefficient']==0.
                obj=p.Objective(d,meta['rf_center_hz'],arm,0.,None,None,None)
                metrics=p.diagnostics(obj,d,r['best'])
                for key,value in metrics.items():np.testing.assert_allclose(value,r[key],rtol=0,atol=1e-6,err_msg=key)
                assert np.linalg.norm(r['best']['point_km'])<=4.+1e-7
                rows.append(dict(scan=scan,stage=stage,arm=arm,position_windows=len(d.times),satellites=len(d.numbers),
                    calibration_converged=cal['converged'],coefficient=r['best']['coefficient'],**metrics))
    return rows,coverage


def measurements(stages,scans):
    rows=[];distributions={v:[] for v in stages if v!='raw'}
    margin_deltas={v:[] for v in stages if v!='raw'}
    for scan in scans:
        folder=p.calibration.INPUTS/scan
        obs=json.loads((folder/'observations.json').read_text())['records']
        first=json.loads((folder/'refinement/refined.json').read_text())['records']
        current={'raw':{r['row_index']:(r['original_hz'],r['original_margin']) for r in obs},
                 'pass1':{r['row_index']:(r['output_hz'],r['refinement'].get('margin',r['original_margin'])) for r in first}}
        if 'pass2' in stages:
            second=json.loads((p.HERE/'refinement'/scan/'refined.json').read_text())
            assert second['summary']['status']=='complete' and not second['summary']['orbit_information_used']
            assert second['summary']['parent_sha256']==p.digest(folder/'refinement/refined.json')
            current['pass2']={r['row_index']:(r['output_hz'],r['refinement'].get('margin',r['original_margin'])) for r in second['records']}
        for stage in stages[1:]:
            previous='raw' if stage=='pass1' else 'pass1'
            old=current[previous];new=current[stage];assert old.keys()==new.keys()
            delta=np.array([p.circular(new[k][0]-old[k][0]) for k in old])
            dm=np.array([new[k][1]-old[k][1] for k in old])
            if stage=='pass2':assert np.all(dm>=-1e-12)
            a=p.load_stage(scan,previous);b=p.load_stage(scan,stage)
            ia=np.argsort(a.group);ib=np.argsort(b.group)
            np.testing.assert_array_equal(a.group[ia],b.group[ib])
            topdelta=p.circular(b.measured[ib]-a.measured[ia])
            rows.append(dict(scan=scan,stage=stage,candidates=len(delta),windows=len(a.times),
                candidate_median_absolute_shift_hz=float(np.median(abs(delta))),candidate_p95_absolute_shift_hz=float(np.percentile(abs(delta),95)),
                candidate_shifts_over100hz=int(sum(abs(delta)>100)),candidate_positive_margin_changes=int(sum(dm>1e-10)),
                top_id_changes=int(sum(a.original_rows[ia]!=b.original_rows[ib])),top_frequency_changes_over100hz=int(sum(abs(topdelta)>100)),
                top_median_absolute_shift_hz=float(np.median(abs(topdelta))),top_p95_absolute_shift_hz=float(np.percentile(abs(topdelta),95))))
            distributions[stage].extend(abs(delta));margin_deltas[stage].extend(dm)
    return rows,distributions,margin_deltas


def render(stages,scans,polished=False):
    rows,coverage=collect(stages,scans,polished);measurement,shifts,margins=measurements(stages,scans)
    out=p.HERE/('phase1' if len(stages)==2 else 'comparison');out.mkdir(exist_ok=True)
    table_write(out/'position-results.csv',rows);table_write(out/'association-results.csv',coverage)
    table_write(out/'measurement-changes.csv',measurement)
    summaries=[]
    for arm in p.ARMS:
        for stage in stages:
            selected=[r for r in rows if (r['stage'],r['arm'])==(stage,arm)]
            cov=[r for r in coverage if (r['stage'],r['arm'])==(stage,arm)]
            e=np.array([r['distance_m'] for r in selected])
            summaries.append(dict(stage=stage,arm=arm,scans=len(e),median_error_m=float(np.median(e)),mean_error_m=float(np.mean(e)),
                below1km=int(sum(e<1000)),boundary=sum(r['boundary'] for r in selected),unconverged=sum(not r['converged'] for r in selected),
                unconverged_calibrations=sum(not r['calibration_converged'] for r in selected),
                assigned=sum(r['assigned'] for r in cov),denominator=sum(r['windows'] for r in cov),
                coverage_percent=100*sum(r['assigned'] for r in cov)/sum(r['windows'] for r in cov),
                median_frequency_rms_hz=float(np.median([r['posterior_weighted_residual_rms_hz'] for r in selected]))))
    lookup={(r['scan'],r['stage'],r['arm']):r for r in rows}
    paired=[]
    for a,b in zip(stages,stages[1:]):
        for arm in p.ARMS:
            delta=np.array([lookup[s,b,arm]['distance_m']-lookup[s,a,arm]['distance_m'] for s in scans])
            valid=np.array([all(lookup[s,v,arm]['converged'] and lookup[s,v,arm]['calibration_converged'] for v in (a,b)) for s in scans])
            paired.append(dict(before=a,after=b,arm=arm,improved=int(sum(delta<0)),worsened=int(sum(delta>0)),
                median_paired_change_m=float(np.median(delta)),mean_paired_change_m=float(np.mean(delta)),
                paired_valid_scans=int(sum(valid)),median_valid_change_m=float(np.median(delta[valid])) if valid.any() else None,
                mean_valid_change_m=float(np.mean(delta[valid])) if valid.any() else None))
    archive_comparison=[]
    for scan in scans:
        for arm in p.ARMS:
            path=p.HERE.parent/'2026_10_05_n16_ambiguity_prototypes/polished'/f'{scan}-{arm}-baseline.json'
            old=json.loads(path.read_text());new=lookup[scan,'pass1',arm]
            archive_comparison.append(dict(scan=scan,arm=arm,archived_error_m=float(1000*np.linalg.norm(old['best']['point_km'])),
                fresh_existing_refinement_error_m=new['distance_m'],new_position_windows=new['position_windows'],
                archive_sha256=p.digest(path),note='Same saved GLRT refinement; fresh upstream calibration/selection and matched search starts.'))
    table_write(out/'archived-control-comparison.csv',archive_comparison)
    measurement_summary=[]
    for stage in stages[1:]:
        subset=[r for r in measurement if r['stage']==stage]
        measurement_summary.append(dict(stage=stage,candidates=sum(r['candidates'] for r in subset),
            windows=sum(r['windows'] for r in subset),candidate_positive_margin_changes=sum(r['candidate_positive_margin_changes'] for r in subset),
            candidate_shifts_over100hz=sum(r['candidate_shifts_over100hz'] for r in subset),
            median_absolute_candidate_shift_hz=float(np.median(shifts[stage])),
            p95_absolute_candidate_shift_hz=float(np.percentile(shifts[stage],95)),
            top_candidate_id_changes=sum(r['top_id_changes'] for r in subset),
            top_frequency_changes_over100hz=sum(r['top_frequency_changes_over100hz'] for r in subset)))
    p.save(out/'summary.json',dict(scope=p.__doc__,summary=summaries,paired=paired,measurement_summary=measurement_summary,
        verified_position_fits=len(rows),shared_start_continuation=polished))
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    offsets=np.linspace(-.25,.25,len(stages));x=np.arange(len(scans))
    fig,axes=plt.subplots(2,1,figsize=(17,10),sharex=True,sharey=True)
    for ax,arm in zip(axes,p.ARMS):
        for i,scan in enumerate(scans):
            ax.plot(i+offsets,[lookup[scan,v,arm]['distance_m'] for v in stages],color='.8',lw=1,zorder=1)
            for dx,v in zip(offsets,stages):
                r=lookup[scan,v,arm];ax.scatter(i+dx,r['distance_m'],s=42,marker='^' if r['boundary'] else 'o',color=COLORS[v],zorder=3)
                if not r['converged']:ax.scatter(i+dx,r['distance_m'],marker='x',color='black',s=38,zorder=4)
                if not r['calibration_converged']:ax.scatter(i+dx,r['distance_m'],marker='s',facecolors='none',edgecolors='red',s=85,zorder=4)
        medians=[next(r['median_error_m'] for r in summaries if (r['stage'],r['arm'])==(v,arm)) for v in stages]
        ax.set_title(('Fitted c' if arm=='fitted-c' else 'c = 0')+' · median error: '+' → '.join(f'{m:.0f} m' for m in medians))
        ax.axhline(4000,color='.5',ls=':',lw=1);ax.set_ylim(-120,4220);ax.set_ylabel('Position error from known roof (m)');ax.grid(alpha=.2)
    axes[-1].set_xticks(x,scans)
    handles=[Line2D([],[],marker='o',color=COLORS[v],label=LABELS[v]) for v in stages]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.95),ncol=len(stages))
    cohort='N01–N16' if len(scans)==16 else f'{len(scans)} completed scans'
    fig.suptitle(cohort+' · Does orbit-free GLRT refinement improve localization?',fontsize=19)
    fig.text(.5,.025,'Independent 4 km searches; full-data calibration + greedy/replacement rerun for each stage. Same position observations in both c arms.\nTriangles = boundary; × = position unconverged; red square = upstream calibration unconverged. Exploratory in-sample comparison.',ha='center',fontsize=10)
    fig.subplots_adjust(top=.87,bottom=.11,hspace=.3);fig.savefig(out/'position-error.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(17,9),sharex=True,sharey=True)
    covlookup={(r['scan'],r['stage'],r['arm']):r for r in coverage}
    for ax,arm in zip(axes,p.ARMS):
        for dx,v in zip(offsets,stages):
            ax.bar(x+dx,[covlookup[s,v,arm]['coverage_percent'] for s in scans],width=.22,color=COLORS[v],label=LABELS[v])
        ax.set_title('Association calibration: '+('fitted c' if arm=='fitted-c' else 'c = 0'));ax.set_ylabel('Passing 20 ms windows assigned (%)');ax.set_ylim(0,102);ax.axhline(90,color='.3',ls=':',lw=1);ax.grid(axis='y',alpha=.2)
    axes[0].legend(ncol=len(stages));axes[-1].set_xticks(x,scans)
    fig.suptitle('Coverage · same passing-window denominator, stage-specific highest-score candidate',fontsize=17)
    fig.text(.5,.025,'Score = assigned windows − 10 × satellites. ±600 Hz association gate; all archived visible satellites searched.\nNo duplicate-candidate inflation. c=0 association results are diagnostic; both position arms use fitted-c-selected windows/bank.',ha='center',fontsize=10)
    fig.subplots_adjust(top=.89,bottom=.12,hspace=.3);fig.savefig(out/'association-coverage.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,len(stages)-1,figsize=(8*(len(stages)-1),9),squeeze=False)
    for col,(a,b) in enumerate(zip(stages,stages[1:])):
        for row,arm in enumerate(p.ARMS):
            ax=axes[row,col];delta=np.array([lookup[s,b,arm]['distance_m']-lookup[s,a,arm]['distance_m'] for s in scans])
            bars=ax.barh(scans,delta,color=np.where(delta<0,'#009E73','#D55E00'))
            for bar,scan in zip(bars,scans):
                if not all(lookup[scan,v,arm]['converged'] and lookup[scan,v,arm]['calibration_converged'] for v in (a,b)):
                    bar.set_hatch('///');bar.set_edgecolor('.25');bar.set_linewidth(.5)
            ax.invert_yaxis();ax.axvline(0,color='.3',lw=1)
            ax.set_title(f'{LABELS[b]} vs {LABELS[a]}\n'+('Fitted c' if arm=='fitted-c' else 'c = 0'));ax.set_xlabel('Change in position error (m) · negative is better');ax.grid(axis='x',alpha=.2)
    fig.suptitle('Paired per-scan position changes',fontsize=19)
    fig.text(.5,.02,'Axes have different scales: the additional-pass changes are only a few metres.\nHatched bars: at least one calibration or position fit missed the convergence tolerance.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.95));fig.savefig(out/'paired-changes.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(14,5))
    edges=np.array([0,1,10,50,100,300,1000,np.inf]);labels=['<1','1–10','10–50','50–100','100–300','300–1k','≥1k']
    for j,v in enumerate(stages[1:]):
        bins=np.histogram(shifts[v],edges)[0];axes[0].bar(np.arange(len(labels))+(j-.5*(len(stages)-2))*.3,100*bins/sum(bins),width=.28,color=COLORS[v],label=LABELS[v])
        values=np.sort(margins[v]);axes[1].plot(values,np.arange(1,len(values)+1)/len(values),color=COLORS[v],label=LABELS[v])
    axes[0].set_xticks(np.arange(len(labels)),labels);axes[0].set_xlabel('Absolute alias-aware candidate shift (Hz)');axes[0].set_ylabel('Candidates (%)');axes[0].legend()
    axes[1].set_xlabel('Change in candidate GLRT margin');axes[1].set_ylabel('Cumulative fraction');axes[1].legend()
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('What changed in the measurements? Each stage compared with its predecessor');fig.tight_layout();fig.savefig(out/'measurement-changes.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),sharey=True)
    for ax,arm in zip(axes,p.ARMS):
        for scan in scans:
            values=[lookup[scan,v,arm]['posterior_weighted_residual_rms_hz'] for v in stages]
            ax.plot(np.arange(len(stages)),values,color='.8',lw=.8,zorder=1)
        for j,v in enumerate(stages):
            values=[lookup[s,v,arm]['posterior_weighted_residual_rms_hz'] for s in scans]
            ax.scatter(np.full(len(values),j),values,color=COLORS[v],s=28,zorder=2)
            ax.plot([j-.1,j+.1],[np.median(values)]*2,color='black',lw=3,zorder=3)
        ax.set_xticks(np.arange(len(stages)),[LABELS[v].replace(' refinement','\nrefinement') for v in stages])
        ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0');ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Posterior-weighted frequency residual RMS (Hz)')
    fig.suptitle('Frequency fit is a separate metric from localization accuracy')
    fig.text(.5,.015,'Lines connect scans; black bars = cohort medians. Conditional on each stage’s selected windows/bank; not an independent accuracy test.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.055,1,.95));fig.savefig(out/'frequency-fit.png',dpi=160);plt.close(fig)
    headers=['Stage','RF arm','Coverage','Median position error','Mean position error','Median fit RMS','Below 1 km','Position unconverged','Calibration unconverged']
    lines=['<tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr>']
    for r in summaries:
        cells=[LABELS[r['stage']],r['arm'],f"{r['coverage_percent']:.2f}%",f"{r['median_error_m']:.0f} m",f"{r['mean_error_m']:.0f} m",f"{r['median_frequency_rms_hz']:.1f} Hz",r['below1km'],r['unconverged'],r['unconverged_calibrations']]
        lines.append('<tr>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>')
    html='<html><meta charset="utf-8"><title>N16 GLRT refinement experiment</title><style>body{max-width:1400px;margin:40px auto;font:17px system-ui;padding:20px}img{width:100%}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Orbit-free GLRT refinement: N01–N16</h1>'
    html+='<p>Comparison 1: unrefined measurements versus the saved three-iteration refinement. Comparison 2: one additional three-iteration orbit-free restart, retaining the previous maximum if not improved. Original IQ only; no satellite or orbit information enters GLRT refinement.</p><table>'+''.join(lines)+'</table>'
    if 'pass2' in stages:
        extra=next(r for r in measurement_summary if r['stage']=='pass2')
        html+=f'<p><strong>Additional-pass measurement result:</strong> only {extra["top_frequency_changes_over100hz"]} of {extra["windows"]:,} winning-window frequencies changed by more than 100 Hz. {extra["top_candidate_id_changes"]} candidate IDs changed; an ID switch need not be a different physical signal. The remaining kilometer-scale bias is not removed by repeating this refinement.</p>'
    html+='<p>Full-data receiver calibration and all-visible-satellite greedy + replacement are rerun per measurement stage. Every original passing receiver/channel/20 ms window stays in the coverage denominator; its stage-specific highest-margin candidate is selected. Original detection selection is not undone.</p>'
    html+='<p>The existing-refinement column is a fresh controlled pipeline rerun, not a copy of older position results. Shared starts can find lower-score basins even without changing GLRT data. See <a href="archived-control-comparison.csv">archived-control comparison</a>; all decisions use score, not roof error.</p>'
    html+='<p>Positioning uses independent 4 km local searches, soft Q1 horizon, 200 Hz noise, common timing σ=10 s, relative timing σ=1/3 s, absolute satellite shifts ±20 s. Fitted-c and c=0 position arms share observations, bank, priors and search budgets. The upstream fitted-c-derived receiver baseline is shared; this is an additional-c ablation, not removal of every historical use of c.</p>'
    html+='<p>Known-roof calibration and in-sample development evidence, not blind validation. Higher GLRT score or higher association coverage does not establish correct satellite identity or better localization. Lower total position NLL across different retained observations is not a controlled comparison. Convergence flags are retained; no global minimum certificate.</p>'
    if polished:html+='<p>All position cases received matched continuation: the same eight archived/all-stage RF seeds were repriced, the top two fitted for up to 12 s each, then SLSQP (20 s) and Fisher (15 s) as needed. Selection is by score, never true position error. Earlier unpolished results are preserved.</p>'
    for name in ['position-error','paired-changes','association-coverage','frequency-fit','measurement-changes']:html+=f'<img src="{name}.png">'
    html+='<p>Data: <a href="position-results.csv">position CSV</a> · <a href="association-results.csv">association CSV</a> · <a href="measurement-changes.csv">measurement CSV</a> · <a href="summary.json">verified summary</a></p></html>'
    (out/'report.html').write_text(html)
    print(json.dumps(dict(summary=summaries,paired=paired),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--phase1',action='store_true');parser.add_argument('--scans',nargs='+',default=p.SCANS)
    parser.add_argument('--polished',action='store_true')
    args=parser.parse_args();render(['raw','pass1'] if args.phase1 else list(p.STAGES),args.scans,args.polished)
