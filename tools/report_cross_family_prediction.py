"""Publish cross-family validation, evidence-weight factors and inventory progress."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus

POLICIES=('original','fixed_noise_only','unit_weights_only','annotation_fixed')
SUFFIXES=('constrained','fixed_noise_only','unit_weights_only','fixed-noise')


def held_metrics(before,after,select):
    """Point-weighted RMS on identical held observations, without refitting."""
    a=[r for r in before if select(r)];b=[r for r in after if select(r)]
    if len(a)!=len(b):raise ValueError('held row sets differ')
    old=[];new=[];ids=[]
    for x,y in zip(a,b,strict=True):
        if x['component']!=y['component'] or x['observation_ids']!=y['observation_ids']:raise ValueError('held observation sets differ')
        old.extend(x['residual_hz']);new.extend(y['residual_hz']);ids.extend(x['observation_ids'])
    if len(ids)!=len(set(ids)):raise ValueError('held observations counted twice')
    if not ids:return dict(points=0,control_RMS_hz=None,target_RMS_hz=None,RMS_gain_hz=None)
    rms=lambda v:float(np.sqrt(np.mean(np.asarray(v)**2)))
    return dict(points=len(ids),control_RMS_hz=rms(old),target_RMS_hz=rms(new),RMS_gain_hz=rms(old)-rms(new))


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=args.refresh);(out/'figures').mkdir(exist_ok=True)
    evidence={};hashes={}
    def load(path):
        path=Path(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    audit=load(s/'native-evidence-weight-factorial-audit-v1.json')
    lookup={(Path(r['run']).name,r['role'],r['arm']):r for r in audit['rows']}
    factors=[];trials=[]
    for scan in ('0093','0063'):
        for policy,suffix in zip(POLICIES,SUFFIXES,strict=True):
            name=f'native-{scan}-explicit-phase-{suffix}-v1';root=s/name
            load(root/'protocol.json');control=load(root/'control.json');target=load(root/'target.json')
            for arm in ('c0','fitted_c'):
                a,b=control['arms'][arm],target['arms'][arm];aa,bb=[lookup[name,role,arm] for role in ('control','target')]
                passed=control['paired_valid'] and target['paired_valid'] and aa['all_pass'] and bb['all_pass']
                passed=passed and not any(q['incumbent_ownership_changes'] or q['control_ownership_changes'] for q in (aa,bb))
                factors.append(dict(scan='DS24-'+scan,policy=policy,arm=arm,RF_qualified=passed,
                    control_error_km=error(a),target_error_km=error(b),position_gain_km=error(a)-error(b),
                    added_points=b['added_points'],lost_points=b['lost_points'],
                    control_native_RMS_hz=aa['native']['RMS_hz'],target_native_RMS_hz=bb['native']['RMS_hz']))
                for role,v,q in [('control',a,aa),('target',b,bb)]:
                    trials.append(dict(scan='DS24-'+scan,policy=policy,arm=arm,role=role,
                        objective=v['negative_twice_elbo'],exact_gate_pass=q['all_pass'],minimum_slack=q['minimum_slack'],
                        objective_replay_difference=q['objective_replay_difference'],
                        old_owner_changes=len(q['incumbent_ownership_changes']),control_owner_changes=len(q['control_ownership_changes'])))
    csvout('factorial_positions.csv',factors);csvout('factorial_audit.csv',trials)
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for row,scan in enumerate(('DS24-0093','DS24-0063')):
        for col,arm in enumerate(('c0','fitted_c')):
            ax=axs[row,col];items=[r for r in factors if r['scan']==scan and r['arm']==arm];xx=np.arange(4)
            ax.bar(xx-.17,[r['control_error_km'] for r in items],.33,color='#999999',label='No-addition control')
            ax.bar(xx+.17,[r['target_error_km'] for r in items],.33,color='#0072b2',label='Add native curve')
            ax.axhline(.5,c='#009e73',ls='--',lw=1,label='500 m goal')
            ax.set(title=scan+' / '+arm,ylabel='Evaluation position error (km)',xticks=xx,
                xticklabels=['Original','150 Hz only','Unit powers only','Both fixed']);ax.tick_params(axis='x',labelsize=8);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Separate measurement-noise scale from curve confidence powers\nExploratory two-case ablation; every paired fit passes RF checks')
    fig.savefig(out/'figures/factorial_positions.png',dpi=145);plt.close(fig)

    root=s/'native-position-cross-family-validation-v1';protocol=load(root/'protocol.json');executions=[];folds=[];strata=[]
    replay=load(s/'native-position-cross-family-replay-v1.json')
    for job in protocol['jobs']:
        term=load(root/(job['name']+'-terminal.json'));executions.append(dict(scan=job['scan'],seed=job['seed'],status=term['status']))
        load(root/job['name']/'protocol.json')
        if term['status']!='complete':continue
        r=load(root/job['name']/'result.json')
        for arm,v in r['arms'].items():
            a,b=v['variants']['control'],v['variants']['target'];old,new=a['held_predictions'],b['held_predictions']
            primary=held_metrics(old,new,lambda q:q['kind']=='curved' and not q['same_family'] and q['train_points']>=4)
            native=held_metrics(old,new,lambda q:q['kind']=='native')
            folds.append(dict(scan=job['scan'],seed=job['seed'],arm=arm,control_qualified=a['training_qualified'],target_qualified=b['training_qualified'],
                other_family_points=primary['points'],other_family_control_RMS_hz=primary['control_RMS_hz'],
                other_family_target_RMS_hz=primary['target_RMS_hz'],other_family_RMS_gain_hz=primary['RMS_gain_hz'],
                native_points=native['points'],native_control_RMS_hz=native['control_RMS_hz'],native_target_RMS_hz=native['target_RMS_hz'],native_RMS_gain_hz=native['RMS_gain_hz'],
                position_shift_km=float(np.linalg.norm(np.array(a['endpoint_east_north_km'])-b['endpoint_east_north_km']))))
            eligible=lambda q:q['kind']=='curved' and q['train_points']>=4
            for field,get in [('family',lambda q:str(q['norad'])),('receiver',lambda q:'RX'+str(q['receiver'])),
                              ('channel_group',lambda q:'CH1–4' if q['channel']<=4 else 'CH5–8')]:
                for group in sorted({get(q) for q in old if eligible(q)}):
                    metrics=held_metrics(old,new,lambda q:eligible(q) and get(q)==group)
                    strata.append(dict(scan=job['scan'],seed=job['seed'],arm=arm,grouping=field,group=group,
                        paired_training_qualified=a['training_qualified'] and b['training_qualified'],**metrics))
    csvout('validation_executions.csv',executions);csvout('held_predictions.csv',folds);csvout('held_residual_strata.csv',strata)
    fig,axs=plt.subplots(1,2,figsize=(13,6),layout='constrained');labels=[f"{r['scan']} / {r['seed']} / {r['arm']}" for r in folds]
    for ax,key,title in zip(axs,('other_family_RMS_gain_hz','native_RMS_gain_hz'),('Other-family held curved evidence','Added curve held evidence'),strict=True):
        vals=[r[key] for r in folds];yy=np.arange(len(folds));colors=['#0072b2' if r['control_qualified'] and r['target_qualified'] else '#d55e00' for r in folds]
        ax.barh(yy,vals,color=colors);ax.axvline(0,c='black',lw=.6);ax.set(yticks=yy,yticklabels=labels,title=title,xlabel='Control RMS − target RMS (Hz); positive is better')
        ax.tick_params(axis='y',labelsize=7);ax.grid(axis='x',alpha=.2)
    fig.suptitle('Training-only fits: the new curve helps its own predictions more than other families\nOrange: both fitted-c endpoints fail training gates; one additional fold timed out')
    fig.savefig(out/'figures/held_predictions.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,7),layout='constrained')
    for ax,scan in zip(axs,('DS24-0093','DS24-0063'),strict=True):
        rr=[r for r in strata if r['scan']==scan];cols=sorted({(r['seed'],r['arm']) for r in rr});groups=sorted({(r['grouping'],r['group']) for r in rr});matrix=np.full((len(groups),len(cols)),np.nan)
        for r in rr:matrix[groups.index((r['grouping'],r['group'])),cols.index((r['seed'],r['arm']))]=r['RMS_gain_hz']
        vmax=max(1.,np.nanmax(abs(matrix)));im=ax.imshow(matrix,cmap='RdBu',vmin=-vmax,vmax=vmax,aspect='auto')
        ax.set(title=scan,xticks=np.arange(len(cols)),xticklabels=[str(a)+' / '+b for a,b in cols],yticks=np.arange(len(groups)),yticklabels=[a+': '+b for a,b in groups]);ax.tick_params(axis='x',rotation=70,labelsize=7);ax.tick_params(axis='y',labelsize=7);fig.colorbar(im,ax=ax,label='Held RMS gain (Hz)')
    fig.suptitle('Where held residual changes occur: all original curved evidence\nFamily, receiver and channel-group rows overlap; these are not independent tests')
    fig.savefig(out/'figures/held_residual_strata.png',dpi=140);plt.close(fig)

    weights=load(s/'native-position-evidence-weights-v2.json');weight_rows=[];downweights=[]
    for r in weights['rows']:
        weight_rows.append(dict(scan=r['scan'],arm=r['arm'],native_sigma_median_hz=r['native_base_sigma_hz']['median'],
            fixed150_precision_reduction=r['native_weight_reduction_with_fixed150'],old_effective_sigma_median_hz=r['curved_effective_sigma_hz']['median']))
        downweights.extend(dict(scan=r['scan'],arm=r['arm'],**v) for v in r['downweighted_curves'])
    csvout('noise_scales.csv',weight_rows);csvout('downweighted_curves.csv',downweights)
    fig,axs=plt.subplots(1,2,figsize=(11,5),layout='constrained')
    for ax,scan in zip(axs,('DS24-0093','DS24-0063'),strict=True):
        rr=[r for r in downweights if r['scan']==scan and r['arm']=='c0'];groups=sorted({r['norad'] for r in rr});xx=np.arange(len(groups))
        ax.bar(xx,[sum(r['points'] for r in rr if r['norad']==g) for g in groups],color='#aaaaaa',label='Points in downweighted curves')
        ax.bar(xx,[sum(r['points']*r['power'] for r in rr if r['norad']==g) for g in groups],color='#0072b2',label='Sum(points × confidence power)')
        ax.set(title=scan,xticks=xx,xticklabels=groups,ylabel='Point count / weighted count');ax.tick_params(axis='x',rotation=60,labelsize=8);ax.legend(fontsize=7);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Original curve-confidence heuristic suppresses some satellite evidence\nCounts illustrate powers only; noise precision and correlation also affect information')
    fig.savefig(out/'figures/curve_powers.png',dpi=145);plt.close(fig)

    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};queue=s/'systematic-annotation-v1';attempt=queue/'attempt-22';batch=[]
    load(attempt/'protocol.json')
    for q in load(attempt/'selected.json'):
        tid=q['track_id'];term=load(attempt/(tid+'-terminal.json'));r=dict(scan=q['label'],track_id=tid,status='execution_'+term['status'],norad=None)
        if term['status']=='complete':
            path=queue/tid/'result.json';a=load(path);vote=identity_consensus(a['folds'],score_name=a.get('identity_score_name','joint'))
            r.update(status=vote['status'],norad=vote['norad']);byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=a.get('geometry_only_early_exit',False),distinct_schedule_ready=not a.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=r['status']
        batch.append(r)
    if len(ledger)!=1630 or len(byid)!=1630:raise ValueError('inventory changed')
    csvout('annotation_ledger.csv',ledger);csvout('annotation_batch.csv',batch)

    groot=s/'graph-inclusion-batch21-v1';gp=load(groot/'protocol.json');graph=[];gallery=[]
    owners=load(groot/'qualified_owner_audit.json');oa={(r['track_id'],r['role'],r['arm']):r for r in owners['rows']}
    for job in gp['jobs']:
        tid=job['track_id'];term=load(groot/(tid+'-terminal.json'))
        if term['status']!='complete':raise ValueError('incomplete graph inclusion')
        load(groot/tid/'protocol.json');q=load(groot/tid/'target_0.json');control=load(groot/tid/'control.json');fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(q['arms'].items()):
            t=v['targets'][0];c=control['arms'][arm];o=oa.get((tid,'target_0',arm));old=oa.get((tid,'control',arm))
            verified=bool(o and old and all(r['all_pass'] and not r['incumbent_ownership_changes'] and not r['control_ownership_changes'] for r in (o,old)))
            graph.append(dict(scan=job['label'],track_id=tid,arm=arm,paired_RF_pass=q['paired_valid'],control_pass=control['paired_valid'],exact_and_owner_verified=verified,
                target_curve_points=len(t['times_s']),added_vs_incumbent=v['added_points'],lost_vs_incumbent=v['lost_points'],
                net_added_vs_control=len(v['proposed_associated_ids'])-len(c['proposed_associated_ids']),before_error_km=error(c),after_error_km=error(v)))
            axs[0,col].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=10);axs[0,col].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Conditional residual (Hz)')
        fig.suptitle(f"{job['label']} / NORAD {t['norad']} / {tid}\nPaired RF pass: {q['paired_valid']} (research candidate)")
        f=f'figures/{tid}_graph.png';fig.savefig(out/f,dpi=120);plt.close(fig);gallery.append(f"## {job['label']} / {tid}\n\n![Graph trial]({f})")
    csvout('graph_trials.csv',graph);(out/'graph_gallery.md').write_text('# Every graph inclusion trial\n\n'+'\n\n'.join(gallery)+'\n')
    ga=load(groot/'gate_audit.json');failures=[];categories={}
    for r in ga['results']:
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in r[key]:
                if not v['compatible']:
                    failures.append(dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],role=role,target=v.get('target',False),component=v['component'],failures=';'.join(v['failures'])))
                    categories.setdefault(r['track_id'],set()).update(v['failures'])
    csvout('graph_gate_failures.csv',failures)
    counts=Counter('Owner support only' if x=={'multiple_orbital_owners_required'} else 'Residual/geometry failures' for x in categories.values())
    counts['Passing recovery']=sum(r['paired_RF_pass'] and r['exact_and_owner_verified'] for r in graph if r['arm']=='c0')
    fig,ax=plt.subplots(figsize=(8,4),layout='constrained');ax.bar(list(counts),list(counts.values()),color=['#d55e00','#999999','#0072b2']);ax.set(ylabel='Number of graph trials',title='17 supported identities tested in the full original model');ax.grid(axis='y',alpha=.2)
    fig.savefig(out/'figures/graph_outcomes.png',dpi=145);plt.close(fig)
    summary=dict(graph_assessed=sum(bool(r['annotation_source']) for r in ledger),graph_total=len(ledger),annotation_batch=dict(Counter(r['status'] for r in batch)),
        graph_inclusion_outcomes=dict(counts),validation_executions=dict(Counter(r['status'] for r in executions)),
        complete_fold_arm_comparisons=len(folds),both_training_qualified=sum(r['control_qualified'] and r['target_qualified'] for r in folds),
        exact_full_data_fits=len(audit['rows']),replayed_training_endpoints=len(replay['rows']),production_changed=False,retained_cohort_policy_changed=False)
    for name in ('report_cross_family_prediction.py','validate_explicit_phase_position.py','run_explicit_phase_validation.py',
                 'audit_explicit_phase_validation.py','audit_graph_inclusion_owners.py','audit_native_evidence_weights.py',
                 'grouped_predictive_scan.py','explicit_shared_phase.py','run_explicit_phase_inclusion.py','audit_explicit_phase_endpoint.py'):
        path=Path(__file__).with_name(name);hashes[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name,obj in [('summary.json',summary),('sources.json',hashes)]:
        (out/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f)
    # Full owners, IDs and holdout assignments remain available independently
    # of the compact report evidence; none overwrite accepted policy receipts.
    full={k:v for k,v in evidence.items() if ('explicit-phase-' in k and k.endswith(('/control.json','/target.json'))) or 'cross-family' in k or k.endswith('qualified_owner_audit.json')}
    with gzip.open(out/'candidate_and_validation_receipts.json.gz','wt') as f:json.dump(full,f,separators=(',',':'))
    approved=[r for r in graph if r['paired_RF_pass']]
    (out/'README.md').write_text(f'''# Cross-family prediction, evidence weighting, and large-curve recovery

We can now retain some previously rejected curves without relaxing their gates or changing old satellite ownership. That is not yet a reliable localization improvement rule. The two native curves still separate those questions: **DS24-0093 improves, DS24-0063 worsens**, across all four evidence-weight policies tested. New training-only validation finds little corroborating improvement in held observations from other satellite families.

One of **17** newly tested original graph recoveries passes: AUTO-f7f4de11's 47-point RX1 CH2 curve, **NORAD 68607**, from 247.589 to 298.411 seconds. Its refit adds **63 points total**, comprising the target's 47 and 16 additional points qualified by the refit. It preserves every old satellite owner and improves both matched position errors modestly. This remains a research candidate; neither production nor retained cohort totals change.

This continues the [explicit shared-phase inclusion report](../2026_10_30_explicit_phase_inclusion/README.md). All inference uses causal TLEs, and GPS is used only to calculate reported error. The c=0 and fitted-c arms share observations, candidate identities, prior policies and budgets. No new RF data were collected.

## 1. What the held-block test says

We reused three recorded randomized **12-second block** partitions per scan, with **2-second guards**, across every receiver and channel simultaneously. This is not random individual-point withholding. All position, phase, receiver and predictive-constant fitting uses training observations. The frozen graph, satellite identities, earlier guard decisions and prior choices remain conditioning assumptions: this is **conditional model validation**, not an independent end-to-end identity test.

Each fold first fits original curved training evidence from the center of the 25 × 25 km region (37.906, −122.545), then starts the matched control and native-addition models at that same RF-only endpoint. Each uses 81 phase-start candidates over ±0.2 s and five phase-refresh rounds of 48 optimizer iterations. The shared satellite phase is an explicit optimizer coordinate; other satellite and receiver parameters retain the existing conditional treatment.

Training uses fixed 150 Hz measurement noise and unit curve powers, avoiding reuse of full-data RF confidence estimates. Predictive measurements use twice that variance and the original 300 Hz constant prior. Original predictive entries receive appended training-only views; original geometry and observation IDs are preserved. Curved calibration groups with fewer than four training points are excluded and recorded. At least eight target training points are required. Held predictions use exact orbit means and constants learned only from training observations; no held constant is refitted.

**Five of six fold jobs completed; DS24-0093 seed 94721 timed out at 360 seconds.** It is an unresolved execution, not a successful validation or scientific rejection. Nine of the ten complete arm comparisons pass training gates in both variants. Both fitted-c endpoints for DS24-0063 seed 94721 fail; they are shown in orange and are not acceptance evidence.

{table(executions,['scan','seed','status'])}

{table(folds,['scan','seed','arm','control_qualified','target_qualified','other_family_points','other_family_RMS_gain_hz','native_RMS_gain_hz','position_shift_km'])}

Positive gain means lower held RMS after adding the native curve. The primary witness consists of **original curved points from other satellite families**, with at least four training points in their curve. The gain is generally tiny (the largest is about 0.42 Hz); native held predictions change much more. This does not establish an independent position benefit. It also does not prove the curve is false: position and phase may compensate, and the fixed-noise validation policy gives the native evidence less weight than the original fit.

![Held residual improvements](figures/held_predictions.png)

The partitions overlap and are not independent replicates. These are plug-in mean residuals, not calibrated predictive probabilities: position, phase and noise uncertainty are not integrated. A few training-only endpoints reach a region boundary, so these folds also expose weak or unstable geometry. There is no claim of global convergence or precise location from this validation.

All **20 completed control/target arm endpoints** were rebuilt from saved phase-round histories without rerunning optimization. Objectives and held residuals reproduce exactly. Perturbing every excluded curved value by **1,000,000 Hz** leaves the final fitted objective unchanged in every replay, conditional on the fixed graph and prior choices. This narrowly checks excluded-value dependence; it does not undo full-data identity or graph selection. Future receipts now save the final phase reference directly.

The following plot breaks down held original curved residuals by satellite, receiver and channel group. These rows overlap and cannot be combined as independent evidence. It includes the same-family curves as a secondary diagnostic. Channel groups here mean CH1–4 versus CH5–8, not an assumed physical band mapping.

![Family and receiver residual comparison](figures/held_residual_strata.png)

[Held metrics](held_predictions.csv), [all strata](held_residual_strata.csv), [execution receipts](validation_executions.csv), [full validation and candidate receipts](candidate_and_validation_receipts.json.gz).

## 2. Separating noise scale from confidence weighting

The validation changes both noise and curve powers relative to the full-data prototype. A controlled 2 × 2 ablation separates those effects. The original noise model and original curve powers form one corner; fixed 150 Hz noise, unit curve powers, and both together form the others. Within each policy, the no-addition control and native-addition fit use the same data, priors, candidate identities, starts and search budget, apart from the explicitly added target. Existing receiver/orbit/constant prior widths and gates are unchanged. All **32** full-data endpoints pass exact selected-family orbit gate replay and preserve old ownership.

{table(factors,['scan','policy','arm','RF_qualified','control_error_km','target_error_km','added_points','control_native_RMS_hz','target_native_RMS_hz'])}

![Factorial position results](figures/factorial_positions.png)

For DS24-0093, unit curve powers with the original noise model yield **0.484 → 0.393 km (c=0)** and **0.556 → 0.432 km (fitted c)**. This crosses the 500 m goal in this one case, but is an exploratory result, not a promoted algorithm. Fixed noise alone makes its control worse; the two changes are not interchangeable. DS24-0063 still worsens when its 44-point curve is added under every policy. A better target frequency fit therefore cannot substitute for external geometric confirmation.

The target noise scales explain why the fixed-noise validation gives weaker feedback: DS24-0093's original median native base sigma is **57.66 Hz**, versus **101.06 Hz** for DS24-0063. Replacing these with 150 Hz reduces their median predictive precision by **6.77×** and **2.20×**, respectively. These are precision ratios, not changes in measured SNR or sample rate.

{table(weight_rows,['scan','arm','native_sigma_median_hz','fixed150_precision_reduction','old_effective_sigma_median_hz'])}

![Downweighted curves](figures/curve_powers.png)

The existing `cross_rx_support` rule assigns power 1 when a family has support on two receivers, 0.6 when it has at least two receiver/channel owners and the curve's competitor confidence is ≥0.95, and 0.2 otherwise. DS24-0093's active old curves of the recovered family 58189 have power 0.6. **Mixed powers within a family do not by themselves demonstrate a bug**, because the rule also uses per-curve confidence. Family-replacement experiments intentionally preserve the original powers for matched comparisons; the downstream loader carries them forward. Whether those frozen weights remain calibrated after recovery is a testable concern, not an established offset or wavelength error.

Source: [weight rule](../../tools/evaluate_ds23_family_weighting.py), [initial application](../../tools/algo02_scan.py), [family replacement preservation](../../tools/probe_ds23_family_cavity_position.py), [downstream replay](../../tools/benchmark_graph_covariance.py). [Noise scale CSV](noise_scales.csv), [downweighted curve CSV](downweighted_curves.csv), [factorial positions](factorial_positions.csv), [all endpoint audits](factorial_audit.csv).

## 3. A new original-model graph recovery, and all failures

{table(approved,['scan','arm','target_curve_points','added_vs_incumbent','lost_vs_incumbent','exact_and_owner_verified','before_error_km','after_error_km'])}

AUTO-f7f4de11 goes from **1,291/2,321 (55.62%) to 1,354/2,321 (58.34%)** associated points. The old nominal identity of the target was already 68607; this is recovery of rejected evidence, not a satellite replacement. Three randomized block nominations agree in both c arms, with minimum joint-score margin 74.92 over the runner-up. Identity support is conditional on the graph and candidate search. A full original-model refit from the regional center then passes all gates, including an exact selected-family orbit replay and preservation of every incumbent and matched-control satellite owner. No new nuisance parameter or gate relaxation is used for this graph case.

![Passing graph recovery](figures/93011b4437c32b34b691_graph.png)

The other **16** trials fail: **12** have residual/geometry failures, and **4** fail only the multiple-orbital-owner support requirement. The latter are not interchangeable with proven wrong identities; the model requires independent owners before trusting physical orbital corrections. Failures on an old curve count too. Provisional point gains in failed fits are not accepted associations. The complete gate audit covers rejected fits; a separate ownership/exact-orbit audit covers the passing control and target.

![Graph outcomes](figures/graph_outcomes.png)

[Every trial's CFO and residual plot](graph_gallery.md), [all graph results](graph_trials.csv), [every failing component and gate](graph_gate_failures.csv).

## 4. Inventory coverage and next decision

The bounded annotation batch finishes **29** of 32 jobs, with three 600-second timeouts. The original 1,630-entry graph inventory now has **{summary['graph_assessed']} completed annotations**. This inventory spans DS24 and the day's automatic analyses; it must not be described as 1,630 DS24-only tracks. Annotation completion is not accepted association. The three new timeouts and all earlier unresolved entries remain visible in the ledger.

Batch classifications: `{summary['annotation_batch']}`. [Full ledger](annotation_ledger.csv), [this batch](annotation_batch.csv).

The next bounded experiment should estimate confidence/noise using training data only, then compare original, refreshed-support and unit-power policies using the same held cross-family observations. Keep DS24-0063 as a counterexample, and require a GPS-blind criterion that distinguishes it from beneficial additions. For owner-only failures, test jointly supported family evidence before loosening orbital priors. For residual failures, compare shared receiver structure against shared satellite structure using independently supported curves. Do not select whichever policy gives the best GPS error on each scan.

This iteration adds evidence for three distinct bottlenecks: optimization over a shared satellite phase can recover feasible curves; confidence powers materially alter geometry; and a curve can satisfy all residual gates while moving position in the wrong direction. It does not establish sample rate, receiver separation, or a channel-frequency offset as the cause. No new ALGO promotion, production deployment, accepted-cohort change, or full-DS24 accuracy claim is made.

## Reproduction and validation

Run `tools/run_explicit_phase_validation.py` on the two diagnostic directories recorded in the source receipts, then `tools/audit_explicit_phase_validation.py`. The latter reconstructs final references from saved histories and evaluates the excluded-value perturbation check without optimization. Full-data runs use `tools/run_explicit_phase_inclusion.py --constrained --noise-policy` with each of `original`, `fixed_noise_only`, `unit_weights_only`, and `annotation_fixed`; the complete arguments, source IDs, partitions and file hashes are archived. Replay all eight run directories with `tools/audit_explicit_phase_endpoint.py`.

The original-model graph batch uses `tools/run_supported_graph_inclusions.py` on annotation attempt 21; the new annotation ledger consumes attempt 22. Audit rejected graphs with `tools/audit_receiver_ramp_gates.py --graph` and the passing graph with `tools/audit_graph_inclusion_owners.py`. Generate this report with `tools/report_cross_family_prediction.py --study <study-root> --previous reports/2026_10_30_explicit_phase_inclusion --output reports/2026_10_30_cross_family_prediction`.

**13 targeted tests pass**, covering training-view exclusion and immutability, evidence-policy factor isolation, explicit phase normalization and conditional coefficients, fixed-coordinate prediction, and identical held-point accounting. Scientific endpoint audits cover 32 full-data native fits, 20 completed training endpoints, and four passing graph endpoints. Timeouts and failed fits remain reported rather than being silently dropped.

[Summary](summary.json), [source hashes](sources.json), [compact evidence](evidence.json.gz), [full candidate/validation receipts](candidate_and_validation_receipts.json.gz).
''')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('study','previous','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--refresh',action='store_true');run(p.parse_args())
