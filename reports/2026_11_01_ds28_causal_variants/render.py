"""Seal DS28 inference, then introduce confirmed evaluation truth for reporting."""
import csv
from collections import Counter
from datetime import datetime,timezone
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
TRUTH=(37.849061591561885,-122.48574968092912)
LABELS={'ALGO05':'Current ALGO05 baseline','48h_15s':'48 h / ±15 s','72h_15s':'72 h / ±15 s',
        '72h_30s':'72 h / ±30 s','72h_30s_recency':'72 h / ±30 s + recency'}
COLORS=['#555555','#15958a','#2676bf','#df8c24','#9756a6']
def error(ll):
    a,b=np.deg2rad(TRUTH),np.deg2rad(ll)
    h=np.sin((b[0]-a[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((b[1]-a[1])/2)**2
    return float(2*6371008.8*np.arcsin(np.sqrt(h)))
def csvfile(path,rows):
    if not rows:return
    with Path(path).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader()
        w.writerows({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)
def main():
    protocol=read(ROOT/'protocol.json');cohort=protocol['cohort'];audit=read(ROOT/'full-replay-audit.json')
    assert len(audit)==len(cohort) and all(r['verified'] for r in audit)
    assert all((ROOT/'position'/r['case']/'result.json').exists() for r in cohort)
    paths=[p for sub in ('inputs','preflight','catalogues','screen','position') for p in (ROOT/sub).rglob('*.json')]
    paths+=list(ROOT.glob('*.py'))+[ROOT/'protocol.json',ROOT/'full-replay-audit.json',ROOT/'dataset/manifest.json',
        ROOT/'input-audit.json',ROOT/'numerical-provenance.json',ROOT/'upstream-failure.json']
    paths += [PREVIOUS/'common.py',ROOT.parent/'2026_10_31_causal72_age_prior/evidence.py',ROOT.parent/'2026_10_31_causal72_age_prior/run.py']
    write(ROOT/'inference-seal.json',dict(files={str(p):digest(p) for p in paths},GPS_inference=False))
    totals={r['case']:r['total_GLRT'] for r in read(INVENTORY/'per-scan.json')}
    rows=[];decisions=[];trials=[];screens=[];plots=[]
    for c in cohort:
        case=c['case'];z=read(ROOT/'inputs'/(case+'.json'));r=read(ROOT/'position'/case/'result.json')
        for arm in ARMS:
            b=z['baseline_arms'][arm];be=error(b['endpoint_latlon'])
            row=dict(case=case,arm=arm,method='ALGO05',error_m=be,associated=len(z['baseline_owners'][arm]),total=totals[case],
                     added_points=0,status='baseline',endpoint_latlon=b['endpoint_latlon'],frequency_objective=b['negative_twice_elbo'],
                     matched_control_error_m=None,delta_vs_control_m=None)
            rows.append(row)
            for policy,v in r['decisions'].items():
                out=dict(row,method=policy,status=v['status'])
                if v['status']=='qualified':
                    q=r['trials'][v['trial']]['arms'][arm];ce=error(r['control'][arm]['endpoint_latlon'])
                    out.update(error_m=error(q['endpoint_latlon']),associated=row['associated']+q['proposed_added_points'],
                               added_points=q['proposed_added_points'],endpoint_latlon=q['endpoint_latlon'],
                               frequency_objective=q['negative_twice_elbo'],matched_control_error_m=ce,
                               delta_vs_control_m=error(q['endpoint_latlon'])-ce)
                rows.append(out)
        decisions += [dict(case=case,policy=p,**v) for p,v in r['decisions'].items()]
        for name,t in r['trials'].items():
            if 'arms' not in t:trials.append(dict(case=case,trial=name,status=t['status'],error=t.get('error')));continue
            plots.append((case,name,t))
            for arm,v in t['arms'].items():
                trials.append(dict(case=case,trial=name,arm=arm,status=t['status'],norad=t['entry']['norad'],points=t['entry']['points'],
                    baseline_error_m=error(z['baseline_arms'][arm]['endpoint_latlon']),control_error_m=error(r['control'][arm]['endpoint_latlon']),
                    candidate_error_m=error(v['endpoint_latlon']),failed_gates=[k for k,b in v['checks'].items() if not b],
                    control_pass=r['control'][arm]['all_checked_gates_pass'],frequency_objective=v['negative_twice_elbo']))
        for target in read(ROOT/'screen'/case/'result.json')['targets']:
            for s in target['summaries']:
                for arm,d in s['arms'].items():
                    if 'full' not in d['folds']:continue
                    winner=d['folds']['full']['winner']
                    screens.append(dict(case=case,fragment=target['source']['fragment_id'],arm=arm,policy=s['policy'],screen_pass=s['screen_pass'],
                        **{k:winner[k] for k in ('norad','age_h','phase_s','rms_hz','bias_hz','rate_hz_s')},
                        minimum_margin=min(f['margin'] for f in d['folds'].values())))
    for r in rows:r['associated_pct']=100*r['associated']/r['total']
    summary=[]
    for arm in ARMS:
        baseline={r['case']:r['error_m'] for r in rows if r['arm']==arm and r['method']=='ALGO05'}
        for method in LABELS:
            rr=[r for r in rows if r['arm']==arm and r['method']==method];ee=np.array([r['error_m'] for r in rr])
            delta=np.array([r['error_m']-baseline[r['case']] for r in rr])
            summary.append(dict(arm=arm,method=method,count=len(rr),mean_m=float(ee.mean()),median_m=float(np.median(ee)),
                p90_m=float(np.quantile(ee,.9)),worst_m=float(ee.max()),within_500m=int((ee<=500).sum()),over_1km=int((ee>1000).sum()),
                associated=sum(r['associated'] for r in rr),total=sum(r['total'] for r in rr),
                associated_pct=100*sum(r['associated'] for r in rr)/sum(r['total'] for r in rr),added_points=sum(r['added_points'] for r in rr),
                changed_scans=sum(r['status']=='qualified' for r in rr),improved_over_25m=int((delta<-25).sum()),worsened_over_25m=int((delta>25).sum())))
    for name,rr in [('position-errors',rows),('summary',summary),('decisions',decisions),('trials',trials),('screen-summary',screens)]:csvfile(ROOT/(name+'.csv'),rr)
    write(ROOT/'summary.json',dict(rows=summary,decisions={p:dict(Counter(d['status'] for d in decisions if d['policy']==p)) for p in POLICIES},
        completed=len(cohort),unavailable=protocol['unavailable'],searched_fragments=sum(c['targets'] for c in cohort)))
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,arm in zip(axs,ARMS):
        for (method,label),color in zip(LABELS.items(),COLORS):
            e=np.sort([r['error_m']/1000 for r in rows if r['arm']==arm and r['method']==method])
            ax.step(e,np.arange(1,len(e)+1)/len(e),where='post',color=color,label=label,alpha=.8)
        ax.axvline(.5,ls=':',color='black');ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of usable DS28 scans',ylim=(0,1.03));ax.grid(alpha=.2)
    axs[0].legend(fontsize=8);fig.suptitle('DS28: baseline and fixed causal recovery variants (overlapping curves may coincide)')
    fig.savefig(ROOT/'position_error_distributions.png',dpi=170);plt.close(fig)
    cases=[c['case'] for c in cohort];fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for j,arm in enumerate(ARMS):
        for mi,((method,label),color) in enumerate(zip(LABELS.items(),COLORS)):
            rr=[next(r for r in rows if r['case']==c and r['arm']==arm and r['method']==method) for c in cases]
            xx=np.arange(len(cases))+(mi-2)*.12
            axs[0,j].scatter(xx,[r['error_m']/1000 for r in rr],label=label,color=color,s=28)
            axs[1,j].scatter(xx,[r['associated_pct'] for r in rr],color=color,s=28)
        for ax in axs[:,j]:ax.set_xticks(range(len(cases)),[c.split('-')[-1] for c in cases]);ax.grid(alpha=.2);ax.set_xlabel('DS28 scan')
        axs[0,j].set(title=arm,ylabel='Position error (km)');axs[1,j].set_ylabel('All native GLRT associated (%)')
    axs[0,0].legend(fontsize=8);fig.savefig(ROOT/'per_scan_results.png',dpi=170);plt.close(fig)
    atlas=['# DS28 physical candidate trials','','These are hypotheses, including rejections. Qualification requires both c arms and matched controls.','']
    if plots:
        (ROOT/'curves').mkdir(exist_ok=True)
        for case in sorted({p[0] for p in plots}):
            pp=[p for p in plots if p[0]==case];fig,axs=plt.subplots(len(pp),2,figsize=(12,3.5*len(pp)),squeeze=False,layout='constrained')
            for i,(_,name,t) in enumerate(pp):
                detail=t['arms']['fitted_c']['family_details'][-1];d=detail['diagnostics'][0];tt=np.asarray(d['times_s'])
                axs[i,0].scatter(tt,np.asarray(d['CFO_hz'])/1000,s=10,label='Native GLRT')
                axs[i,0].plot(tt,np.asarray(d['prediction_CFO_hz'])/1000,color='#d84b32',label='Corrected orbital prediction')
                axs[i,1].plot(tt,np.asarray(d['raw_residual_hz'])-d['profile_bias_hz'],'.-',ms=3);axs[i,1].axhline(0,color='black',lw=.8)
                axs[i,0].set(title=f"{case} NORAD {t['entry']['norad']}: {t['entry']['points']} points, ±{name.split('-')[-1]} s, {t['status']}",ylabel='CFO (kHz)',xlabel='Time (s)')
                axs[i,1].set(title=f"Profile RMS {d['profile_RMS_hz']:.1f} Hz, phase {detail['phase_map_s']:.2f} s",ylabel='Residual (Hz)',xlabel='Time (s)')
            axs[0,0].legend(fontsize=8);fig.savefig(ROOT/'curves'/(case+'.png'),dpi=150);plt.close(fig)
            atlas += [f'![{case}](curves/{case}.png)','']
    (ROOT/'CURVES.md').write_text('\n'.join(atlas))
    m=read(ROOT/'dataset/manifest.json');utc=lambda n:datetime.fromtimestamp(n/1e9,timezone.utc).isoformat()
    lines=['# DS28: fresh-cohort evaluation of causal TLE recovery variants','',
        f"DS28 contains {len(m['members'])} fast acquisitions in [{utc(m['start_utc_ns'])}, {utc(m['cutoff_utc_ns'])}). All are 10 Msps. {len(cohort)} have usable matched baseline results; {len(protocol['unavailable'])} remain unavailable and are retained in the roster.",'',
        'The current baseline is ALGO05 (ALGO04 plus conditional gap-fragment recovery). This study reuses exact public ALGO04 exports, replays installed ALGO05, then applies the four fixed research variants from the preceding DS26/DS27 experiment. It does not re-extract IQ or rerun cold regional acquisition. No production changes were made.','',
        '## Position and native GLRT association','',
        '| Arm | Method | Mean km | Median km | P90 km | Worst km | GLRT associated | Added points |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary:lines.append(f"| {r['arm']} | {LABELS[r['method']]} | {r['mean_m']/1000:.3f} | {r['median_m']/1000:.3f} | {r['p90_m']/1000:.3f} | {r['worst_m']/1000:.3f} | {r['associated_pct']:.3f}% | {r['added_points']} |")
    lines += ['', 'All four variants recover the same 28 native points in **DS28-0002 RX2 CH6 T001**, assigned to NORAD **64147**. Fitted-c error changes **294.3 → 277.7 m**; c=0 changes **463.8 → 443.7 m**. The causal TLE is only **14.72 hours old**, the screening phase is about −1.8 seconds, and the minimum identity margin over the partitions and both arms is 173.76. Thus this recovery comes from the additional residual search; it does not require an older TLE, expanded phase bounds, or a recency penalty.', '',
        'Across the seven usable scans, fitted-c mean error changes **652.8 → 650.4 m**, while the median (480.8 m), P90 (1,135.9 m), worst error (1,361.7 m), and four-of-seven count within 500 m remain unchanged. Native association rises from **20,937 / 27,721 (75.528%)** to **20,965 / 27,721 (75.629%)**. The c=0 mean changes 666.0 → 663.1 m. Numerical differences between the ±15 s and ±30 s accepted endpoints are below 0.1 mm.', '',
        'Frequency evidence is reported separately: the recovered curve has approximately **20.2 Hz bias-profiled RMS** in the physical fit. On matched baseline support, the mean recorded negative-twice-ELBO is **2.55 higher** for fitted-c than c=0, despite its 13.22 m lower mean geographic error. This penalized score is not a raw residual RMS. The no-addition continuation changes scan 0002 error by less than 1 mm, so the 16.52 m fitted-c reduction is attributable to the added curve rather than merely continuing optimization. See `frequency-fit-ablation.json` and `trials.csv`.', '',
        '**Recommendation:** retain the production default. DS28 supports a small additional recovery, but gives no incremental localization evidence for the 72-hour window, wider phase range, or recency penalty. The next useful work is the upstream failure in 0001 and the unchanged 1.362 km outlier in 0003. This cohort does not establish a general 500 m accuracy result.', '',
        '## Every DS28 scan', '', '| Scan | Status | Baseline fitted-c error, m | Recovery variants, m | Baseline GLRT | Recovery GLRT |', '|---|---|---:|---:|---:|---:|']
    for member in m['members']:
        case=member['dataset_label'];base=next((r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']=='ALGO05'),None)
        if base is None:lines.append(f'| {case} | Upstream discovery failed | — | — | Unknown | Unknown |');continue
        result=next(r for r in rows if r['case']==case and r['arm']=='fitted_c' and r['method']=='72h_30s')
        lines.append(f"| {case} | Complete | {base['error_m']:.1f} | {result['error_m']:.1f} | {base['associated_pct']:.2f}% | {result['associated_pct']:.2f}% |")
    lines += ['', 'DS28-0001 has complete recording and GLRT inputs. A fresh, unchanged installed ALGO02 retry fails after preparation during regional discovery with `ValueError: orbit phase interpolation never extrapolates`. Consequently ALGO05 and these conditional add-ons have no qualified incumbent to extend. It remains a failed result in all five method rosters; position error and association are unknown, not zero. See `upstream-failure.json` and `upstream-failure.log`. Successful-scan metrics cover 7/8 acquisitions (87.5% availability).']
    lines+=['','![Position error distributions](position_error_distributions.png)','','![Per-scan error and association](per_scan_results.png)','','## Fixed experiment','',
        'The variants use 48 h / ±15 s, 72 h / ±15 s, 72 h / ±30 s, and 72 h / ±30 s with the score penalty `2 log(2) max(age_h − 48, 0) / 24`. Both element epoch and archive collection must precede the scan and meet the age bound. Existing physical nuisance priors are retained; no age-dependent prior widening is introduced.','',
        f"The search covers {sum(c['targets'] for c in cohort)} residual fragments, at most three per scan with ≥20 native points and ≥15 seconds, ranked by duration independently of position error. Complete causal STARLINK catalogues are screened at the inferred RF endpoint; up to three candidates per policy, arm and training partition receive the normalized phase/offset/rate comparison. Three seeded random 12-second block holds with 2-second guards test identity stability. The minimum score margin is 10 in every partition and both arms.",'',
        'At most one new family per scan and policy is proposed. Existing-family extensions remain unchanged; at most two new families are integrated jointly. These variants are independent: a broader search can choose a different proposal and reject it, even when a narrower variant accepts its own proposal. Final position fits retain the physical orbit uncertainty model and use matched c=0/fitted-c observations, candidates, priors and budgets. A matched no-addition continuation isolates optimizer continuation from added evidence.','',
        'Both arms and controls must pass residual, phase convergence, visibility, incumbent-owner preservation, exact-orbit replay and quadrature agreement gates. Position quadrature is 0.05 s, checked at 0.025 and 0.0125 s. Rejections retain the baseline. Absolute frequency objectives across different point sets are not localization evidence. Trial objectives and control comparisons are recorded separately in the machine-readable results.','',
        'The 25 × 25 km inference box remains centered at 37.906, −122.545. The user-confirmed evaluation site (37.849061591561885, −122.48574968092912) enters only this reporting script after the inference seal. No future TLE or hand-picked satellite enters inference.','',
        '## Limits and reproduction','',
        'This is conditional recovery with a bounded shortlist and local position continuation. It does not demonstrate global satellite uniqueness or full regional reassociation. The physical model evaluates the nominated identity, rather than exhaustively reranking competitors. Eight single-site scans are a small generalization cohort.','',
        'Validation: **25 tests pass** across dataset boundaries/content identity, screening eligibility and grouped holds, normalized evidence, physical family mixtures and phase quadrature. All seven baseline selected likelihoods replay exactly; all seven fresh ALGO05 outputs match their public production decisions, positions and candidates. Every one of 10,464 nominal TLEs matches the independently exported causal catalogue. The final audit verifies 70 comparison rows, unique native IDs and preservation of every incumbent owner.','',
        'See `protocol.json`, `baseline-roster.json`, `dataset/manifest.json.gz`, `dataset-inventory.csv`, `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `decisions.csv`, `trials.csv`, and `inference-seal.json`. Every failed/unavailable scan is retained in the protocol. Native trial predictions and gate results are preserved under `position/`; [curve figures](CURVES.md) retain every attempted physical trial.','',
        'Run scripts with `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python`, `PYTHONPATH=src:tools`, and one BLAS/OMP thread. Sequence: dataset freeze; public baseline export; installed ALGO05 replay; `common.py`; `export_catalogues.py`; `screen.py preflight`; `screen.py screen`; `position.py`; `audit_replay.py`; `render.py`. The unchanged prior reconstruction implementation is imported with recorded hash, not modified.','']
    (ROOT/'README.md').write_text('\n'.join(lines));print(json.dumps(read(ROOT/'summary.json'),indent=2))

if __name__=='__main__':main()
