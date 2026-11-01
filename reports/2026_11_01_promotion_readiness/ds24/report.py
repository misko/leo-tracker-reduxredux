"""Report every frozen DS24 outcome; geographic truth is evaluation only."""
import csv
import json
from collections import Counter
from pathlib import Path
import time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent


def read(path):return json.loads(Path(path).read_text())


def csv_write(name, rows):
    with (OUT/name).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
        ['| '+' | '.join(map(str,row))+' |' for row in rows])


def main():
    protocol=read(OUT/'candidate/protocol.json');roster=read(OUT/'inputs/roster.json')
    source=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds25_fast_causal_variants')
    historical={(r['case'],r['arm']):r for r in csv.DictReader((source/'position-errors.csv').open()) if r['method']=='72h_30s'}
    rows=[];decisions=[]
    for case in protocol['cases']:
        result=read(OUT/'candidate'/case/'result.json')
        z=read(OUT/'inputs/inputs'/(case+'.json'))
        observations=read(Path(z['native_path'])/'observations.json')
        denominator=len({r['observation_id'] for r in observations})
        assert denominator==len(observations)
        base=protocol['baselines'][case]
        for arm in ('c0','fitted_c'):
            previous=historical[(case,arm)]
            assert abs(base[arm]['error_m']-float(previous['error_m']))<1e-5
            assert base[arm]['associated']==int(previous['associated'])
            assert denominator==int(previous['total'])
            final=result['final'][arm]
            rows.append(dict(case=case,arm=arm,status=result['execution_status'],selected=result['selected'],
                baseline_error_m=base[arm]['error_m'],candidate_error_m=final['error_m'],
                error_delta_m=final['error_m']-base[arm]['error_m'],
                baseline_associated=base[arm]['associated'],candidate_associated=final['associated'],
                total_glrt=denominator,baseline_objective=base[arm]['objective'],candidate_objective=final['objective'],
                candidate_rms_hz=final.get('rms_hz'),seconds=result.get('supervisor_seconds')))
        folder=OUT/'candidate'/case
        screens=[read(p) for p in folder.glob('*/screen.json')]
        trigger=read(folder/'trigger.json') if (folder/'trigger.json').exists() else {}
        recorded_guards={p.stem.removesuffix('-guard'):read(p) for p in folder.glob('*/*-guard.json')}
        recorded_guards.update(result.get('guards',{}))
        decisions.append(dict(case=case,status=result['execution_status'],selected=result['selected'],
            targets=trigger.get('selected',result.get('targets',[])),screens=len(screens),
            proposals=sum(len(s.get('proposals',[])) for s in screens),
            diagnostic_partition_proposals=sum('prediction_limit' in h for s in screens for h in s.get('proposals',[])),
            guards=recorded_guards,records=len(list(folder.glob('*/*/decision.json'))),
            seconds=result.get('supervisor_seconds'),history_completed=(folder/'history.json').exists()))
    summaries=[]
    for arm in ('c0','fitted_c'):
        subset=[r for r in rows if r['arm']==arm]
        for method,prefix in [('ALGO06','baseline'),('guarded_candidate','candidate')]:
            errors=np.array([r[prefix+'_error_m'] for r in subset]);delta=np.array([r['error_delta_m'] for r in subset])
            summaries.append(dict(dataset='DS24',arm=arm,method=method,n=len(subset),members=34,
                mean_m=float(errors.mean()),median_m=float(np.median(errors)),p90_m=float(np.percentile(errors,90)),
                p95_m=float(np.percentile(errors,95)),max_m=float(errors.max()),within500=int(sum(errors<500)),
                associated_pct=100*sum(r[prefix+'_associated'] for r in subset)/sum(r['total_glrt'] for r in subset),
                improved25=int(sum(delta < -25)) if prefix=='candidate' else 0,
                regressed25=int(sum(delta > 25)) if prefix=='candidate' else 0))
    csv_write('positions.csv',rows);csv_write('summary.csv',summaries)
    status=Counter(r['status'] for r in decisions);selected=[r for r in decisions if r['selected']]
    guards=[g for r in decisions for g in r['guards'].values()]
    latencies=np.array([r['seconds'] for r in decisions if r['seconds'] is not None])
    summary=dict(summaries=summaries,decisions=decisions,status=dict(status),unavailable=roster['unavailable'],
        activated=len(selected),tested_guards=len(guards),passed_guards=sum(g.get('passed',False) for g in guards),
        supervisor_latency_s=dict(median=float(np.median(latencies)),maximum=float(latencies.max())),
        settings_unchanged=protocol['settings']==read(OUT.parent/'candidate/protocol.json')['settings'])
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    proposals=[]
    for path in sorted((OUT/'candidate').glob('DS24-*/*/*/decision.json')):
        record=read(path);case=path.parts[-4]
        for arm in ('c0','fitted_c'):
            fit=record['pair'].get(arm) or {}
            proposals.append(dict(case=case,hypothesis=record['name'],arm=arm,
                accepted=record['accepted'],paired_physical_qualified=fit.get('qualified',False),
                penalized_RF_gain=record.get('gains',{}).get(arm),
                baseline_error_m=protocol['baselines'][case][arm]['error_m'],trial_error_m=fit.get('error_m')))
    if proposals:csv_write('proposal_decisions.csv',proposals)
    proposal_table=table(['Scan','Proposal','Arm','Physically qualified','Penalized RF gain','Accepted'],[
        [r['case'],r['hypothesis'],r['arm'],r['paired_physical_qualified'],
         f"{r['penalized_RF_gain']:.3f}" if r['penalized_RF_gain'] is not None else 'Unavailable',r['accepted']]
        for r in proposals]) if proposals else 'No proposal reached a complete full-fit decision.'
    fig,axes=plt.subplots(1,2,figsize=(12,4.7))
    for ax,arm in zip(axes,('c0','fitted_c')):
        subset=[r for r in rows if r['arm']==arm]
        for prefix,label,color,style in [('baseline','ALGO06','#555555','-'),('candidate','Guarded candidate','#0072b2','--')]:
            errors=np.sort([r[prefix+'_error_m']/1000 for r in subset])
            ax.step(errors,np.arange(1,len(errors)+1)*100/len(errors),where='post',label=label,color=color,linestyle=style,lw=2)
        ax.set(title=arm.replace('_',' '),xlabel='Position error (km)',ylabel='Available scans at or below error (%)',ylim=(0,102))
        ax.axvline(.5,color='#999999',ls=':',lw=1);ax.grid(alpha=.2);ax.legend()
    fig.suptitle('DS24 fast: frozen guarded candidate vs ALGO06 — 25 available / 34 members')
    fig.tight_layout();fig.savefig(OUT/'error_cdf.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
    for ax,arm in zip(axes,('c0','fitted_c')):
        subset=[r for r in rows if r['arm']==arm];xx=np.arange(len(subset))
        ax.plot(xx,[r['baseline_error_m']/1000 for r in subset],'o',mfc='none',ms=8,color='#555555',label='ALGO06')
        ax.plot(xx,[r['candidate_error_m']/1000 for r in subset],'x',color='#0072b2',label='Guarded candidate')
        ax.set(ylabel='Position error (km)',title=arm.replace('_',' '));ax.grid(alpha=.2);ax.legend()
    axes[-1].set_xticks(xx,[r['case'].removeprefix('DS24-') for r in subset],rotation=60)
    axes[-1].set_xlabel('DS24 scan label');fig.tight_layout();fig.savefig(OUT/'paired_errors.png',dpi=170);plt.close(fig)
    metrics=table(['Arm','Method','N','Mean km','Median km','P95 km','Worst km','GLRT associated'],[
        [r['arm'],r['method'],r['n'],*[f"{r[k]/1000:.3f}" for k in ('mean_m','median_m','p95_m','max_m')],f"{r['associated_pct']:.2f}%"] for r in summaries])
    cohort=list(csv.DictReader((OUT.parent/'population_summary.csv').open()))
    comparative=[]
    for dataset in ('DS24','DS26','DS27','DS28'):
        source_rows=summaries if dataset=='DS24' else [r for r in cohort if r['dataset']==dataset]
        pair={r['method']:r for r in source_rows if r['arm']=='fitted_c' and r['method'] in ('ALGO06','guarded_candidate')}
        comparative.append([dataset,pair['ALGO06']['n'],f"{float(pair['ALGO06']['mean_m'])/1000:.3f}",
            f"{float(pair['guarded_candidate']['mean_m'])/1000:.3f}", 'New candidate execution' if dataset=='DS24' else 'Retrospective saved-fit audit'])
    fresh=read(OUT.parent/'fresh_summary.json')['summary'];pair={r['method']:r for r in fresh if r['arm']=='fitted_c'}
    comparative.append(['Five fresh scans',5,f"{pair['ALGO06']['mean_m']/1000:.3f}",f"{pair['guarded_candidate']['mean_m']/1000:.3f}",'New candidate execution'])
    text=f'''# DS24 fast: guarded reassociation versus ALGO06

This completes the requested DS24 comparison using the frozen guarded candidate from the [promotion-readiness report](../README.md). Production remains ALGO06. The candidate has no new ALGO number and this evaluation changes no production state.

## Cohort and result

All 34 fast comparison acquisitions remain accounted for: 25 have saved qualified ALGO06 baselines and nine lack the frozen GLRT inputs. No scan is selected by geographic error. Candidate selections: **{len(selected)}/25**. Execution statuses: `{dict(status)}`. Missing baselines receive no invented position error.

{metrics}

![Position error distributions](error_cdf.png)

![Every available scan, both c arms](paired_errors.png)

## Comparison across evaluated datasets

The table reports mean fitted-c error. DS24 and the five fresh scans execute the new frozen candidate. DS26–28 retain the earlier retrospective decision-layer audit; they are not newly rerun here. DS23 still lacks this comparison. DS25 is adaptive-only; its 34 fast comparison recordings are these same DS24 members.

{table(['Cohort','Available scans','ALGO06 km','Guarded candidate km','Evidence'],comparative)}

## What was executed

The unchanged [candidate runner](../run_candidate.py), [acceptance policy](../policy.py), receiver-shared predictive checks, seeds, causal 72-hour catalogue, ±30 s phase bound, 25×25 km regional box, two prescribed starts, 15 phase rounds, 40 position iterations and 1200-second per-scan cap were retained. Eight isolated subprocesses run in parallel, with one numerical thread each. Both c arms use the same observations, nominees, priors and budgets. The known GPS site is used only for reporting error, never satellite selection or acceptance.

The [DS24 adapter](evaluate_ds24.py) composes the exact saved 72h/±30s ALGO06 research outcome, including its accepted addition where present. These are the same outcomes used in the [ALGO06 comparison](../../2026_11_01_ds24_plus_error_comparison/README.md); they are not newly fetched live production terminals. Before candidate search, all 25 baselines must reproduce both endpoints, normalized frequency objectives and native owner maps. The frozen input tree and complete prepared dependency trees are hashed before execution. Candidate and original sources are pinned independently; no scientific function or acceptance threshold is changed.

This is a new conditional reassociation evaluation over saved GLRT/graph/ALGO06 states, not a raw-IQ or regional cold-start rerun. The additional adapter only selects the DS24 input root, verifies saved-baseline authority and supervises the unchanged worker. Its baseline receipts explicitly identify research provenance and do not claim public V5 verification.

## Search accounting and limits

The search triggered {sum(len(r['targets']) for r in decisions)} families and saved {sum(r['proposals'] for r in decisions)} proposals. Of those, {sum(r['diagnostic_partition_proposals'] for r in decisions)} were diagnostic partitions, which the frozen candidate excludes from acceptance. There were {len(guards)} subsequent admission decisions: {sum(g.get('reason')=='destination_already_owned' for g in guards)} destinations already owned baseline points and were excluded; {sum(g.get('passed',False) for g in guards)} passed the receiver-shared predictive guard. Causal-history preparations: {sum(r['history_completed'] for r in decisions)}; full-fit proposal decisions: {sum(r['records'] for r in decisions)}. Completed searches: {status.get('complete',0)}/25. The policy preserves the exact ALGO06 baseline for rejected or incomplete searches. See [complete decisions](summary.json) and [per-scan metrics](positions.csv).

Median supervised candidate latency was {np.median(latencies):.2f} seconds; maximum {latencies.max():.2f} seconds. These are additional candidate costs, not total acquisition/GLRT/ALGO06 pipeline runtime; they include the worker's frozen-input validation and baseline replay.

DS24-0079 exposes an expensive baseline case. It already contains recovered families 100192 (44 points, ±15 s at 0.025 s spacing) and 63045 (62 points, ±30 s at 0.05 s spacing). Each has 1,201 phase nodes, so the exact shared-calibration likelihood integrates 1,442,401 pairs per objective evaluation. Influence ranking repeatedly evaluates this likelihood while omitting calibration families. A [nonblocking live stack snapshot](0079-runtime-stack-privileged.txt) caught that numerical integration inside `rank_families`; this is a mechanism diagnostic, not a statistical runtime profile. [Derived grid receipt](0079-runtime-analysis.json). The evaluation preserves the exact baseline and budget instead of dropping a recovered family or coarsening its phase grid.

Full-fit decisions below use the unchanged RF criterion: penalized gain must be positive in both arms, in addition to the physical and predictive gates. Trial position errors never select the outcome and rejected trials are excluded from the headline accuracy distributions.

{proposal_table}

DS24 was already studied during earlier algorithm development; this is additional existing-cohort qualification, not untouched-site validation. Lower frequency loss is reported separately in the per-scan table and never treated as proof of better positioning. An unchanged result does not establish that its satellite assignments are correct: the search only considers the frozen top-two influential families and bounded nominees. No gate is retuned using this evaluation. An initial preflight invocation before input preparation finished stopped on a missing roster, before any candidate search; its log is retained separately.

## Reproduction and audit

Run `evaluate_ds24.py prepare`, then `preflight`, `freeze`, and `run --workers 8` using the pinned numerical environment. The published protocol and audit record exact file hashes and runtime versions. Large prepared inputs remain local. [Tests](tests.txt), [preflight](candidate/preflight.json), [frozen protocol](candidate/protocol.json), [roster](roster.json), and [execution audit](execution-audit.json) retain the evidence needed to distinguish missing input, screening rejection, incomplete fit and accepted replacement.

The [publication manifest](publication-manifest.json) hashes the published artifacts and locally retained detailed fit/worker archives. Complete prepared-input hashes remain in the frozen protocol; candidate screening and final decision records are published.
'''
    (OUT/'README.md').write_text(text)
    print('Rendered',len(decisions),'outcomes;',len(selected),'selected;',dict(status))


if __name__=='__main__':main()
