"""Evaluate sealed RF-only decisions; evaluation GPS is introduced only here."""
import csv,hashlib
from collections import Counter
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

TRUTH=(37.849061591561885,-122.48574968092912)
LABELS={'ALGO05':'Current baseline','48h_15s':'48 h / ±15 s','72h_15s':'72 h / ±15 s',
        '72h_30s':'72 h / ±30 s','72h_30s_recency':'72 h / ±30 s + age penalty'}
COLORS={'ALGO05':'#555555','48h_15s':'#15958a','72h_15s':'#2676bf','72h_30s':'#df8c24','72h_30s_recency':'#9756a6'}

def error(ll):
    a,b=np.deg2rad(TRUTH),np.deg2rad(ll)
    h=np.sin((b[0]-a[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((b[1]-a[1])/2)**2
    return float(2*6371008.8*np.arcsin(np.sqrt(h)))

def csvfile(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        w.writerows({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)

def main():
    protocol=read(ROOT/'protocol.json');cohort=protocol['cohort']
    missing=[z['case'] for z in cohort if not (ROOT/'position'/z['case']/'result.json').exists() or not (ROOT/'screen'/z['case']/'result.json').exists()]
    if missing:raise ValueError('Whole cohort incomplete: '+str(missing))
    audit=read(ROOT/'full-replay-audit.json')
    if len(audit)!=len(cohort) or not all(r['verified'] for r in audit):raise ValueError('Full baseline replay incomplete')
    files=[p for name in ['inputs','preflight','screen','position','catalogues'] for p in (ROOT/name).rglob('*.json')]
    files+=[ROOT/'protocol.json',ROOT/'full-replay-audit.json',ROOT/'numerical-provenance.json',ROOT/'nominal-catalogue-audit.json']+list(ROOT.glob('*.py'))
    write(ROOT/'inference-seal.json',dict(files={str(p):digest(p) for p in files},GPS_used=False,
            note='RF decisions frozen before this script introduces evaluation coordinates'))
    totals={r['case']:r['total_GLRT'] for r in read(INVENTORY/'per-scan.json')}
    rows=[];trials=[];screenrows=[];decisions=[];plots=[];controls=[];winner_changes=Counter()
    for item in cohort:
        case=item['case'];dataset=case.split('-')[0];inp=read(ROOT/'inputs'/(case+'.json'));r=read(ROOT/'position'/case/'result.json')
        baseline=inp['baseline_arms']
        for arm in ARMS:
            b=dict(dataset=dataset,case=case,arm=arm,method='ALGO05',error_m=error(baseline[arm]['endpoint_latlon']),
                   associated=len(inp['baseline_owners'][arm]),total=totals[case],added_points=0,status='published_baseline',
                   endpoint_latlon=baseline[arm]['endpoint_latlon'],candidate_vs_matched_control_m=0.,control_vs_published_m=0.)
            rows.append(b)
            if r['control']:
                v=r['control'][arm];controls.append(dict(dataset=dataset,case=case,arm=arm,baseline_error_m=b['error_m'],
                    control_error_m=error(v['endpoint_latlon']),all_gates=v['all_checked_gates_pass'],
                    movement_km=float(np.linalg.norm(np.asarray(v['endpoint_east_north_km'])-np.asarray(baseline[arm]['endpoint_east_north_km'])))))
            for policy,decision in r['decisions'].items():
                v=dict(b,method=policy,status=decision['status'])
                if decision['status']=='qualified':
                    trial=r['trials'][decision['trial']];p=trial['arms'][arm]
                    v.update(error_m=error(p['endpoint_latlon']),associated=b['associated']+p['proposed_added_points'],
                        added_points=p['proposed_added_points'],endpoint_latlon=p['endpoint_latlon'],
                        candidate_vs_matched_control_m=error(p['endpoint_latlon'])-error(r['control'][arm]['endpoint_latlon']),
                        control_vs_published_m=error(r['control'][arm]['endpoint_latlon'])-b['error_m'])
                rows.append(v)
        for policy,v in r['decisions'].items():decisions.append(dict(case=case,dataset=dataset,policy=policy,**v))
        for name,t in r['trials'].items():
            if 'arms' not in t:
                trials.append(dict(case=case,trial=name,status=t['status'],error=t.get('error')));continue
            for arm,v in t['arms'].items():
                trials.append(dict(case=case,trial=name,norad=t['entry']['norad'],points=t['entry']['points'],arm=arm,
                    status=t['status'],baseline_error_m=error(baseline[arm]['endpoint_latlon']),
                    control_error_m=error(r['control'][arm]['endpoint_latlon']),candidate_error_m=error(v['endpoint_latlon']),
                    failed_gates=[k for k,b in v['checks'].items() if not b],control_pass=r['control'][arm]['all_checked_gates_pass']))
            plots.append((case,name,t))
        search=read(ROOT/'screen'/case/'result.json')
        for target in search['targets']:
            ss={s['policy']:s for s in target['summaries']}
            for arm in ARMS:
                winners={}
                for policy,s in ss.items():
                    folds=s['arms'][arm]['folds'];f=folds.get('full')
                    if not f:continue
                    w=f['winner'];winners[policy]=w['norad']
                    margin=min(v['margin'] for v in folds.values())
                    screenrows.append(dict(case=case,dataset=dataset,fragment_id=target['source']['fragment_id'],points=target['source']['points'],
                        arm=arm,policy=policy,norad=w['norad'],age_h=w['age_h'],phase_s=w['phase_s'],rms_hz=w['rms_hz'],
                        full_margin=f['margin'],minimum_group_margin=margin,screen_pass=s['screen_pass'] and margin>=10,
                        noise_pass=w['noise']['noise_screen_pass'],training_winners=[v['winner']['norad'] for k,v in folds.items() if k!='full']))
                for a,b in [('48h_15s','72h_15s'),('72h_15s','72h_30s'),('72h_30s','72h_30s_recency')]:
                    if a in winners and b in winners and winners[a]!=winners[b]:winner_changes[a+' -> '+b]+=1
    for row in rows:row['associated_pct']=100*row['associated']/row['total']
    summaries=[]
    for dataset in ('DS26','DS27'):
        for arm in ARMS:
            base={r['case']:r for r in rows if r['dataset']==dataset and r['arm']==arm and r['method']=='ALGO05'}
            for method in LABELS:
                group=[r for r in rows if r['dataset']==dataset and r['arm']==arm and r['method']==method]
                err=np.array([r['error_m'] for r in group]);delta=np.array([r['error_m']-base[r['case']]['error_m'] for r in group])
                summaries.append(dict(dataset=dataset,arm=arm,method=method,count=len(group),mean_m=float(err.mean()),median_m=float(np.median(err)),
                    p90_m=float(np.percentile(err,90)),p95_m=float(np.percentile(err,95)),worst_m=float(err.max()),over_1km=int((err>1000).sum()),
                    associated=sum(r['associated'] for r in group),total=sum(r['total'] for r in group),
                    associated_pct=100*sum(r['associated'] for r in group)/sum(r['total'] for r in group),added_points=sum(r['added_points'] for r in group),
                    changed_scans=sum(r['status']=='qualified' for r in group),improved_over_25m=int((delta<-25).sum()),worsened_over_25m=int((delta>25).sum()),
                    mean_candidate_vs_matched_control_m=float(np.mean([r['candidate_vs_matched_control_m'] for r in group])),
                    mean_continuation_contribution_m=float(np.mean([r['control_vs_published_m'] for r in group])),
                    maximum_regression_m=float(delta.max()),maximum_improvement_m=float(-delta.min())))
    csvfile(ROOT/'position-errors.csv',rows);csvfile(ROOT/'summary.csv',summaries);csvfile(ROOT/'trials.csv',trials)
    csvfile(ROOT/'controls.csv',controls);csvfile(ROOT/'screen-summary.csv',screenrows);csvfile(ROOT/'decisions.csv',decisions)
    write(ROOT/'summary.json',dict(rows=summaries,winner_changes_across_both_arms=winner_changes,
        completed_scans=len(cohort),unavailable_scans=len(protocol['unavailable']),searched_fragments=sum(z['targets'] for z in cohort),
        matched_control_count=len(controls)//2,decisions_by_policy={k:dict(Counter(r['status'] for r in decisions if r['policy']==k)) for k in POLICIES}))
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for i,dataset in enumerate(('DS26','DS27')):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for method in LABELS:
                v=np.sort([r['error_m']/1000 for r in rows if r['dataset']==dataset and r['arm']==arm and r['method']==method])
                ax.step(v,np.arange(1,len(v)+1)/len(v),where='post',label=LABELS[method],color=COLORS[method],alpha=.85,lw=1.5)
            maximum=max(r['error_m']/1000 for r in rows if r['dataset']==dataset and r['arm']==arm)
            ax.set(title=f'{dataset} — {arm}',xlabel='Position error (km)',ylabel='Fraction of usable scans',xscale='log',xlim=(.03,max(15,maximum*1.1)),ylim=(0,1.02));ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);fig.suptitle('Causal recovery variants: full available fast-scan cohorts\nRejected proposals retain the current published baseline')
    fig.savefig(ROOT/'position_error_distributions.png',dpi=160);plt.close(fig)
    changed=sorted({r['case'] for r in rows if r['status']=='qualified'})
    fig,axes=plt.subplots(1,2,figsize=(13,max(4,.4*len(changed)+1.7)),layout='constrained')
    for j,arm in enumerate(ARMS):
        ax=axes[j]
        for k,case in enumerate(changed):
            base=next(r for r in rows if r['case']==case and r['arm']==arm and r['method']=='ALGO05')
            ax.scatter(base['error_m']/1000,k,c=COLORS['ALGO05'],marker='x',s=55)
            for offset,method in zip([-.18,-.06,.06,.18],POLICIES):
                v=next(r for r in rows if r['case']==case and r['arm']==arm and r['method']==method)
                ax.plot([base['error_m']/1000,v['error_m']/1000],[k+offset,k+offset],color=COLORS[method],alpha=.45)
                ax.scatter(v['error_m']/1000,k+offset,c=COLORS[method],s=22,label=LABELS[method] if k==0 else None)
        ax.set_yticks(range(len(changed)),changed);ax.set(title=arm,xlabel='Position error (km)');ax.grid(axis='x',alpha=.2)
    if changed:axes[0].legend(fontsize=8)
    else:axes[0].text(.5,.5,'No qualified position updates',transform=axes[0].transAxes,ha='center')
    fig.suptitle('Cases changed by at least one qualified conditional recovery\nCross: current baseline; colors: predeclared variants')
    fig.savefig(ROOT/'changed_scan_errors.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,max(4,.4*len(changed)+1.7)),layout='constrained')
    for j,arm in enumerate(ARMS):
        ax=axes[j];ax.axvline(0,color='black',lw=.8)
        for k,case in enumerate(changed):
            base=next(r for r in rows if r['case']==case and r['arm']==arm and r['method']=='ALGO05')
            for offset,method in zip([-.18,-.06,.06,.18],POLICIES):
                v=next(r for r in rows if r['case']==case and r['arm']==arm and r['method']==method)
                delta=v['error_m']-base['error_m']
                ax.plot([0,delta],[k+offset,k+offset],color=COLORS[method],alpha=.3)
                ax.scatter(delta,k+offset,c=COLORS[method],s=24,label=LABELS[method] if k==0 else None)
        ax.set_yticks(range(len(changed)),changed);ax.set(title=arm,xlabel='Change in position error (m): negative is better');ax.grid(axis='x',alpha=.2)
    if changed:axes[0].legend(fontsize=8)
    fig.suptitle('Paired error changes on every affected scan\nUnchanged fallbacks sit at zero; age-penalty results may overlap the unpenalized variant')
    fig.savefig(ROOT/'paired_error_changes.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,dataset in zip(axes,('DS26','DS27')):
        group=[r for r in summaries if r['dataset']==dataset and r['arm']=='fitted_c']
        ax.bar(range(len(group)),[r['added_points'] for r in group],color=[COLORS[r['method']] for r in group])
        ax.set_xticks(range(len(group)),[LABELS[r['method']] for r in group],rotation=25,ha='right',fontsize=8)
        for k,r in enumerate(group):ax.annotate(f"{r['associated_pct']:.3f}%",(k,r['added_points']),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
        ax.set(title=dataset,ylabel='Additional qualified native GLRT points');ax.margins(y=.3)
    fig.suptitle('Recovery yield: all GLRT points remain in the denominator')
    fig.savefig(ROOT/'association_coverage.png',dpi=160);plt.close(fig)
    def curve_figure(items,path):
        fig,axes=plt.subplots(len(items),2,figsize=(12,max(4,3*len(items))),squeeze=False,layout='constrained')
        for i,(case,name,t) in enumerate(items):
            v=t['arms']['fitted_c'];detail=v['family_details'][-1];diag=detail['diagnostics'][0]
            tt=np.asarray(diag['times_s']);yy=np.asarray(diag['CFO_hz']);pred=np.asarray(diag['prediction_CFO_hz'])
            axes[i,0].scatter(tt,yy/1000,s=10,color='black',label='Native GLRT');axes[i,0].plot(tt,pred/1000,color='#2676bf',label='Physical orbit + frozen receiver mean')
            residual=np.asarray(diag['raw_residual_hz'])-diag['profile_bias_hz']
            axes[i,1].plot(tt,residual,'.-',ms=3,color='#2676bf');axes[i,1].axhline(0,color='black',lw=.8)
            axes[i,0].set(title=f"{case}: {t['entry']['norad']} / {t['entry']['points']} points / ±{name.split('-')[-1]} s / {t['status']}",ylabel='CFO (kHz)',xlabel='Scan time (s)')
            axes[i,1].set(title=f"RMS {diag['profile_RMS_hz']:.1f} Hz; phase {detail['phase_map_s']:.2f} s",ylabel='Profile residual (Hz)',xlabel='Scan time (s)')
        axes[0,0].legend(fontsize=8);fig.savefig(path,dpi=130);plt.close(fig)
    if plots:
        (ROOT/'curves').mkdir(exist_ok=True);atlas=['# Physical position-trial curves','',
            'Fitted-c arm. All attempted physical trials, including rejected hypotheses; each panel preserves the original native points. Qualification is paired across c arms. These figures do not turn rejected proposals into associations.','']
        for case in sorted({c for c,_,_ in plots}):
            curve_figure([p for p in plots if p[0]==case],ROOT/'curves'/(case+'.png'))
            atlas += ['## '+case,'',f'![{case}](curves/{case}.png)','']
        (ROOT/'CURVES.md').write_text('\n'.join(atlas))
        chosen=[];seen=set()
        for item in sorted(plots,key=lambda v:(-v[2]['entry']['points'],v[0],v[1])):
            if item[0] not in seen:chosen.append(item);seen.add(item[0])
            if len(chosen)==8:break
        curve_figure(chosen,ROOT/'position_trial_curves.png')
    lines=['# DS26 / DS27: causal TLE age and phase recovery variants','',
        f"Evaluated {len(cohort)} usable fast scans (148 DS26, 13 DS27), with {len(protocol['unavailable'])} pre-existing unavailable scans retained in the accounting. The search covered {sum(z['targets'] for z in cohort)} residual fragments: at most three per scan, at least 20 native points and 15 seconds, ranked by duration before fitting.",
        '', 'This is a bounded conditional recovery experiment on the current ALGO05 outputs, not a fresh GLRT extraction or cold-start full-pipeline rerun. Every variant starts from the same saved RF-derived position within the existing 25 × 25 km region. Evaluation GPS is used only by `render.py`, after sealing inference decisions. No production changes were made.',
        '', '## Variants','',
        '- **48 h / ±15 s:** matched additional-search control with the original catalogue age and phase bounds.',
        '- **72 h / ±15 s:** admit the latest causal TLE per satellite out to 72 hours. Both collection and element epoch must precede the scan and satisfy the age window.',
        '- **72 h / ±30 s:** extend the phase search and private predictive propagation grid. Existing calibration equations and priors remain unchanged.',
        '- **72 h / ±30 s + age penalty:** add `2 log(2) max(age_h − 48, 0) / 24` to the candidate score. This halves prior odds per additional day. It is a sensitivity test, not evidence that older satellites are less likely to transmit.',
        '', '## Position and coverage','', '| Dataset | Arm | Variant | Mean km | Median km | P90 km | >1 km | GLRT associated | Added points |', '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:lines.append(f"| {r['dataset']} | {r['arm']} | {LABELS[r['method']]} | {r['mean_m']/1000:.3f} | {r['median_m']/1000:.3f} | {r['p90_m']/1000:.3f} | {r['over_1km']} | {r['associated_pct']:.3f}% | {r['added_points']} |")
    lines+=['','![Position distributions](position_error_distributions.png)','','![Paired error changes](paired_error_changes.png)','','![Changed scans](changed_scan_errors.png)','','![Association coverage](association_coverage.png)',
        '', '## Exact scope and safeguards','',
        'The incumbent core and selected additive likelihoods are replayed, including accepted graph fragments and joint new-family mixtures. Published owners are preserved; incidental unpublished membership extensions are recorded and never counted as recovered points.',
        '', 'Screening searches the complete eligible STARLINK catalogue at each saved RF endpoint, with a coarse phase grid and up to three nominations per policy, arm, and training partition. Finalists from the two c arms are unioned within each partition; full-data nominations are not inserted into training-only shortlists. Exact full-point screening integrates a 300 Hz constant, 0.5 Hz/s rate, 5-second phase prior and whole-track alias. The normalized likelihood includes the nuisance-volume penalty.',
        '', 'Three seeded random 12-second block holds with two-second guards test candidate stability. Every partition in both c arms must agree, with score margin at least 10, RMS at most 450 Hz, admissible bias/rate, interior phase, visibility and the existing residual-noise screen. These checks are conditional on the frozen graph and incumbent RF solution; they do not prove globally unique satellite identity.',
        '', 'At most one new-family fragment is proposed per scan and policy, chosen by the minimum RF identity margin, then point count. Existing-family extensions are unchanged. The final position uses the physical orbital-uncertainty model, not the screening offset/rate model. Causal history priors and the existing unavailable-history fallback are preserved. A separate age-dependent widening of nuisance priors is not tested here.',
        '', 'The matched position control and candidate have three phase-refresh rounds, up to 100 evaluations per round, and identical 25 × 25 km bounds. A second new family is integrated jointly with an incumbent new family so receiver covariance is counted once. The declared exact-mixture cap is two families; a third is left unchanged. Target data never recalibrate the receiver mean at a fixed position.',
        '', 'A proposal must pass both c arms, preserve incumbent owners, pass exact-orbit incumbent replay, all family residual gates, phase convergence, phase-boundary checks and local quadrature score/gradient checks. The numerical pilot showed that 0.1-second integration was insufficient; the cohort position trials use 0.05 seconds and verify 0.025/0.0125 seconds. Rejected or failed-closed proposals retain the published baseline. Candidate-versus-matched-control errors are separate in `trials.csv`; better frequency fit is not treated as better localization.',
        '', 'These are research qualifications, not promotion-ready production decisions. Identity ranking uses the normalized offset/rate screening model; the full physical likelihood is evaluated for the selected identity, not exhaustively reranked across every competitor. Shortlisting, the three-fragment cap, the two-family integration cap and local continuation all limit the conclusions. None of the results establishes global uniqueness or demonstrates that the full 25 × 25 km cold-start search improves.',
        '', '## Reproduction and evidence','',
        'Run with the modern numerical worktree `/srv/bulk/leo-dev/fast-algo02-production-v1`, its `.venv/bin/python`, `PYTHONPATH=src:tools`, and `OPENBLAS_NUM_THREADS=1`. `common.py` freezes the cohort; `export_catalogues.py` uses the read-only archive adapter; `screen.py` replays and nominates; `position.py` performs matched trials; `audit_replay.py` verifies full incumbent likelihoods; `render.py` seals inference and introduces evaluation GPS.',
        '', 'Validation: four new screening tests, seven inherited normalized-evidence tests, and nine physical-likelihood / phase-resolution tests passed. The operations test collection could not run in the numerical environment because its shared test configuration imports the unavailable `alembic` package. The executed catalogue search separately checks epoch and collection causality for every exported element. All 241,233 overlapping nominal elements match the 72-hour export byte for byte; existing satellite predictions are not silently swapped.',
        '', 'Machine-readable results: `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `trials.csv`, `controls.csv`, `decisions.csv`, and `inference-seal.json`. Per-scan raw evidence and catalogue provenance are retained under `inputs/`, `preflight/`, `catalogues/`, `screen/`, and `position/`. Initial infrastructure retries and the archived coarse numerical pilot are retained separately.',
        '', '[All physical-trial curves and residuals](CURVES.md). The overview below shows the eight longest trial sources, selected by native point count, not position error.',
        '', '![Physical candidate curves and residuals](position_trial_curves.png)','']
    (ROOT/'README.md').write_text('\n'.join(lines))
    print(json.dumps(read(ROOT/'summary.json'),indent=2))

if __name__=='__main__':main()
