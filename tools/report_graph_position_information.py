"""Publish weak-direction diagnostics and uncertainty-aware recovery trials."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
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
    s = args.study; out = args.output
    out.mkdir(parents=True, exist_ok=False); (out/'figures').mkdir()
    evidence = {}; hashes = {}; executions = []
    def load(p):
        hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        r = read(p); evidence[str(p)] = compact_evidence(r); return r
    def csvout(name, rows):
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows(rows)
    def save(fig, name):
        fig.savefig(out/'figures'/name, dpi=150); plt.close(fig)
    def terminal(p, stage):
        r = load(p); executions.append(dict(stage=stage, source=str(p), **{k:r.get(k) for k in ('status','reason','seconds')}))
        assert r['status'] == 'complete'; return r

    previous = args.previous/'annotation_ledger.csv'
    hashes[str(previous)] = hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger = list(csv.DictReader(previous.open())); byid = {r['track_id']:r for r in ledger}
    queue = s/'systematic-annotation-v1'; attempt = queue/'attempt-26'; batch = []
    load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid = j['track_id']; terminal(attempt/(tid+'-terminal.json'), 'annotation26')
        source = queue/tid/'result.json'; r = load(source); load(source.parent/'protocol.json')
        a = identity_consensus(r['folds'], score_name=r.get('identity_score_name','joint'))
        byid[tid].update(state=a['status'], norad=a['norad'], minimum_margin=a.get('minimum_margin'),
                         annotation_source=str(source), partition_policy='distinct timestamps',
                         geometry_only_early_exit=r.get('geometry_only_early_exit',False),
                         distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        batch.append(dict(scan=j['label'], track_id=tid, status=a['status'], norad=a['norad']))
    audits = []; audit_checks = []
    root = s/'predictive-phase-audit-ds24-v1'
    for j in load(root/'protocol.json')['jobs']:
        tid = j['track_id']; terminal(root/(tid+'-terminal.json'), 'predictive phase audit')
        path = root/(tid+'.json'); r = load(path); a = r['corrected']
        winning = [v for v in r['rows'] if v['nominated']]; audit_checks.extend(winning)
        row = byid[tid]; row.update(phase_prior_state=row['state'], state=a['status'], phase_audit_source=str(path))
        audits.append(dict(scan=j['label'], track_id=tid, original=r['original']['status'], corrected=a['status'],
                           norad=a['norad'], phase_gap_s=max(v['phase_reference_check']['phase_change_s'] for v in winning),
                           maximum_mean_difference_hz=max(v['maximum_target_mean_difference_hz'] or 0 for v in winning),
                           prior_kinds=';'.join(sorted({v['prior_kind'] for v in winning}))))
    csvout('annotation_batch.csv', batch); csvout('predictive_phase_audits.csv', audits)

    cases = [('49154edb','43897235b1c6fc1e8428','75e1d752b6758388'),
             ('e32d57a7','31d98d4cc908a38c734b','e066a22d0a0b28fc')]
    infos = {}; geometry = []; comparisons = []; votes = []; new_votes = {}; originals = {}
    for short, tid, job in cases:
        info = load(s/f'graph-position-pull-{short}-v1'/'result.json')
        load(s/f'graph-position-pull-{short}-v1'/'protocol.json'); infos[short] = info
        folder = s/'graph-inclusion-batch24-v1'/tid
        originals[short] = {role:load(folder/(role+'.json')) for role in ('control','target_0')}
        inv = load(s/'all-large-track-recovery'/job/'inventory.json')
        for arm, v in info['arms'].items():
            m = v['models']; h = m['control']['curvature_at_control']; eig = h['eigenvalues']
            target = next(r for r in m['target_0']['endpoints']['addition_position']['curves'] if r['target'])
            geometry.append(dict(scan=info['job']['label'], arm=arm, shift_km=v['position_shift_km'],
                                 weak_alignment=v['direction_weak_axis_alignment'], weak_curvature=eig[0], strong_curvature=eig[1],
                                 curvature_ratio=eig[1]/eig[0],
                                 control_cost=m['control']['endpoints']['addition_position']['objective']-m['control']['endpoints']['control_position']['objective'],
                                 addition_gain=m['target_0']['endpoints']['control_position']['objective']-m['target_0']['endpoints']['addition_position']['objective'],
                                 target_norad=target['norad'], target_phase_s=target['phase_s'],
                                 target_orbit_modes_active=target['orbit_modes_active'], point_noise_hz=target['point_noise_hz'],
                                 power=target['power'], noise_precision=target['noise_precision'], target_RMS_hz=target['RMS_hz'],
                                 maximum_phase_gap_s=max(vv['maximum_evaluated_phase_gap_s'] for vv in m.values())))
        root = s/f'graph-predictive-recheck-{short}-v1'
        load(root/'protocol.json'); terminal(root/'annotation-terminal.json','predictive identity '+short)
        r = load(root/'annotation'/'result.json'); load(root/'annotation'/'protocol.json')
        vote = identity_consensus(r['folds'], score_name='conditional_target'); new_votes[short] = vote
        for v in vote['votes']: votes.append(dict(scan=r['job']['label'], status=vote['status'], **v))
        byid[tid].update(predictive_recheck_source=str(root/'annotation'/'result.json'),
                         predictive_recheck_state=vote['status'], predictive_recheck_minimum_margin=vote['minimum_margin'])
        roles = [('Original control', originals[short]['control']), ('Calibrating addition', originals[short]['target_0'])]
        if vote['status'] == 'conditionally_supported_identity':
            terminal(root/'inclusion-terminal.json','predictive inclusion '+short)
            load(root/'inclusion'/'protocol.json')
            roles += [(name,load(root/'inclusion'/(file+'.json'))) for name,file in
                      [('Predictive control','control'),('Predictive addition','new_family')]]
            byid[tid].update(predictive_research_inclusion='RF_verified_candidate',predictive_inclusion_source=str(root/'inclusion'))
        else:
            assert not (root/'inclusion').exists()
            executions.append(dict(stage='predictive inclusion '+short,status='not_run_identity_ambiguous',source=str(root),reason='minimum predictive identity margin below 10'))
        for name,r in roles:
            for arm,v in r['arms'].items():
                total = next(x['total_GLRT'] for x in inv['summary'] if x['arm']==arm)
                comparisons.append(dict(scan=inv['job']['label'], method=name, arm=arm, error_km=error(v),
                                        associated_points=len(v['proposed_associated_ids']), associated_percent=100*len(v['proposed_associated_ids'])/total,
                                        added_points=v['added_points'], lost_points=v['lost_points'], paired_gates=r['paired_valid']))
    csvout('position_geometry.csv', geometry); csvout('position_comparison.csv', comparisons); csvout('predictive_identity_votes.csv', votes)

    fig, axs = plt.subplots(2,2,figsize=(12,8),layout='constrained')
    maps, axes = plt.subplots(2,2,figsize=(10,9),layout='constrained')
    for row,(short,_,_) in enumerate(cases):
        for col,(arm,v) in enumerate(infos[short]['arms'].items()):
            ax = axs[row,col]; mx = axes[row,col]; shift = v['position_shift_km']
            for role,label,color in [('control','Original model','#0072b2'),('target_0','With calibrating addition','#d55e00')]:
                m = v['models'][role]; origin = m['endpoints']['control_position']['objective']
                ax.plot([q['fraction']*shift for q in m['line']],[q['objective']-origin for q in m['line']],'.-',color=color,label=label)
            ax.axvline(0,color='gray',ls=':'); ax.axvline(shift,color='gray',ls='--')
            ax.set(title='AUTO-'+short+' / '+arm,xlabel='Distance along control → addition (km)',ylabel='Objective change from control position')
            ax.grid(alpha=.2); ax.legend(fontsize=8)
            m = v['models']['control']; h = np.array(m['curvature_at_control']['hessian_per_km2'])
            start = np.array(m['endpoints']['control_position']['x']); end = np.array(m['endpoints']['addition_position']['x'])-start
            u = np.linspace(-1.6,1.6,140); xx,yy = np.meshgrid(u,u); z = np.stack([xx,yy],axis=-1)
            quad = .5*np.einsum('...i,ij,...j->...',z,h,z)
            cs = mx.contour(xx,yy,quad,levels=[.5,1,2,4],colors='#777777',linewidths=.8); mx.clabel(cs,fontsize=8)
            mx.scatter(0,0,color='black',label='Control'); mx.annotate('',end,(0,0),arrowprops=dict(arrowstyle='->',color='#d55e00',lw=2))
            mx.scatter(*end,color='#d55e00',label='Calibrating addition')
            if short=='49154edb':
                root = s/f'graph-predictive-recheck-{short}-v1'/'inclusion'
                p = read(root/'new_family.json')['arms'][arm]
                xy = np.array(p['endpoint_east_north_km'])-start
                mx.scatter(*xy,marker='s',color='#009e73',label='Predictive addition',s=35)
            mx.set(aspect='equal',title='AUTO-'+short+' / '+arm,xlabel='East from original control (km)',ylabel='North from original control (km)')
            mx.legend(fontsize=7); mx.grid(alpha=.15)
    fig.suptitle('Nuisance-refreshed objective along the observed displacement\nEach model has its own zero at the control position; absolute likelihoods are not compared.')
    maps.suptitle('Local quadratic objective contours at the original control\nThese are objective increments, NOT confidence regions or probability contours.')
    save(fig,'objective_profiles.png'); save(maps,'weak_direction_geometry.png')

    root = s/'graph-family-ablations-49154edb-v1'; ablations = []
    for n in load(root/'protocol.json')['jobs']:
        terminal(root/(str(n)+'-terminal.json'),'family ablation'); load(root/str(n)/'protocol.json')
        c = load(root/str(n)/'control.json'); t = load(root/str(n)/'target_0.json')
        for arm,v in t['arms'].items():
            ablations.append(dict(omitted_norad=n,arm=arm,control_error_km=error(c['arms'][arm]),addition_error_km=error(v),
                                  control_pass=c['paired_valid'],addition_pass=t['paired_valid'],
                                  remaining_old_points_lost=v['remaining_incumbent_points_lost']))
    csvout('family_ablations.csv',ablations)
    fig,axs = plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        rr = [r for r in ablations if r['arm']==arm]; x = np.arange(len(rr))
        ax.bar(x-.18,[r['control_error_km'] for r in rr],.35,label='No target',color='#0072b2')
        ax.bar(x+.18,[r['addition_error_km'] for r in rr],.35,label='Calibrating target',color='#d55e00')
        ax.set(xticks=x,xticklabels=[str(r['omitted_norad']) for r in rr],xlabel='Omitted entire satellite family',ylabel='Position error (km)',title=arm)
        ax.legend(); ax.grid(axis='y',alpha=.2)
    fig.suptitle('AUTO-49154edb: four RF-selected single-family deletions retain the adverse effect')
    save(fig,'satellite_ablations.png')

    root = s/'graph-predictive-recheck-49154edb-v1'/'inclusion'
    replay = load(root/'exact_owner_replay.json'); assert replay['all_verified']
    prior = read(root/'protocol.json')['family_prior']; recovery = []; replays = []
    for r in replay['rows']:
        replays.append(dict(role=r['role'],arm=r['arm'],verified=r['verified'],objective_difference=r['objective_difference'],
                            phase_gap_s=r['phase_reference_check']['phase_change_s'],
                            maximum_incumbent_exact_difference_hz=max(v['maximum_linearization_difference_hz'] for v in r['exact_incumbent_family_replays']),
                            incumbent_owner_changes=len(r['incumbent_ownership_changes']),control_owner_changes=len(r['control_ownership_changes'])))
        if r['target']:
            f = r['target']; d = f['diagnostics'][0]
            recovery.append(dict(arm=r['arm'],phase_map_s=f['phase_map_s'],phase_sigma_s=f['phase_sigma_s'],
                                 RMS_hz=d['profile_RMS_hz'],minimum_elevation_deg=d['minimum_elevation_deg'],
                                 phase_boundary_mass=f['phase_boundary_mass'],receiver_coefficient_change=f['receiver_calibration_change'],
                                 continuous_phase_s=r['continuous_target']['phase_map_s'],
                                 continuous_RMS_hz=r['continuous_target']['diagnostics'][0]['profile_RMS_hz'],**d['noise']))
    csvout('recovery_residuals.csv',recovery); csvout('independent_replay.csv',replays)
    fig,axs = plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        r = next(r for r in replay['rows'] if r['role']=='new_family' and r['arm']==arm)
        d = r['target']['diagnostics'][0]; tt = d['times_s']; y = np.array(d['CFO_hz']); res = np.array(d['raw_residual_hz'])-d['profile_bias_hz']
        old = originals['49154edb']['target_0']['arms'][arm]['targets'][0]
        axs[0,col].scatter(tt,y/1000,s=14,color='black',label='42 original GLRT points')
        axs[0,col].plot(tt,(np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000,color='#009e73',label='Predictive physical fit + bias')
        axs[1,col].plot(tt,res,'.-',color='#009e73',label='Predictive residual, bias removed')
        axs[1,col].plot(old['times_s'],old['residual_hz'],'.-',color='#d55e00',alpha=.7,label='Original calibrating residual')
        axs[0,col].set(title=arm,ylabel='GLRT CFO (kHz)'); axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)')
        axs[1,col].axhline(0,color='black',lw=.6)
        for ax in axs[:,col]: ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.suptitle('AUTO-49154edb / RX2 CH1 / NORAD 58893\nFits use different uncertainty/receiver roles; residual RMS alone cannot rank position accuracy.')
    save(fig,'recovered_curve.png')
    fig,axs = plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,(short,_,_) in zip(axs,cases,strict=True):
        rr = [r for r in votes if r['scan']=='AUTO-'+short]
        ax.bar(range(len(rr)),[r['margin'] for r in rr],color='#009e73' if short=='49154edb' else '#d55e00')
        ax.axhline(10,color='black',ls='--',label='Required margin = 10')
        ax.set(xticks=range(len(rr)),xticklabels=[str(r['seed'])+'\n'+r['arm'] for r in rr],title='AUTO-'+short+' / '+new_votes[short]['status'],ylabel='Held predictive density margin')
        ax.tick_params(axis='x',labelsize=7); ax.set_yscale('log'); ax.legend(fontsize=8); ax.grid(axis='y',alpha=.2)
    save(fig,'predictive_identity_margins.png')
    csvout('annotation_ledger.csv',ledger); csvout('executions.csv',executions)
    summary = dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
                   annotation_batch=dict(Counter(r['status'] for r in batch)),new_predictive_phase_audits=len(audits),
                   phase_audit_status_changes=sum(r['original']!=r['corrected'] for r in audits),
                   cumulative_audited=sum(bool(r.get('phase_audit_source')) for r in ledger),
                   unaudited_DS24_supported=sum('DS24' in r['scopes'] and r['state']=='conditionally_supported_identity' and not r.get('phase_audit_source') for r in ledger),
                   predictive_winning_prior_kinds=dict(Counter(v['prior_kind'] for v in audit_checks)),
                   full_inclusion_replay_verified=replay['all_verified'],production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary); write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f: json.dump(evidence,f,separators=(',',':'))
    position_rows = [r for r in comparisons if r['scan']=='AUTO-49154edb']
    text = f'''# Recovering a curve without over-weighting its positional information

The AUTO-49154edb 42-point RX2 CH1 curve remains conditionally supported as **NORAD 58893** under a fresh causal predictive search. Giving it a physical-orbit and receiver-uncertainty likelihood, while keeping it out of receiver calibration at a fixed position, recovers all 42 points with fitted-c position error **0.589 km**. The earlier calibrating addition gave **1.465 km**; the matched no-addition predictive control gives **0.548 km**. This mitigates an adverse position shift; it does **not** improve the no-addition baseline. Neither model is promoted here.

The contrasting AUTO-e32d57a7 recovery previously improved error substantially, but the predictive test cannot distinguish its preferred NORAD 67634 from 66322 strongly enough. That trial stops before inclusion. A good GPS outcome is not permission to accept a weak satellite identity.

## Experimental scope

These two diagnostic cases were selected because their previously reported position effects contrasted. GPS is used for evaluation and that declared diagnostic selection only, never candidate nomination, optimization or parameter tuning. Both use causal catalogues, a 25 × 25 km regional box centered at **37.906, −122.545**, and center-start position fits. Evaluation site: **37.849061591561885, −122.48574968092912**. Every trial includes matched c=0/fitted-c arms; candidate sets, observations, other priors and budgets match within that ablation.

The fresh annotation holds out random whole scan-wide **12-second blocks with 2-second guards**, with three distinct timestamp-selected target partitions. Simultaneous receiver/channel evidence shares each block assignment. The target never calibrates the receiver. Training uses fixed 150 Hz noise and unit powers, five rounds of 48 position steps, and the existing physical prior. Incumbent identities and graph construction remain fixed conditioning assumptions. Position and learned noise-precision uncertainty are not integrated: this is conditional predictive evidence, not calibrated satellite probability or an independent replication.

## The regressing fit moves in a weakly constrained direction

At frozen satellite identities, we refit nuisance quantities for five raw-checked phase-reference rounds at each of 17 positions along the original control-to-addition line. Finite differences at ±25 m estimate local objective curvature at the control endpoint. This is not a 2D full-pipeline restart grid, and it does not search new associations. Recorded source objectives replay within 1e-5.

{table(geometry,['scan','arm','shift_km','weak_alignment','weak_curvature','strong_curvature','control_cost','addition_gain'])}

In AUTO-49154edb, the ~1 km shift aligns **0.998** with the weakest direction. The original model pays only **1.1–1.2 objective units** for moving there. The curvature ratio is about 11–12, compared with about 1.4–1.5 in the contrasting scan. This supports a position/nuisance tradeoff under this conditional model; it does not establish the global surface, prove the original position correct, or identify a unique physical hardware error. The plotted ellipses are local quadratic objective increments, not calibrated confidence regions.

![Objective profiles](figures/objective_profiles.png)

![Weak direction](figures/weak_direction_geometry.png)

NORAD 58893 has no other active calibration evidence. In the calibrating addition its phase is ~1.9 s with a 15 s prior width, but the singleton support policy supplies no physical orbit modes. The curve's nominal point noise is ~62 Hz, power 0.2, and fitted precision ~2.0. Low pointwise RMS therefore coexists with a strong positional pull. Receiver frequency means change by up to ~62 Hz and rates by ~1.35 Hz/s across old curves; these are model tradeoffs, not independently measured receiver drift.

## Four single-family deletions do not explain away the regression

We rank incumbent families by the absolute change in grouped weighted residual energy, summed across c arms, and delete the top four one at a time. No GPS error enters this ranking. Both curved and predictive observations of the selected family are removed from control and addition. Other observations, priors and five × 48-step budgets remain matched. Weighted residual energy is a diagnostic contribution, not the complete ELBO decomposition.

{table(ablations,['omitted_norad','arm','control_error_km','addition_error_km','control_pass','addition_pass','remaining_old_points_lost'])}

![Satellite ablations](figures/satellite_ablations.png)

All four deletions retain the adverse effect in both arms; no remaining incumbent points are lost. Thus no one of these four families explains it. This does not rule out other families, multiple simultaneous mistakes, or a shared model bias. These are diagnostic fits, not accepted satellite deletions.

## Uncertainty-aware predictive recovery

The target's likelihood integrates shared receiver-coefficient uncertainty, conditioned once on existing predictive evidence, and three physical orbital modes. It integrates satellite phase on the existing ±15 s box rather than treating one fitted phase as exact. At fixed position it does not update receiver calibration; it still affects position, which can indirectly change the incumbent receiver fit. The family is eligible because its graph label has no active calibration or predictive observations.

The causal prior uses mean phase {prior['phase_prior_mean_s']:.3f} s and width {prior['phase_prior_sigma_s']:.3f} s. Latest causal TLE age is {prior['history'][0]['age_s']/3600:.2f} hours; the previous causal epoch gap is {prior['history'][0]['previous_epoch_gap_s']/3600:.2f} hours. Historical disagreement gives radial/cross scales about **1.500 / 0.080 km**, mean-motion sigma **0.00505 rev/day**, inclination **0.000673°**, and RAAN **0.000841°**. The existing phase box contains **68.27%** of the Gaussian prior mass; this truncation is explicitly retained, not presented as full-prior integration. Target phase boundary mass is zero numerically. Existing predictive noise also includes a 300 Hz track-bias prior and twice nominal independent variance.

{table(position_rows,['method','arm','error_km','associated_points','associated_percent','added_points','lost_points','paired_gates'])}

The calibrating addition associates **73** extra points, including **31 incidental points elsewhere**; the predictive addition recovers only the **42 target points**. These are not identical associated sets across methods. Each method has its own refitted no-addition control. Full-data point noise/weights are retained within each method; fresh annotation has its separate fixed-noise validation policy. Absolute objective values and RMS must not be directly ranked across these changed likelihoods.

{table(recovery,['arm','phase_map_s','RMS_hz','continuous_phase_s','continuous_RMS_hz','minimum_elevation_deg','noise_screen_pass'])}

![Recovered CFO and residual](figures/recovered_curve.png)

The target passes mean, slope, curvature, discontinuity and lag-one residual screens. A post-fit 0.1/0.05/0.025-second phase-grid comparison at the endpoint and ±25 m neighbors passes the existing local agreement guard in both arms. A separate replay reproduces objectives and memberships, preserves all incumbent and control satellite owners, and passes gates with each incumbent family's exact orbit substituted one at a time. The largest incumbent tangent/exact difference is below **0.002 Hz**. Continuously refining the target phase preserves its gates and ~18 Hz RMS. This replay does not refit position or change acceptance. The uncertainty-aware recovery is an RF-qualified research candidate, not a production deployment.

Several things change together relative to direct calibration: receiver role, physical orbit uncertainty, target noise/bias treatment and marginalization. This comparison does **not** isolate which one removes the harmful position pull. A matched factorial ablation is needed before attributing it specifically to TLE uncertainty.

## A useful negative result from the contrasting scan

{table(votes,['scan','seed','arm','norad','runner_up','margin','adequate'])}

![Predictive identity margins](figures/predictive_identity_margins.png)

AUTO-e32d57a7 prefers 67634 in all six votes, but its margins are **1.31–5.96**, below the pre-existing threshold **10**. All six predictions pass the adequacy screen. This is insufficient discrimination from 66322, not failure to fit a curve. No predictive inclusion is run. The old calibrating addition's favorable position result (~2.48 to ~1.18 km) remains historical evidence under a different conditional model, not a reason to relax the threshold. The ledger preserves both states and sources without overwriting retained policy.

## Inventory and historical phase checks

All 32 jobs in annotation attempt 26 complete: **{summary['annotations_completed']} / {summary['inventory_total']}** original inventory entries now have annotations. This batch yields `{summary['annotation_batch']}`. An annotation can be ambiguous, mismatched or unsupported; this count is not accepted GLRT coverage. Native overlapping branches remain separate.

The remaining **19 supported predictive-only DS24 annotations** replay their original training objective and every original candidate score. All 19 retain their identity-support status after replacing clipped phase-change metadata with the raw phase/reference gap. There are now **{summary['cumulative_audited']}** phase-audited entries and **{summary['unaudited_DS24_supported']}** currently supported DS24 entries without an audit. For existing shared-posterior predictions, the audit replaces the mean with exact orbit geometry but freezes covariance; it does not claim a full exact-posterior reranking. Exact phase-mixture cases already evaluate phase geometry directly. No historical fit is silently replaced.

## Next discriminating experiments

1. Freeze these observations, candidates, budgets and priors; ablate target-to-receiver feedback, physical orbit covariance and track-bias/noise treatment separately. Evaluate both c arms and independently held families. Determine which change suppresses spurious weak-direction information.
2. Apply the frozen predictive-identity and inclusion rules to the other two previously RF-verified recoveries, including all failures. Do not switch methods per scan according to GPS improvement.
3. Resolve ambiguous identities with independent curved evidence across receivers/channels when available. Keep receiver drift corrections shared and supported by other satellites; do not add a free per-track slope merely to pass residual gates.
4. Continue the remaining inventory with bounded batches. Retain distinctions between detection, identity support, valid physical fit and useful position information. High association percentage alone is not a promotion criterion.

No new ALGO version, dataset-wide localization gain or production-policy change is claimed. The evidence now shows why a plausible identity and clean residual are not sufficient: a curve can still inject unjustifiably strong information along a weak position direction.

## Reproduction and artifacts

Source tools: `diagnose_graph_position_pull.py`, `ablate_graph_position_families.py`, `annotate_predictive_only.py`, `include_new_predictive_family.py`, `audit_predictive_family_inclusion.py`, and `audit_predictive_annotation_phase.py`. This report is generated by `report_graph_position_information.py`. Protocols retain exact inputs, masks, seeds and budgets. The predictive inclusion now checks raw phase convergence rather than clipped-reference stagnation.

**20 targeted tests pass**, covering phase-reference/domain checks, randomized training masks, family deletion, finite-difference curvature, predictive covariance/phase integration, resolution guards and owner preservation. Immutable full numerical evidence stays under `/srv/bulk/leo/research/ch78-qualified-cohort-20261029`; this publication contains a compact hashed archive, including unsuccessful annotations and skipped inclusion.

[Summary](summary.json), [cumulative ledger](annotation_ledger.csv), [new annotation statuses](annotation_batch.csv), [phase audits](predictive_phase_audits.csv), [position geometry](position_geometry.csv), [position and coverage](position_comparison.csv), [family ablations](family_ablations.csv), [identity votes](predictive_identity_votes.csv), [residuals](recovery_residuals.csv), [independent replay](independent_replay.csv), [executions](executions.csv), [source hashes](sources.json), [compact evidence](evidence.json.gz), and [previous iteration](../2026_10_30_residual_witness_recovery/README.md).
'''
    (out/'README.md').write_text(text)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('study','previous','output'): p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
