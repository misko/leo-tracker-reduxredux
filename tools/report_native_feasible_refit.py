"""Document the matched optimizer ablation and a bounded graph inventory batch."""
import argparse
from collections import Counter
import csv, gzip, hashlib, json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read, write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study; out=args.output; out.mkdir(exist_ok=False,parents=True); (out/'figures').mkdir()
    evidence={}; hashes={}
    def load(path):
        path=Path(path); hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        r=read(path); evidence[str(path)]=r; return r
    def csvread(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    root=s/'native-feasible-0089-v2'; pr=load(root/'protocol.json'); load(root/'execution.json')
    load(s/'native-feasible-0089-v1/protocol.json');load(s/'native-feasible-0089-v1/execution.json')
    audit=load(root/'boundary_audit.json'); inv=load(Path(audit['inventory'])); old=inv['policy']
    rows=[]; results={}
    def collect(name,path):
        r=load(path);results[name]=r
        for arm,v in r['arms'].items():
            g=next(g for g in v['gates']['tracks'] if (g['norad']==64594 if r['job']['label']=='DS24-0089' else 'RX1-CH8-T002-' in g['component']))
            rows.append(dict(scan=r['job']['label'],trial=name,arm=arm,passes=r['paired_valid'],points=len(v['proposed_associated_ids']),
                added=v['added_points'],lost=v['lost_points'],error_km=error(v),
                negative_twice_elbo=v['negative_twice_elbo'],step_z=g['conditional_residual_gate']['diagnostics']['maximum_step_z'],
                final_phase_change_s=v['final_phase_change_s']))
    for j in pr['jobs']:
        terminal=load(root/(j['key']+'-terminal.json'))
        if terminal['status']!='complete':raise ValueError('native continuation incomplete')
        load(root/j['key']/'protocol.json')
        for p in sorted((root/j['key']).glob('*.json')):
            if p.stem in ('control','target_0','target_1','combined'):collect(j['key']+'/'+p.stem,p)
    objective_root=s/'native-feasible-0089-objective-control-v1'
    load(objective_root/'protocol.json')
    if load(objective_root/'terminal.json')['status']!='complete':raise ValueError('objective ablation incomplete')
    for p in sorted((objective_root/'trial').glob('*.json')):
        if p.stem in ('control','target_0','target_1','combined'):collect('same_objective_free/'+p.stem,p)
    for tid in ('749f0cad6f6a3e098e52','3a521e43a122a7f2c535','afad314bd4301aeedd3b'):
        collect('regional/'+tid,s/'native-evidence-inclusions-v1'/tid/'target_0.json')
    collect('regional/control',Path(audit['control']))
    second=s/'native-feasible-0083-v1';load(second/'protocol.json')
    for execution in load(second/'execution.json'):
        if execution['status']!='complete':raise ValueError('second scan incomplete')
        for name in ('control','combined'):
            collect('DS24-0083/'+execution['mode']+'/'+name,second/execution['mode']/(name+'.json'))
    csvout('native_trials.csv',rows)
    control_audit=[]
    for pattern in ('omitted-branch-inclusions-v*','flagged-native-inclusions-v*','native-evidence-inclusions-v1'):
        for folder in sorted(s.glob(pattern)):
            for p in sorted(folder.glob('*/control.json')):
                target=p.with_name('target_0.json')
                if not target.exists():continue
                c,r=read(p),read(target)
                for source in (p,target):hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
                control_audit.append(dict(source=str(p),branch_id=p.parent.name,scan=c['job']['label'],control_pass=c['paired_valid'],
                    target_pass=all(g['compatible'] for v in r['arms'].values() for g in v.get('targets',[])),trial_pass=r['paired_valid']))
    csvout('prior_native_control_audit.csv',control_audit)
    combined=results['disjoint_incumbent_feasible/combined']; free=results['same_objective_free/combined']
    ids=[set(t['observation_ids']) for t in combined['target_entries']]
    if ids[0]&ids[1] or sum(map(len,ids))!=89:raise ValueError('invalid joint identity union')
    if not combined['paired_valid'] or any(v['lost_points'] for v in combined['arms'].values()):raise ValueError('joint recovery failed')
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for d in combined['arms'][arm]['native_target_diagnostics']:
            label=f"{d['component'].split('-RX')[-1].split('-NATIVE')[0]} / {d['norad']} / {len(d['times_s'])} pts"
            line,=axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,label=label)
            axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=9,color=line.get_color())
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3,c=line.get_color())
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[0,col].legend(fontsize=7)
        axs[1,col].set(xlabel='Scan time (s)',ylabel='Bias-profiled residual (Hz)');axs[1,col].axhline(0,c='black',lw=.6)
        for ax in axs[:,col]:ax.grid(alpha=.2)
    fig.suptitle('DS24-0089: 89 distinct native points pass jointly\nCFO line includes orbit + receiver model, before independent track bias')
    fig.savefig(out/'figures/recovered_curves.png',dpi=150);plt.close(fig)
    other=results['DS24-0083/incumbent_feasible/combined'];other_free=results['DS24-0083/incumbent_elbo_unconstrained/combined']
    if not other['paired_valid'] or any(v['lost_points'] for v in other['arms'].values()):raise ValueError('second recovery failed')
    other_summary=[];fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(arm,v) in enumerate(other['arms'].items()):
        base=other['baseline'][arm]
        other_summary.append(dict(arm=arm,before_points=len(base['proposed_associated_ids']),after_points=len(v['proposed_associated_ids']),
            before_error_km=error(base),after_error_km=error(v),objective_cost_vs_same_data_free=v['negative_twice_elbo']-other_free['arms'][arm]['negative_twice_elbo']))
        for d in v['native_target_diagnostics']:
            line,=axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,label=f"{d['norad']} / {len(d['times_s'])} points")
            axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=9,color=line.get_color())
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3,c=line.get_color())
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[0,col].legend(fontsize=7)
        axs[1,col].set(xlabel='Scan time (s)',ylabel='Bias-profiled residual (Hz)');axs[1,col].axhline(0,c='black',lw=.6)
    fig.suptitle('DS24-0083: 93 additional disjoint points; original constraints, priors and identities')
    fig.savefig(out/'figures/ds24_0083_recovered.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(15,4),layout='constrained')
    a=audit['arms']['fitted_c'];focus=next(t['component'] for t in a['replays']['control']['tracks'] if not t['gate']['compatible'])
    for name,r in a['replays'].items():
        t=next(t for t in r['tracks'] if t['component']==focus)
        axs[0].plot(t['times_s'],t['residual_hz'],'.-',ms=4,label=name)
    axs[0].axhline(0,c='black',lw=.6);axs[0].set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)',title='Old RX1 CH1 T005 / 64594');axs[0].legend()
    line=a['line'];distance=[r['displacement_m'] for r in line]
    axs[1].plot(distance,[next(t['step_z'] for t in r['tracks'] if t['component']==focus) for r in line])
    axs[1].axhline(4,c='red',ls='--',label='Unchanged gate');axs[1].set(xlabel='Distance toward free endpoint (m)',ylabel='Maximum step z',title='Frozen-phase position slice');axs[1].legend()
    axs[2].plot(distance,[r['objective']-line[0]['objective'] for r in line]);axs[2].set(xlabel='Distance toward free endpoint (m)',ylabel='Change in −2 ELBO',title='Tiny objective gain crosses gate')
    for ax in axs:ax.grid(alpha=.2)
    fig.suptitle('Matched no-addition control: 32.32 m movement, not a newly added track, triggers the failure')
    fig.savefig(out/'figures/incumbent_boundary.png',dpi=150);plt.close(fig)
    lost=[dict(component=t['component'],points=t['points'],norads=t['frozen_satellites']) for t in a['lost_tracks']];csvout('lost_extension_tracks.csv',lost)
    # Cohort update is an accounting overlay on the prior research policy;
    # no other scans are rerun or silently relabeled as validated.
    previous=csvread(args.previous/'policy_position_and_coverage.csv');cohort=[]
    for r in previous:
        replacement={'DS24-0089':combined,'DS24-0083':other}.get(r['scan'])
        v=replacement['arms'][r['arm']] if replacement else None
        if v and int(r['new_points'])!=len(replacement['baseline'][r['arm']]['proposed_associated_ids']):raise ValueError('prior policy mismatch')
        cohort.append(dict(scan=r['scan'],arm=r['arm'],total_GLRT=int(r['total_GLRT']),before_points=int(r['new_points']),
            after_points=len(v['proposed_associated_ids']) if v else int(r['new_points']),before_error_km=float(r['new_error_km']),
            after_error_km=error(v) if v else float(r['new_error_km']),new_fit=bool(v)))
    csvout('cohort_accounting.csv',cohort);metrics=[]
    for arm in ('c0','fitted_c'):
        rr=[r for r in cohort if r['arm']==arm]
        for variant in ('before','after'):
            errors=[r[variant+'_error_km'] for r in rr];points=sum(r[variant+'_points'] for r in rr)
            metrics.append(dict(arm=arm,variant=variant,scans=len(rr),points=points,associated_percent=100*points/sum(r['total_GLRT'] for r in rr),
                mean_error_km=float(np.mean(errors)),median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9))))
    csvout('cohort_metrics.csv',metrics)
    # Append assessments without changing the frozen 1,630-entry denominator.
    ledger=csvread(args.previous/'annotation_ledger.csv');byid={r['track_id']:r for r in ledger};batch=[]
    queue=s/'systematic-annotation-v1';attempt=queue/'attempt-18';load(attempt/'protocol.json')
    for r in load(attempt/'selected.json'):
        tid=r['track_id'];term=load(attempt/(tid+'-terminal.json'))
        item=dict(scan=r['label'],track_id=tid,execution=term['status'],status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            source=queue/tid/'result.json';result=load(source);vote=identity_consensus(result['folds'],score_name=result.get('identity_score_name','joint'))
            item.update(status=vote['status'],norad=vote['norad'])
            byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),annotation_source=str(source),
                partition_policy='distinct timestamps',geometry_only_early_exit=result.get('geometry_only_early_exit',False),distinct_schedule_ready=not result.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=item['status']
        batch.append(item)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('ledger changed')
    csvout('annotation_ledger.csv',ledger);csvout('graph_annotation_batch.csv',batch)
    graph=s/'graph-inclusion-batch17-v1';gp=load(graph/'protocol.json');gr=[];gallery=[]
    for j in gp['jobs']:
        tid=j['track_id'];term=load(graph/(tid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('incomplete graph trial')
        r=load(graph/tid/'target_0.json');c=load(graph/tid/'control.json')
        fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(r['arms'].items()):
            t=v['targets'][0];gr.append(dict(scan=j['label'],track_id=tid,arm=arm,passes=r['paired_valid'],control_passes=c['paired_valid'],
                target_pass=t['gate']['compatible'],norad=t['gate']['norad'],added=v['added_points'],lost=v['lost_points'],
                before_error_km=error(c['arms'][arm]),after_error_km=error(v)))
            axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=9)
            axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        fig.suptitle(f"{j['label']} / {tid} / paired pass: {r['paired_valid']}")
        file='figures/'+tid+'.png';fig.savefig(out/file,dpi=120);plt.close(fig);gallery.append(f"## {j['label']}\n\n![Graph trial]({file})\n")
    csvout('graph_trials.csv',gr);(out/'graph_gallery.md').write_text('# All 20 graph inclusion trials\n\n'+'\n'.join(gallery))
    ga=load(graph/'gate_audit.json');failures=[]
    for r in ga['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in r[key]:
                if not v['compatible']:failures.append(dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,target=v.get('target',False),component=v['component'],failures=';'.join(v['failures'])))
    csvout('graph_gate_failures.csv',failures)
    summary=dict(graph_assessed=sum(bool(r['annotation_source']) for r in ledger),graph_total=len(ledger),
        graph_annotation_outcomes=dict(Counter(r['status'] for r in batch)),graph_passing=sum(r['passes'] for r in gr if r['arm']=='fitted_c'),
        native_added=182,old_points_lost=0,production_changed=False,independent_identity_validation=False)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    total=int(inv['summary'][0]['total_GLRT'])
    native_summary=[dict(arm=arm,before_points=len(old[arm]['proposed_associated_ids']),after_points=len(v['proposed_associated_ids']),
        before_percent=100*len(old[arm]['proposed_associated_ids'])/total,after_percent=100*len(v['proposed_associated_ids'])/total,
        before_error_km=error(old[arm]),after_error_km=error(v),objective_cost_vs_same_data_free=v['negative_twice_elbo']-free['arms'][arm]['negative_twice_elbo']) for arm,v in combined['arms'].items()]
    (out/'README.md').write_text(f'''# DS24-0089 and DS24-0083: recovery refits dropped existing acceptance constraints

The previous iteration described three recovered curves as making an old CH1 track fail. **The matched no-addition control already failed.** Exact replay identifies a fitting-procedure mismatch: the accepted incumbent was gate-constrained, while the recovery experiment ran an unconstrained position optimizer. This finding supersedes the earlier causal interpretation. It does not establish that every remaining unassociated curve has this cause.

## Controlled experiment and result

Use the same causal catalogue, identities, alias choices, receiver/orbit priors, calibration observations, target observations, and acceptance checks. Compare the original regional unconstrained run with RF-incumbent continuations. The original unconstrained fitter uses bounded Gauss–Newton on its residual vector, whereas the constrained fitter uses SLSQP on negative twice ELBO. To separate optimizer/objective effects from the gate constraints, also run the exact SLSQP helper and objective with physical gate slacks replaced by the constant one. This third continuation retains the same start, phase refresh, bounds, finite-difference step and iteration limit. Each continuation has five phase refreshes and up to 48 optimizer iterations per refresh in both c arms. Actual objective-evaluation counts differ; receipts preserve them. The constrained solver retains its existing 1e-6 numerical interior, followed by independent final gates and the no-old-point-loss check. GPS is used only for error reporting, never candidate or optimizer selection. Continuations are not new blind regional acquisitions; their incumbent arose from the preceding 25×25 km RF analysis.

All three individual proposals pass under constrained continuation, and all fail under the original unconstrained continuation. The same-objective SLSQP no-addition control, two individual additions, and joint addition all fail their paired checks; these results are included in the CSV. The 43-point RX2 CH2 proposal is wholly contained in the 61-point proposal. A first joint assembly correctly rejected this overlap before fitting; its failed execution receipts remain archived. The valid joint experiment uses the full 61-point RX2 CH2 curve (69255) plus the disjoint 28-point RX1 CH4 curve (64599). **89 distinct points are added, with zero old points lost**, in both arms. No truncation, new nuisance coefficient, TLE change, or threshold relaxation was needed.

{table(native_summary,['arm','before_points','after_points','before_percent','after_percent','before_error_km','after_error_km','objective_cost_vs_same_data_free'])}

The coverage increase is material; the localization change is not: fitted-c improves about 2.7 m, while c=0 worsens about 18.4 m. Frequency scores are compared only between constrained and free fits of identical observations. Adding observations changes the likelihood dimension, so raw total scores before/after adding points are not a model-quality comparison. [All native controls and trials](native_trials.csv) include rejected results and phase convergence.

![Recovered native curves](figures/recovered_curves.png)

## Why 63 old points disappeared

The old RX1 CH1 T005 / 64594 has 31 active points. Its fitted-c step statistic is 3.999995859 at the frozen incumbent and 4.008525933 at the original unconstrained control, against the unchanged limit of 4. The control moves only 32.319 m and improves negative twice ELBO by approximately 0.004585. Exact objective, gate, and observation-membership replay succeeds in both c arms. Warm-starting the free optimizer still fails even after phase convergence; this is not explained by the regional starting point or a stale phase linearization.

When that track fails, 64594 has no compatible curved representative to nominate it during post-fit graph extension. Three other graph tracks lose their extension associations: RX2 CH1 T007 (13 points), RX1 CH3 T007 (23), and RX1 CH4 T010 (27). These are the 63 lost points. The active 31-point track remains in the calibration mask, but the whole trial is rejected; proposed membership counts in rejected trials are not accepted coverage.

![Gate boundary and incumbent residual](figures/incumbent_boundary.png)

The right two panels sample a one-dimensional position segment, using the frozen incumbent phase reference and re-profiling nuisance coefficients at each position. They are not full pipeline reruns or fully phase-refreshed two-dimensional loss surfaces. The left panel compares exact saved endpoint residuals. Borderline acceptance remains a scientific weakness: constrained fitting can preserve a threshold without establishing model correctness or identity. Independent prediction and false-association checks are still needed before promotion.

## Second case: DS24-0083

Auditing prior matched controls identifies one other scan with the same experimental defect: four DS24-0083 proposals pass their own target checks, but the no-addition control fails existing RX1 CH8 T002 in c=0. Select the maximal disjoint proposal set using observation IDs only: 30 RX1 CH2 points and 22 RX1 CH1 points assigned to 64309, plus 41 RX1 CH5 points assigned to 100312. The fourth, 26-point proposal is contained in the 30-point branch and is excluded to avoid duplication. This is a diagnostic follow-up selected by control failure, not an independent blind validation cohort.

Using the same SLSQP objective, start, bounds and budget, the unconstrained control and joint trial both fail, while the constrained control and joint trial both pass. **93 points are added, with zero old-point losses.** The old CH8 curve retains autocorrelation in the rejected free fit; its RMS is only about 58 Hz, illustrating why an RMS-only gate misses the problem. Original noise thresholds remain in force. Both c arms are required to pass.

{table(other_summary,['arm','before_points','after_points','before_error_km','after_error_km','objective_cost_vs_same_data_free'])}

Position changes again disagree across c arms: c=0 improves about 10 m, while fitted-c worsens about 48 m. Tiny negative objective differences in an inactive-constraint arm reflect numerical optimizer termination, not a claim that constraining an exact global optimum lowers its objective. The result supports the experimental repair but does not establish a localization benefit.

![DS24-0083 recovered curves](figures/ds24_0083_recovered.png)

## Cohort accounting and remaining graph inventory

An accounting overlay on the preceding 93-scan native research policy adds the two measured joint results, totaling **182 points**; the other 91 scans reuse their previous results. This is not a new dataset-wide optimizer validation. Both scan baselines match the previous policy's point counts; no native recovery is overwritten. Nine unavailable exports remain excluded.

{table(metrics,['arm','variant','points','associated_percent','mean_error_km','median_error_km','p90_error_km'])}

The parallel graph annotation batch yields {summary['graph_annotation_outcomes']}. **{summary['graph_assessed']} / {summary['graph_total']}** frozen graph entries now have assessments. Native proposals and original graph entries are separate inventories and are never summed. [Full ledger](annotation_ledger.csv) and [batch outcomes](graph_annotation_batch.csv) include timeouts explicitly.

Twenty supported graph hypotheses from the preceding batch received original-model paired position trials. **{summary['graph_passing']} / 20 pass.** The passing AUTO-e32d57a7 / 68560 trial adds 61 points, but error worsens from 2.486 to 2.749 km for c=0 and 2.478 to 2.738 km for fitted-c. This is separate automatic-recording evidence, not part of the DS24 native cohort overlay; it reinforces that coverage alone is not localization improvement. [Both-arm results](graph_trials.csv), [replayed failing gates](graph_gate_failures.csv), and [all CFO/residual plots](graph_gallery.md) preserve the failures as well as the pass.

## Reproduction and next decisions

`include_predictive_annotations.py --position-fit incumbent_unconstrained`, `--position-fit incumbent_elbo_unconstrained`, and `--position-fit incumbent_feasible` expose explicit research-only continuations. The default regional experiment is unchanged. The protocol archives exact commands, input paths and source hash. `audit_native_refit_boundary.py` verifies frozen and control replay; `report_native_feasible_refit.py` generates this report. The initial four continuation jobs and the additional objective control have 600-second caps; the two DS24-0083 jobs have 300-second caps. The graph queue uses 16 workers with 600-second per-case caps. No new RF collection or production deployment occurred.

The [prior native control audit](prior_native_control_audit.csv) checks {len(control_audit)} saved matched trials. Seven have failing no-addition controls despite passing target gates: the three DS24-0089 cases above and four DS24-0083 proposals. Both distinct scans now have matched constrained/free joint experiments. Audit counts are trials, not distinct scans or disjoint point totals.

Next, carry the incumbent fit procedure explicitly into recovery evaluation so failing no-addition controls are not attributed to new evidence. Separately test receiver/orbit mismatch for targets that fail their own predictive residual checks. Validate the exploratory identity score on difficult negative controls and separate recordings. Do not promote an ALGO solely from recovered point counts or gate-feasible endpoints. The full annotation/recovery objective remains open.

[Source hashes](sources.json), [compact numerical archive](evidence.json.gz), [cohort accounting](cohort_accounting.csv), and [summary](summary.json). Repetitive observation lists/history are compacted to hashes where supported; original files remain at the recorded paths.
''')
    print(json.dumps(dict(summary=summary,native=native_summary,metrics=metrics),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
