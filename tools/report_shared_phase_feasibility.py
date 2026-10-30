"""Publish exact phase feasibility, grouped prediction and bounded inventory work."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(exist_ok=False,parents=True);(out/'figures').mkdir()
    evidence={};hashes={}
    def load(path):
        path=Path(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        r=read(path);evidence[str(path)]=r;return r
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    root=s/'native-0093-phase-feasibility-v2';pr=load(root/'protocol.json');r=load(root/'result.json')
    summary=[];gates=[];fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for row,(name,arms) in enumerate(r['endpoints'].items()):
        ep=Path(pr['endpoints'][row]);original=load(ep/'target_0.json')
        for col,(arm,v) in enumerate(arms.items()):
            a,b=v['initial'],v['selected'];native0=a['curves'][-1];native1=b['curves'][-1]
            summary.append(dict(endpoint='original' if row==0 else 'conditional',arm=arm,
                original_phase_s=a['phase_s'],selected_phase_s=b['phase_s'],
                target_RMS_before_hz=native0['RMS_hz'],target_RMS_after_hz=native1['RMS_hz'],
                minimum_all_gate_slack=b['minimum_all_slack'],sampled_feasible_phases=v['sampled_feasible_points'],
                conditional_score_penalty_vs_unconstrained=b['score']-v['unconstrained']['score'],
                fixed_position_error_km=error(original['arms'][arm]),
                receiver_change=b['receiver_coefficient_change'],accepted_into_policy=False))
            for stage in ('initial','selected','unconstrained'):
                gates.extend(dict(endpoint=name,arm=arm,stage=stage,gate=k,slack=q) for k,q in v[stage]['all_gate_slacks'].items())
            ax=axs[row,col];grid=np.array(v['grid_phase_s']);mask=abs(grid-a['phase_s'])<.13
            for curve in v['curve_grid']:
                critical='RX1-CH4-T003' in curve['component'];native=curve['kind']=='target'
                ax.plot(grid[mask],np.array(curve['minimum_slack'])[mask],color='#0072b2' if native else '#d55e00' if critical else '#aaaaaa',
                    alpha=1 if native or critical else .45,lw=2 if native or critical else .7,
                    label='New 49-point curve' if native else 'Existing RX1 CH4 T003' if critical else None)
            ax.plot(grid[mask],np.array(v['grid_minimum_family_slack'])[mask],c='black',ls=':',label='All family curves')
            for lo,hi,_ in v['sampled_joint_intervals']:ax.axvspan(lo,hi,color='#009e73',alpha=.2)
            ax.axhline(0,c='black',lw=.7);ax.axvline(a['phase_s'],c='black',ls='--',label='Saved phase')
            ax.axvline(b['phase_s'],c='#009e73',ls='-',label='Selected feasible phase')
            ax.set(xlabel='Shared satellite phase (s)',ylabel='Minimum normalized gate slack',ylim=(-1.5,.55),
                title=('Original RF endpoint' if row==0 else 'Conditional RF endpoint')+' / '+arm)
            ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle('DS24-0093 / NORAD 58189: common phase support exists\nPosition, receiver and orbit coefficients fixed; positive slack passes unchanged gates')
    fig.savefig(out/'figures/phase_support.png',dpi=145);plt.close(fig)
    csvout('phase_summary.csv',summary);csvout('all_gate_slacks.csv',gates)
    original_arms=next(iter(r['endpoints'].values()));fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,(arm,v) in enumerate(original_arms.items()):
        for row,selector in enumerate(('NATIVE','RX1-CH4-T003')):
            k=next(k for k,c in enumerate(v['curves']) if selector in c['component']);t=v['curves'][k]['times_s']
            for stage,color,label in [('initial','#888888','Original shared phase'),('selected','#0072b2','Feasible shared phase')]:
                q=v[stage]['curves'][k];axs[row,col].plot(t,q['residual_hz'],'.-',c=color,label=label+f" ({q['RMS_hz']:.1f} Hz)")
            axs[row,col].axhline(0,c='black',lw=.6);axs[row,col].grid(alpha=.2);axs[row,col].legend(fontsize=8)
            axs[row,col].set(title=arm+' / '+('new 49-point curve' if row==0 else 'existing RX1 CH4 T003'),xlabel='Time (s)',ylabel='Residual (Hz)')
    fig.suptitle('The compromise preserves both curves; no per-curve slope or polynomial correction')
    fig.savefig(out/'figures/residual_compromise.png',dpi=145);plt.close(fig)
    # Every family curve, including existing predictive curves, stays visible.
    gallery=[]
    for page,start in enumerate(range(0,len(next(iter(original_arms.values()))['curves']),6)):
        fig,axs=plt.subplots(6,2,figsize=(12,16),layout='constrained')
        for col,(arm,v) in enumerate(original_arms.items()):
            for row in range(6):
                ax=axs[row,col];k=start+row
                if k>=len(v['curves']):ax.axis('off');continue
                cc=v['curves'][k]
                for stage,color in [('initial','#999999'),('selected','#0072b2')]:ax.plot(cc['times_s'],v[stage]['curves'][k]['residual_hz'],'.-',c=color,ms=3,label=stage)
                ax.axhline(0,c='black',lw=.5);ax.grid(alpha=.2);ax.set(title=arm+' / '+cc['component'].replace('DS24-0093-',''),xlabel='Time (s)',ylabel='Residual (Hz)');ax.legend(fontsize=7)
        f=f'figures/family_residuals_{page+1}.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f'![Every family curve, page {page+1}]({f})')
    (out/'family_gallery.md').write_text('# All same-family residuals at the original RF endpoints\n\n'+'\n\n'.join(gallery)+'\n')
    held=load(s/'native-0093-phase-validation-v1/result.json');load(s/'native-0093-phase-validation-v1/protocol.json');hrows=[];wrows=[]
    for fold in held['folds']:
        for arm,v in fold['arms'].items():
            a=v['variants']['existing_only'];b=v['variants']['existing_plus_native']
            def aggregate(q):
                values=np.array([z for c in q['curves'] if c['kind']=='existing' for z in c['residual_hz']])
                return len(values),float(np.sqrt(np.mean(values**2)))
            n,before=aggregate(a);_,after=aggregate(b)
            hrows.append(dict(seed=fold['seed'],arm=arm,target_held_points=a['curves'][-1]['held_points'],
                target_before_RMS_hz=a['curves'][-1]['RMS_hz'],target_after_RMS_hz=b['curves'][-1]['RMS_hz'],
                existing_held_points=n,existing_before_RMS_hz=before,existing_after_RMS_hz=after,
                before_phase_s=a['phase_s'],after_phase_s=b['phase_s']))
            for aa,bb in zip(a['curves'],b['curves'],strict=True):
                wrows.append(dict(seed=fold['seed'],arm=arm,component=aa['component'],kind=aa['kind'],training_points=aa['train_points'],held_points=aa['held_points'],before_RMS_hz=aa['RMS_hz'],after_RMS_hz=bb['RMS_hz']))
    csvout('held_predictions.csv',hrows);csvout('held_witnesses.csv',wrows)
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,prefix,title in zip(axs,['target','existing'],['New curve: withheld points','Existing same-family curves: withheld points'],strict=True):
        xx=np.arange(len(hrows));ax.bar(xx-.18,[q[prefix+'_before_RMS_hz'] for q in hrows],.36,color='#999999',label='Phase learned from existing curves')
        ax.bar(xx+.18,[q[prefix+'_after_RMS_hz'] for q in hrows],.36,color='#0072b2',label='Phase learned with native training points')
        ax.set(xticks=xx,xticklabels=[str(q['seed'])+'\n'+q['arm']+f"\nn={q[prefix+'_held_points']}" for q in hrows],title=title,ylabel='Held RMS (Hz)');ax.tick_params(axis='x',labelsize=8);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Three randomized scan-wide 12-second block partitions; 2-second guards\nAll calibration, shared phase and curve constants learned without held values')
    fig.savefig(out/'figures/held_predictions.png',dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={v['track_id']:v for v in ledger};queue=s/'systematic-annotation-v1';batch=[]
    attempt=queue/'attempt-20';load(attempt/'protocol.json')
    for q in load(attempt/'selected.json'):
        tid=q['track_id'];term=load(attempt/(tid+'-terminal.json'));v=dict(scan=q['label'],track_id=tid,status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            path=queue/tid/'result.json';a=load(path);vote=identity_consensus(a['folds'],score_name=a.get('identity_score_name','joint'))
            v.update(status=vote['status'],norad=vote['norad']);byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=a.get('geometry_only_early_exit',False),distinct_schedule_ready=not a.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=v['status']
        batch.append(v)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('inventory changed')
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch)
    groot=s/'graph-inclusion-batch19-v1';gp=load(groot/'protocol.json');graph=[];gallery=[]
    for job in gp['jobs']:
        tid=job['track_id'];term=load(groot/(tid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('incomplete inclusion')
        q=load(groot/tid/'target_0.json');control=load(groot/tid/'control.json');fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(q['arms'].items()):
            t=v['targets'][0];graph.append(dict(scan=job['label'],track_id=tid,arm=arm,passes=q['paired_valid'],control_passes=control['paired_valid'],
                norad=t['gate']['norad'],added=v['added_points'],lost=v['lost_points'],before_error_km=error(control['arms'][arm]),after_error_km=error(v)))
            axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=9);axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        fig.suptitle(f"{job['label']} / {tid} / paired pass {q['paired_valid']}");f=f'figures/{tid}_graph.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f"## {job['label']}\n\n![Graph trial]({f})")
    csvout('graph_trials.csv',graph);(out/'graph_gallery.md').write_text('# All 16 graph inclusion trials\n\n'+'\n\n'.join(gallery)+'\n')
    audit=load(groot/'gate_audit.json');failures=[]
    for q in audit['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in q[key]:
                if not v['compatible']:failures.append(dict(scan=q['scan'],track_id=q['track_id'],arm=q['arm'],role=role,component=v['component'],failures=';'.join(v['failures'])))
    csvout('graph_gate_failures.csv',failures)
    passing=[v for v in graph if v['passes']];fig,axs=plt.subplots(1,2,figsize=(11,5),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for accepted,color in [(False,'#aaaaaa'),(True,'#0072b2')]:
            rows=[q for q in graph if q['arm']==arm and q['passes']==accepted]
            ax.scatter([v['before_error_km'] for v in rows],[v['after_error_km'] for v in rows],c=color,label='Pass' if accepted else 'Rejected trial')
        limit=max([v[k] for v in graph if v['arm']==arm for k in ('before_error_km','after_error_km')])*1.05
        ax.plot([0,limit],[0,limit],'k--',lw=.8);ax.set(title=arm,xlabel='Matched control error (km)',ylabel='Target trial error (km)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Separate automatic-recording cohort: rejected outcomes remain visible')
    fig.savefig(out/'figures/graph_position_effects.png',dpi=145);plt.close(fig)
    result=dict(graph_assessed=sum(bool(v['annotation_source']) for v in ledger),graph_total=len(ledger),
        graph_annotation_outcomes=dict(Counter(v['status'] for v in batch)),graph_passing=sum(v['passes'] for v in graph if v['arm']=='c0'),
        graph_added_points_per_arm=sum(v['added'] for v in passing if v['arm']=='c0'),
        native_target_held_RMS_wins=sum(v['target_after_RMS_hz']<v['target_before_RMS_hz'] for v in hrows),
        existing_held_RMS_wins=sum(v['existing_after_RMS_hz']<v['existing_before_RMS_hz'] for v in hrows),
        held_comparisons=len(hrows),native_new_policy_points=0,production_changed=False)
    write(out/'summary.json',result);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    (out/'README.md').write_text(f'''# Shared-phase feasibility: DS24-0093 and the next inventory batch

DS24-0093's 49-point RX1 CH4 native curve can coexist with all old associations under the existing residual, alias, elevation and owner gates. At both previously saved RF endpoints, a narrow interval of shared NORAD **58189** phase values satisfies every gate in both c arms. Position, receiver coefficients, orbit coefficients, observations and identities remain fixed. This disproves the narrower hypothesis that the old and new curves necessarily conflict at these endpoints; it does not prove the satellite identity or improve position by itself.

This follows the [parameter consistency report](../2026_10_30_native_parameter_consistency/README.md). No native points from this experiment enter the accepted research-policy totals and production is unchanged. Separately, two of 16 original-model graph trials pass and add 104 points across two automatic recordings, with no old points lost. These are a separate cohort, not additions to DS24's native-recovery percentage.

## Why the previous optimizer rejected a feasible family

The previous position solver varied east/north coordinates while phase and fragment constants were set to posterior means. Its feasible search therefore could not explore every admissible phase realization at a fixed position. The unconstrained satellite/bias update preferred a phase just beyond the old RX1 CH4 T003 slope gate. The original model's phase left a slope and other structure in the new curve. A small compromise in the **same existing phase parameter** satisfies both.

We replay both saved RF-only endpoints and their objectives to 1e-5. The phase diagnostic uses exact causal orbit evaluation, including the existing physical orbit correction at each trial phase, rather than relying on a stale linearization. Receiver and orbit coefficients stay fixed. Existing curved-fragment constants are reconciled analytically with their original 300 Hz prior and frozen hierarchical noise precision. Original profile checks still use their original 1,000 Hz profile constant; native/predictive checks retain their 300 Hz constant. These different conditional/profile operations reproduce the existing gate definitions.

The conditional phase score includes the existing phase prior, weighted old-curve residuals and constant penalties, plus predictive-curve variance **2 × sigma²** and 300 Hz constants. Other coefficients and Gamma precisions are conditioned at their saved values. This conditional MAP score is not the marginalized position ELBO, and its decrease is not evidence of better location accuracy.

The grid covers −15 to +15 seconds at 0.1-second spacing, plus ±1 second around each saved phase at 0.002-second spacing. We record sampled passing runs without interpolating over failing samples. These narrow intervals are about 10–18 milliseconds wide at the sampled endpoints; a coarse grid can miss them. The best sampled phase by conditional score **among passing family phases** is replayed against every original curved/predictive gate in the scan. The complete scan passes at all four selected phases. This is an existence demonstration, not a proof of global optimality or completeness of the coarse search.

{table(summary,['endpoint','arm','original_phase_s','selected_phase_s','target_RMS_before_hz','target_RMS_after_hz','minimum_all_gate_slack','conditional_score_penalty_vs_unconstrained','fixed_position_error_km'])}

Position errors describe the frozen source-trial endpoints, which were previously rejected as complete fits; they are **not newly accepted localization results**. The phase scan cannot change those errors. All receiver-coordinate changes are exactly zero. No per-track slopes, higher-order polynomials, new orbital modes, expanded priors, relaxed gates or future TLEs are used. GPS appears only in report evaluation.

![Shared phase support](figures/phase_support.png)

![New/old curve residual compromise](figures/residual_compromise.png)

[Every family residual](family_gallery.md), [phase summary](phase_summary.csv), and [all scan gate slacks](all_gate_slacks.csv) preserve the old-curve costs of the compromise. The highest-likelihood feasible values lie close to a gate boundary; their positive slack should not be mistaken for strong statistical assurance.

## Does a phase learned without the test points help them?

Three previously recorded distinct randomized 12-second block partitions, with two-second guards, are applied across the entire scan. Receiver/position calibration is refitted from the regional center using only old curved training points, fixed 150 Hz noise and unit curve powers. The one-dimensional exact phase search then compares learning from old training curves alone with learning from old plus native training points. Both use the same causal priors, fixed training receiver/orbit coefficients and train-only curve constants. The phase grid is centered using training calibration only. Selection minimizes training conditional cost and never examines held residuals. Old witness curves require at least four training points; omitted curves are not implied to have been validated.

{table(hrows,['seed','arm','target_held_points','target_before_RMS_hz','target_after_RMS_hz','existing_held_points','existing_before_RMS_hz','existing_after_RMS_hz'])}

The native curve improves in **{result['native_target_held_RMS_wins']}/{result['held_comparisons']}** comparisons. Existing same-family held RMS improves in **{result['existing_held_RMS_wins']}/{result['held_comparisons']}**; the remaining comparisons worsen. The last partition has only seven old-family held points, so its large apparent improvement has limited support. These are overlapping randomized partitions, not independent experiments to pool into significance. The graph and identity hypothesis were previously selected using full observations; this is conditional model validation, not an independent false-association test. Phase/position uncertainty is not integrated in these RMS diagnostics. Other-family predictions are unchanged because receiver, position and their satellite parameters remain fixed.

![Withheld predictions](figures/held_predictions.png)

[Held summary](held_predictions.csv) and [every held witness](held_witnesses.csv) retain the mixed outcomes. This supports explicitly representing shared satellite nuisance variables during constrained optimization. It does not yet authorize promoting this procedure or counting the 49 native points as recovered.

## Bounded inventory and original-model graph inclusions

The original graph ledger advances from 836 to **{result['graph_assessed']}/1,630** scientifically assessed entries. This batch's execution/scientific outcomes are `{result['graph_annotation_outcomes']}`. Timeouts remain explicit unresolved executions, not scientific rejections. Native overlapping proposals are kept separate from these 1,630 graph entries.

All 16 supported identities from the preceding completed batch receive matched original-model control/target position trials. Both c arms use the same observations, candidates, priors and budgets. Two trials pass every qualification and preserve all old points; the other 14 are retained as rejected outcomes with their gate failures. Passing scientific checks does not establish true satellite identity or guarantee better localization.

{table(passing,['scan','arm','norad','added','lost','before_error_km','after_error_km'])}

![Graph position effects](figures/graph_position_effects.png)

[All 16 GLRT/orbit/residual plots](graph_gallery.md), [all position trials](graph_trials.csv), [replayed failures](graph_gate_failures.csv), [updated ledger](annotation_ledger.csv), and [batch classifications](annotation_batch.csv).

## Next bounded experiment

Prototype an explicit shared-phase constrained fit with the unchanged priors and full old/new gates, keeping the receiver update policy explicit. Compare its no-addition control and added-target fit in both c arms, including final exact orbit replay and membership retention. Broaden randomized predictive checks before promotion; do not optimize by evaluation error. DS24-0063's proposed receiver explanation remains a different hypothesis: learn a correction from other satellite families first, then test its transfer to the withheld native curve.

Validation covers 13 targeted test cases across the phase/constant helpers, conditional Gaussian update, native position fitting and supported graph selection. Report links, archive readability and ledger/trial row counts were checked; the phase-support and residual figures were inspected. The existing nonstandard constant-prior scaling on a different satellite is preserved; all investigated NORAD 58189 constant columns have the ordinary scale.

[Summary](summary.json), [source hashes](sources.json), [compact numerical evidence](evidence.json.gz). The systematic annotation and inclusion objective remains active.
''')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
