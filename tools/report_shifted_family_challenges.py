"""Report shared-family checks, complete-target IQ replay and matched refits."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_predictive_role_reassessment import complete_replay_slacks
from report_predictive_covariance_transfer import compact_replays
from report_systematic_annotation import compact_evidence


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();v=read(p);evidence[str(p)]=compact_replays(compact_evidence(v));return v
    def verify(records):
        for p,digest in records.items():
            if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('source changed: '+p)
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    root=s/'shifted-rejected-family-challenges-v2';pr=load(root/'protocol.json');jobs=load(root/'execution.json')
    for r in jobs:
        if r['status']!='complete':raise ValueError('family test incomplete')
    for name in ('shifted-rejected-family-challenges-v1','shifted-rejected-native-audit-v1','shifted-rejected-iq-refinement-v1','shifted-rejected-iq-refinement-v2','shifted-rejected-iq-refinement-v3','shifted-rejected-shared-refresh-v1','shifted-rejected-conditional-refresh-v1','shifted-rejected-conditional-feasible-v1'):
        load(s/name/'execution.json')
        if (s/name/'protocol.json').exists():load(s/name/'protocol.json')
    family=[];members=[];grid=[];native_rows=[];measurements=[];iq_summary=[];trials=[];failures=[];panels={};case_labels={}
    for job in jobs:
        tid=job['track_id'];norad=job['norad'];p=root/tid/'analysis';r=load(p/'result.json');verify(load(p/'protocol.json')['source_hashes']);old=load(s/'shifted-rejected-family-challenges-v1'/tid/'analysis/result.json')
        case=r['job']['label'];case_labels[tid]=case;times=np.asarray(r['times_s']);offset=0
        for e in r['entries']:
            tt=times[offset:offset+e['points']];offset+=e['points'];members.append(dict(scan=case,norad=norad,component=e['component'],role=e['role'],points=e['points'],start_s=float(tt.min()),end_s=float(tt.max())))
        for f,g in zip(r['folds'],old['folds'],strict=True):
            if f['seed']!=g['seed'] or f['split']!=g['split']:raise ValueError('phase refinement changed partitions')
            for arm,z in f['arms'].items():
                scores=z['scores'];b=scores['family_to_family'];a=scores['combined_to_family'];n=len(b['held_indices'])
                family.append(dict(scan=case,norad=norad,seed=f['seed'],arm=arm,held_family_points=n,before_RMS_hz=b['rms_hz'],after_RMS_hz=a['rms_hz'],
                    density_gain=b['negative_twice_log_density']-a['negative_twice_log_density'],density_gain_per_point=(b['negative_twice_log_density']-a['negative_twice_log_density'])/n,
                    target_family_only_RMS_hz=scores['family_to_target']['rms_hz'],target_bias_only_RMS_hz=z['bias_only_projection']['rms_hz'],target_combined_RMS_hz=scores['combined_to_target']['rms_hz']))
                for key,v in scores.items():
                    prior=g['arms'][arm]['scores'][key]
                    if v['held_indices']!=prior['held_indices']:raise ValueError('held points changed')
                    grid.append(dict(scan=case,seed=f['seed'],arm=arm,score=key,density_change=v['negative_twice_log_density']-prior['negative_twice_log_density'],RMS_change_hz=v['rms_hz']-prior['rms_hz']))
        native_path=s/'shifted-rejected-native-audit-v1'/tid;native=load(native_path/'result.json');verify(native['source_hashes'])
        shutil.copyfile(native_path/'native_audit.png',out/'figures'/f'{tid}-native.png')
        tt=np.asarray([p['time_s'] for p in native['points']]);poly=np.asarray([p['original_polynomial_residual_hz'] for p in native['points']]);panels[tid]=dict(times=tt,poly=poly,native=native,corrections={})
        for arm,a in native['arms'].items():
            gap=np.asarray(a['residual_hz'])-poly;native_rows.append(dict(scan=case,norad=norad,arm=arm,points=len(tt),graph_quality=native['graph_quality_status'],
                polynomial_RMS_hz=a['original_polynomial_RMS_hz'],orbital_RMS_hz=a['orbital_RMS_hz'],polynomial_orbit_correlation=a['polynomial_orbital_correlation'],centered_model_gap_RMS_hz=float(np.std(gap))))
        failed=load(s/'shifted-rejected-iq-refinement-v1'/(tid+'-terminal.json'))
        if failed['status']!='execution_failed':raise ValueError('initial incompatible-reader trial not preserved')
        failed_log=s/'shifted-rejected-iq-refinement-v1'/(tid+'-export.log');hashes[str(failed_log)]=hashlib.sha256(failed_log.read_bytes()).hexdigest();evidence[str(failed_log)]=failed_log.read_text()
        for version in (2,3):
            parent=s/f'shifted-rejected-iq-refinement-v{version}';folder=parent/tid;plan=load(folder/'plan.json');local=load(folder/'result.json');workers=load(folder/'execution.json')
            if not all(w['status']=='complete' for w in workers):raise ValueError('IQ worker incomplete')
            if local['plan_sha256']!=hashes[str(folder/'plan.json')]:raise ValueError('IQ plan changed')
            panel=s/'shifted-rejected-iq-refinement-v2'/tid/'panel';meta=load(panel/'manifest.json')
            if not meta['raw_authority_matches_tracking']:raise ValueError('raw authority mismatch')
            verify(meta['source_hashes']);verify(meta['reader_contract_sources']);verify(local['worker_hashes'])
            for path in local['worker_hashes']:
                worker=load(Path(path))
                if worker['panel_manifest_sha256']!=hashes[str(panel/'manifest.json')]:raise ValueError('worker used another IQ panel')
                verify(worker['source_hashes'])
            for point in meta['points']:
                if hashlib.sha256((panel/point['array']).read_bytes()).hexdigest()!=point['array_sha256']:raise ValueError('IQ panel changed')
            rows=local['rows'];ids=[row['point']['observation_id'] for row in rows]
            if ids!=[p['observation_id'] for p in native['points']]:raise ValueError('IQ target scope or order changed')
            delta=np.asarray([v['methods']['joint_all']['CFO_hz']-v['point']['CFO_hz'] for v in rows]);oe=np.asarray([v['methods']['joint_odd']['CFO_hz']-v['methods']['joint_even']['CFO_hz'] for v in rows]);panels[tid]['corrections'][version]=delta
            iq_summary.append(dict(scan=case,version=version,epoch_radius_samples=plan['epoch_radius_samples'],correction_RMS_hz=float(np.sqrt(np.mean(delta**2))),odd_even_RMS_hz=float(np.sqrt(np.mean(oe**2))),
                boundary_points=sum(any(v for k,v in row['methods']['joint_all'].items() if k.endswith('_search_boundary')) for row in rows),
                odd_complement_improved=sum(v['methods']['joint_odd']['complement_score']>v['methods']['joint_odd']['complement_score_at_original'] for v in rows),
                even_complement_improved=sum(v['methods']['joint_even']['complement_score']>v['methods']['joint_even']['complement_score_at_original'] for v in rows)))
            for arm,a in native['arms'].items():
                res=np.asarray(a['residual_hz']);measurements.append(dict(scan=case,version=version,arm=arm,points=len(res),original_centered_RMS_hz=float(np.std(res)),refined_centered_RMS_hz=float(np.std(res+delta)),fixed_orbit_receiver_and_position=True))
        for variant,parent in [('original',s/'shifted-annotation-inclusion-v1'),('shared_satellite_means',s/'shifted-rejected-shared-refresh-v1'),('conditional_satellite_and_bias',s/'shifted-rejected-conditional-refresh-v1'),('conditional_feasible_continuation',s/'shifted-rejected-conditional-feasible-v1')]:
            path=parent/tid/'trial';control=load(path/'control.json');addition=load(path/'target_0.json');audit=load(path/'exact_owner_replay.json');verify(audit['source_hashes']);protocol=load(path/'protocol.json')
            if variant!='original':
                terminal=load(parent/tid/'execution.json')
                if terminal['status']!='complete':raise ValueError('position prototype incomplete')
            qualified=bool(control['paired_valid'] and addition['paired_valid'] and audit['all_verified'])
            for arm,z in addition['arms'].items():
                b=control['arms'][arm];d=z['target_diagnostics'][0]
                before=set(b['proposed_associated_ids']);after=set(z['proposed_associated_ids']);targets={o for t in protocol['targets'] for o in t['observation_ids']}
                if qualified and (after-before!=targets or before-after):raise ValueError('qualified prototype needs a separate membership scope audit')
                trials.append(dict(scan=case,norad=norad,variant=variant,arm=arm,position_fit=protocol['position_fit'],control_valid=control['paired_valid'],addition_valid=addition['paired_valid'],exact_verified=audit['all_verified'],qualified=qualified,before_km=error(b),after_km=error(z),target_RMS_hz=d['RMS_hz'],added_points=len(after-before),lost_points=len(before-after),control_objective=b['negative_twice_elbo'],addition_objective=z['negative_twice_elbo']))
                panels[tid][variant,arm]=d
            for v in audit['rows']:
                for gate,slack in complete_replay_slacks(v).items():
                    if slack<0:failures.append(dict(scan=case,variant=variant,role=v['role'],arm=v['arm'],gate=gate,slack=slack))
    for name,rows in [('family_predictions.csv',family),('family_members.csv',members),('phase_grid_sensitivity.csv',grid),('native_model_comparison.csv',native_rows),('IQ_summary.csv',iq_summary),('fixed_orbit_measurement_effect.csv',measurements),('position_trials.csv',trials),('failed_gates.csv',failures)]:csvout(name,rows)
    fig,axes=plt.subplots(len(jobs),3,figsize=(17,4*len(jobs)),squeeze=False,layout='constrained')
    for axs,job in zip(axes,jobs,strict=True):
        tid=job['track_id'];p=panels[tid];tt=p['times'];original=np.asarray(p['native']['arms']['fitted_c']['residual_hz'])
        axs[0].plot(tt,p['poly'],'.-',label='Original graph polynomial');axs[0].plot(tt,original,'.-',label='Original orbital fit');axs[0].plot(tt,original+p['corrections'][3],'.-',label='IQ refinement, fixed orbital fit');axs[0].set(title=case_labels[tid],ylabel='Residual (Hz)')
        for version,label in [(2,'±0.75 samples'),(3,'±3 samples / 0.3 µs')]:axs[1].plot(tt,p['corrections'][version],'.-',label=label)
        axs[1].set_ylabel('Refined − archived CFO (Hz)')
        for variant,label in [('original','Original'),('shared_satellite_means','Shared satellite means'),('conditional_satellite_and_bias','Conditional satellite + bias'),('conditional_feasible_continuation','Conditional + feasible continuation')]:axs[2].plot(tt,p[variant,'fitted_c']['residual_hz'],'.-',label=label)
        axs[2].set_ylabel('Residual after full position fit (Hz)')
        for ax in axs:ax.axhline(0,c='k',lw=.5);ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    save(fig,'residual_and_refit_comparison.png')
    fig,axes=plt.subplots(len(jobs),2,figsize=(13,4*len(jobs)),squeeze=False,layout='constrained')
    for axs,job in zip(axes,jobs,strict=True):
        rows=[r for r in family if r['norad']==job['norad']];x=np.arange(len(rows));labels=[str(r['seed'])+'\n'+r['arm'] for r in rows]
        for k,label in [('before_RMS_hz','Without target training'),('after_RMS_hz','With target training')]:axs[0].plot(x,[r[k] for r in rows],'o-',label=label)
        axs[0].set(title=str(job['norad']),ylabel='Held incumbent RMS (Hz)');axs[0].legend(fontsize=8)
        axs[1].bar(x,[r['density_gain_per_point'] for r in rows]);axs[1].axhline(0,c='k',lw=.5);axs[1].set_ylabel('Held-family density gain / point\nPositive favors target training')
        for ax in axs:ax.set_xticks(x,labels,fontsize=7);ax.grid(alpha=.2)
    save(fig,'held_family_predictions.png')
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();ledger=list(csv.DictReader(previous.open()))
    for row in ledger:
        tid=row['track_id']
        if tid not in panels:continue
        row.update(shared_family_prediction_source=str(root/tid/'analysis/result.json'),shared_family_prediction_status='unresolved; target conditioning does not consistently improve held family prediction',
            raw_pilot_source=str(s/'shifted-rejected-iq-refinement-v3'/tid/'result.json'),raw_pilot_state='complete target replay; small CFO corrections do not remove orbital mismatch',
            shared_family_refresh_source=str(s/'shifted-rejected-shared-refresh-v1'/tid/'trial'),shared_family_refresh_status='inclusion_rejected')
        qualified=any(r['qualified'] and r['variant']=='conditional_feasible_continuation' and r['scan']==case_labels[tid] for r in trials)
        row.update(conditional_feasible_source=str(s/'shifted-rejected-conditional-feasible-v1'/tid/'trial'),conditional_feasible_status='RF_verified_research_candidate' if qualified else 'inclusion_rejected')
        if qualified:row.update(predictive_research_inclusion='RF_verified_conditional_feasible_research_candidate',predictive_inclusion_source=str(s/'shifted-rejected-conditional-feasible-v1'/tid/'trial'))
    csvout('annotation_ledger.csv',ledger)
    for n in ('remaining_role_candidates.json','remaining_shifted_candidates.json'):
        load(args.previous/n);shutil.copyfile(args.previous/n,out/n)
    batch=load(args.previous/'summary.json');summary=dict(batch=batch,maximum_density_grid_change=max(abs(r['density_change']) for r in grid),maximum_RMS_grid_change_hz=max(abs(r['RMS_change_hz']) for r in grid),prototype_qualified_cases=len({r['scan'] for r in trials if r['variant']!='original' and r['qualified']}),production_changed=False,goal_complete=False)
    write(out/'summary.json',summary);write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    native_gallery='\n\n'.join(f'![Native measurement audit {case_labels[j["track_id"]]}](figures/{j["track_id"]}-native.png)' for j in jobs)
    (out/'README.md').write_text(f'''# Rejected shared-family curves: measurement replay and model consistency

Both shared-family rejections from shifted batch one receive the same diagnostic sequence, without selecting by GPS improvement: randomized bidirectional family prediction, exact native GLRT replay, complete-target IQ remeasurement, and matched shared-satellite model variants. No points are trimmed and no labels are forced. The targets remain research hypotheses unless all physical and ownership checks pass.

## Family evidence and residual origins

{table(members,['scan','norad','component','role','points','start_s','end_s'])}

The family tests exclude the challenged family from receiver/position training and use the existing three randomized scanwide 12-second partitions with two-second guards. Target training can condition one shared phase/orbit distribution and receiver covariance, while the separately trained calibration stays fixed. Held points enter scoring only. The folds overlap; score changes are not calibrated association probabilities.

{table([r for r in family if r['arm']=='fitted_c'],['scan','seed','held_family_points','before_RMS_hz','after_RMS_hz','density_gain'])}

![Held-family prediction](figures/held_family_predictions.png)

67618's target produces small negative held-family density changes in all partitions. 68057 improves two partitions slightly and worsens one more noticeably. Neither gives consistent independent support for the required shared correction. Halving phase spacing from 0.05 to 0.025 seconds changes total density by at most **{summary['maximum_density_grid_change']:.4f}** and RMS by at most **{summary['maximum_RMS_grid_change_hz']:.3f} Hz** across recorded prediction modes. The conclusions are not explained by this quadrature spacing.

Both targets consist of **one original polynomial piece**: degree three for RX1 CH8 / 67618, degree two for RX1 CH3 / 68057. There is no joined-fragment seam. Their saved graph screens report no detected structure; that is not proof of a correct satellite identity. Polynomial residual RMS is about 102 Hz, while full orbital residual RMS is 152–163 Hz. The remaining difference includes smooth shape error. Polynomial fits can absorb smooth receiver/orbit errors, so this decomposition is a diagnostic rather than a measurement-error certificate.

{table([r for r in native_rows if r['arm']=='fitted_c'],['scan','polynomial_RMS_hz','orbital_RMS_hz','polynomial_orbit_correlation','centered_model_gap_RMS_hz'])}

{native_gallery}

## Bounded IQ remeasurement

Every archived GLRT winner and alias lift is replayed exactly. All 36 target points in each scan are remeasured from existing IQ; no frequency point is chosen or discarded based on its residual. The local estimator fits known-pilot carrier frequency, fractional epoch and code rate, with independently fitted odd/even frame subsets and complementary-frame scores. It uses no GPS, TLE, satellite label, orbital prediction or polynomial target value. Odd/even fits share the original full-window nomination and are not independent end-to-end acquisitions.

The first export failed before reading samples because the research reader implements the 2.5 MS/s v1 contract while these 10 MS/s recordings use v2. Those terminal failures are preserved. The measurement-only exporter was decoupled from analysis imports and rerun through the pinned deployed multirate reader. The exporter verifies all source windows and the original raw authority digest, recording the reader and contract source hashes. No persisted contract, raw recording, or production reader was changed.

The initial ±0.75-sample epoch search hit its boundary once for 67618 and 34 times for 68057. At 10 MS/s that bound is only 75 ns; the same setting at 2.5 MS/s permits 300 ns. A measurement-only sensitivity test applies the same **300 ns physical bound**, i.e. ±3 samples at 10 MS/s, to both complete targets. It removes all boundary hits but barely changes CFO estimates. Original failed exports and both successful estimator settings remain in the evidence.

{table(iq_summary,['scan','version','epoch_radius_samples','correction_RMS_hz','odd_even_RMS_hz','boundary_points','odd_complement_improved','even_complement_improved'])}

Corrections are only about **19–21 Hz RMS**. With the original orbital prediction, receiver and position held fixed, fitted-c centered residual RMS changes approximately **163.3→160.4 Hz** for 67618 and **151.6→153.7 Hz** for 68057. These local pilot refinements therefore do not explain the large smooth model gap. This does not rule out wrong peaks, source mixtures or other measurement models; it rules out this particular local refinement as a sufficient fix. Refined measurements are not substituted into production or the following position experiments.

## Existing shared-satellite update variants

All position experiments below use the original observations and causal candidate identities. Controls and additions are matched in each c arm and variant. The shared-moment projection exposes posterior satellite means while preserving receiver means at each position; it leaves the original marginal objective intact at a fixed phase reference. The conditional variant updates satellite and existing track-bias coordinates, holding excluded posterior coordinates at their means. That changes predictive uncertainty and the objective, so it is a separate model experiment, not an equivalent implementation.

The final variant uses the existing feasible optimizer with unchanged gates. It is explicitly a **continuation from the scan's saved RF-only incumbent**, not a fresh regional start and not a GPS initialization. Its matched control uses the same continuation. It tests whether the remaining violations are avoidable through constrained optimization; it does not establish global convergence.

{table(trials,['scan','variant','arm','control_valid','qualified','before_km','after_km','target_RMS_hz'])}

![Residuals, IQ corrections and full refits](figures/residual_and_refit_comparison.png)

Residual RMS improvement alone cannot authorize inclusion. The shared-moment projection improves the target fit but creates incumbent residual failures; the 68057 control already fails an incumbent conditional-mean check. Some conditional-mean failures involve exposing satellite coordinates without their correlated incumbent track-bias coordinates. They must not be interpreted as proof of a wrong satellite. [All failing gates](failed_gates.csv), including controls, and [matched trial results](position_trials.csv) preserve those limitations. Position accuracy is evaluation-only, and no gate is relaxed because an endpoint is closer to GPS.

The conditional satellite-and-bias variant restores valid controls for both cases and removes the large incumbent mean failures. It still fails target shape checks; 67618 also conflicts with its existing CH2 track. That trial reaches about 362 m fitted-c error but remains unqualified. Across the additional model variants, **{summary['prototype_qualified_cases']} cases** pass full paired RF/replay/membership qualification. The feasible-continuation result is included in that count only if both c arms and the control pass every required check.

The feasible continuations also fail and produce substantial regressions: fitted-c errors reach about **19.13 km for 67618** and **5.21 km for 68057**. The latter loses 67 incumbent points, and the former proposes 29 additional unvalidated extension points beyond its target. None of those assignments counts as a recovery. Small phase-refresh changes do not make an infeasible endpoint acceptable. These failures are preserved rather than replacing them with the better-looking unconstrained endpoints; further optimization of these variants is stopped for this iteration.

## Inventory progress and next discriminating tests

[Shifted batch two](../2026_10_30_shifted_annotation_batch2/README.md) completes **{batch['annotations']}** further annotations and **{batch['position_trials']}** matched inclusion cases. **{batch['qualified_curves']} curves / {batch['qualified_points']} points** qualify in separate trials. Its seven numerical-only follow-ups retain matched controls and physical gates. A source-hashed scope audit excludes 16 incidental extension points in one fitted-c result because they were not part of that target's validation or position fit.

The updated ledger preserves these two targets as unresolved and carries all batch results forward. **{batch['remaining_shifted']} shifted-origin and {batch['remaining_older_role']} older-role cases remain; the queues overlap.** No new production version is justified by this iteration alone.

Next work should challenge the conditional identity hypotheses against broader causal candidates and compare simultaneous same-receiver evidence before adding receiver flexibility. A coherent satellite-and-track-bias posterior must also predict independently held family observations, not merely fix in-sample conditional means. For these two targets, another small local CFO adjustment is unlikely to be sufficient. Continue the remaining inventory in bounded batches and test recoveries jointly; do not keep optimizing only the same difficult curves. Source hashes, terminal receipts, native candidate evidence, worker receipts, all c arms and figures accompany this report. No new RF was collected, and the full objective remains incomplete.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
