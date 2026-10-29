"""Report shared-family recovery, owner-gate diagnoses and phase resolution."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_systematic_annotation import compact_evidence
from report_predictive_track_annotation import table


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir();sources={};evidence={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=r;return r
    def csvfile(name,rr):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]),lineterminator='\n');w.writeheader();w.writerows(rr)
    protocol=load(s/'curved-family-inclusion-cohort-v1/protocol.json');fits=[];group_table=[];gallery=[];gate_rows=[]
    for job in protocol['jobs']:
        tag=job['job_id']+'-'+str(job['norad']);folder=s/'curved-family-inclusion-cohort-v1'/tag
        pr=load(folder/'protocol.json');control=load(folder/'control.json');combined=load(folder/'combined.json')
        gates=load(s/'curved-family-gate-explanations-v1'/tag/'result.json')
        for name,pair in gates['variants'].items():
            for arm,v in pair.items():
                for t in v['tracks']:
                    if t['failure_reasons']:gate_rows.append(dict(scan=job['label'],family=job['norad'],variant=name,arm=arm,component=t['component'],reasons=';'.join(t['failure_reasons']),RMS_hz=t['profile_RMS_hz']))
        for p in sorted(folder.glob('*.json')):
            r=load(p)
            if 'arms' not in r:continue
            for arm,v in r['arms'].items():
                fits.append(dict(scan=job['label'],family=job['norad'],variant=p.stem,arm=arm,position_error_km=error(v),
                    added=v['added_points'],lost=v['lost_points'],paired_valid=r['paired_valid'],phase_change_s=v['final_phase_change_s'],RMS_hz=v['RMS_hz']))
        group_table.append(dict(scan=job['label'],satellite=job['norad'],tracks=len(pr['targets']),graph_points=sum(t['points'] for t in pr['targets']),
            c0_error=f"{error(control['arms']['c0']):.3f} → {error(combined['arms']['c0']):.3f}",
            fitted_error=f"{error(control['arms']['fitted_c']):.3f} → {error(combined['arms']['fitted_c']):.3f}",
            proposed_added=combined['arms']['fitted_c']['added_points'],lost=combined['arms']['fitted_c']['lost_points'],passes=combined['paired_valid']))
        fig,axs=plt.subplots(2,1,figsize=(11,7),layout='constrained');tracks=combined['arms']['fitted_c']['targets']
        for k,t in enumerate(tracks):
            label=t['component'].split('-RF')[0].split('-RX')[-1];color=plt.cm.tab10(k)
            axs[0].scatter(t['times_s'],np.array(t['CFO_hz'])/1000,s=10,c=[color],label='RX'+label)
            axs[0].plot(t['times_s'],np.array(t['predicted_CFO_hz'])/1000,c=color,lw=1)
            axs[1].plot(t['times_s'],t['residual_hz'],'.-',ms=3,c=color,label='RX'+label)
        axs[0].set(ylabel='GLRT CFO (kHz)',title='Points: observations; lines: fitted orbit + receiver prediction');axs[0].legend(fontsize=8,ncol=3)
        axs[1].axhline(0,c='black',lw=.8);axs[1].set(ylabel='Conditional residual (Hz)',xlabel='Scan time (s)')
        for ax in axs:ax.grid(alpha=.2)
        fig.suptitle(f"{job['label']} / {job['norad']} — combined curved-role proposal; paired pass = {combined['paired_valid']}")
        fig.savefig(figs/(tag+'.png'),dpi=145);plt.close(fig);gallery.append(f"### {job['label']} / {job['norad']}\n\n![GLRT and residuals](figures/{tag}.png)\n")
    csvfile('curved_trials.csv',fits);csvfile('gate_failures.csv',gate_rows)
    role_protocol=load(s/'curved-predictive-role-v1/protocol.json');roles=[];rolefits=[];role_status={};role_gallery=[]
    for job in role_protocol['jobs']:
        t=job['target'];tid=t['track_id'];root=s/'curved-predictive-role-v1'/tid;r=load(root/'annotation/result.json');a=r['annotation'];role_status[tid]=a
        roles.append(dict(scan=job['job']['label'],component=t['component'].split('-RF')[0],points=t['points'],original_nomination=t['norad'],
            predictive_status=a['status'],predictive_nomination=a['norad']))
        for mode,folder in [('lbfgsb_0.1',root/'inclusion'),('powell_0.1',s/'curved-predictive-role-powell-v1'/tid),('powell_0.025',s/'curved-predictive-role-fine-v1'/tid),('powell_0.0125',s/'curved-predictive-role-finer-v1'/tid)]:
            if not (folder/'new_family.json').exists():continue
            result=load(folder/'new_family.json');control=load(folder/'control.json');load(folder/'protocol.json')
            if mode=='powell_0.0125':
                v=result['arms']['fitted_c'];detail=v['family']['diagnostics'][0];fig,axs=plt.subplots(2,1,figsize=(10,6),layout='constrained')
                tt=np.array(detail['times_s']);axs[0].scatter(tt,np.array(detail['CFO_hz'])/1000,s=17,label='Native GLRT')
                axs[0].plot(tt,np.array(detail['prediction_CFO_hz'])/1000,c='#cc3311',label='Causal orbit + correction + fixed receiver')
                axs[0].set_ylabel('CFO (kHz)');axs[0].legend(fontsize=8)
                axs[1].plot(tt,np.array(detail['raw_residual_hz'])-detail['profile_bias_hz'],'.-',ms=4);axs[1].axhline(0,c='black',lw=.8)
                axs[1].set(xlabel='Scan time (s)',ylabel='Residual after track bias (Hz)',title=f"RMS {detail['profile_RMS_hz']:.1f} Hz; lag-one correlation {detail['noise']['lag1_acf']:.3f}")
                for ax in axs:ax.grid(alpha=.2)
                fig.suptitle(t['component'].split('-RF')[0]+f" | predictive role, paired pass = {result['paired_valid']}")
                name='predictive-'+tid+'.png';fig.savefig(figs/name,dpi=145);plt.close(fig)
                role_gallery.append(f"### {t['component'].split('-RF')[0]}\n\n![Predictive-role GLRT and residuals](figures/{name})\n")
            for arm,v in result['arms'].items():
                f=v['family'];rolefits.append(dict(scan=job['job']['label'],component=t['component'].split('-RF')[0],track_id=tid,mode=mode,arm=arm,
                    control_error_km=error(control['arms'][arm]),target_error_km=error(v),added=v['added_points'],lost=v['lost_points'],
                    control_passes=control['paired_valid'],target_passes=result['paired_valid'],
                    phase_sd_s=f['phase_sigma_s'],phase_map_s=f['phase_map_s'],target_RMS_hz=f['diagnostics'][0]['profile_RMS_hz'],
                    incumbent_objective=v['incumbent_objective'],target_objective=f['negative_twice_log_density'],
                    final_optimizer_success=v['history'][-1]['success'],seconds=result['seconds'],endpoint_east_north_km=v['endpoint_east_north_km']))
    csvfile('predictive_role_annotations.csv',roles);csvfile('predictive_role_trials.csv',rolefits)
    convergence=[]
    for v in rolefits:
        if v['mode']!='powell_0.0125':continue
        old=next(r for r in rolefits if r['track_id']==v['track_id'] and r['arm']==v['arm'] and r['mode']=='powell_0.025')
        convergence.append(dict(component=v['component'],arm=v['arm'],endpoint_change_m=float(1000*np.linalg.norm(np.array(v['endpoint_east_north_km'])-np.array(old['endpoint_east_north_km'])))))
    csvfile('position_grid_convergence.csv',convergence)
    groups=list(dict.fromkeys(v['track_id'] for v in rolefits));fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for k,mode in enumerate(['lbfgsb_0.1','powell_0.1','powell_0.025','powell_0.0125']):
            rr=[next((v for v in rolefits if v['track_id']==g and v['arm']==arm and v['mode']==mode),None) for g in groups]
            for i,v in enumerate(rr):
                if v:ax.scatter(i+(k-1.5)*.15,v['target_error_km'],marker='o' if v['target_passes'] else 'x',color=plt.cm.tab10(k),label=mode if i==0 else None)
        baseline=[next(v for v in rolefits if v['track_id']==g and v['arm']==arm) for g in groups]
        ax.scatter(range(len(groups)),[v['control_error_km'] for v in baseline],marker='_',s=160,c='black',label='matched control')
        ax.set_xticks(range(len(groups)),[v['component'].replace('DS24-','').replace('-RX','\nRX') for v in baseline]);ax.set(title=arm,ylabel='Evaluation position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Predictive role: solver and phase-resolution audit; × fails existing checks')
    fig.savefig(figs/'role_position_errors.png',dpi=150);plt.close(fig)
    line=load(s/'predictive-phase-resolution-line-v1/result.json');line_summary=[];fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,(arm,r) in enumerate(line['arms'].items()):
        xx=np.array([v['fraction'] for v in r['rows']])*r['displacement_km'];fine=np.array([v['scores'][-1]['total_score'] for v in r['rows']])
        for k in range(4):
            step=r['rows'][0]['scores'][k]['step_s'];yy=np.array([v['scores'][k]['total_score'] for v in r['rows']]);mins=[i for i in range(1,len(yy)-1) if yy[i]<yy[i-1] and yy[i]<yy[i+1]]
            axs[0,col].plot(xx,yy-min(fine),'.-',ms=3,label=f'{step:g} s');axs[1,col].plot(xx,yy-fine,label=f'{step:g} s')
            line_summary.append(dict(arm=arm,step_s=step,local_minima=len(mins),max_score_difference_to_finest=float(np.max(abs(yy-fine)))))
        axs[0,col].set(title=arm,ylabel='Joint objective − finest-grid minimum');axs[1,col].set(xlabel='Displacement along saved update (km)',ylabel='Score difference from 0.0125 s grid')
        for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('DS24-0095 CH2: a 0.1 s phase grid introduces an extra minimum\nFixed positions; five incumbent phase refreshes per position; no GPS selection')
    fig.savefig(figs/'phase_resolution_loss_line.png',dpi=150);plt.close(fig);csvfile('phase_resolution.csv',line_summary)
    jointrows=[]
    for step,folder in [(.025,s/'curved-predictive-joint-v1/inclusion'),(.0125,s/'curved-predictive-role-finer-v1/joint')]:
        joint=load(folder/'new_family.json');jc=load(folder/'control.json')
        for arm,v in joint['arms'].items():jointrows.append(dict(step_s=step,arm=arm,control_error_km=error(jc['arms'][arm]),joint_error_km=error(v),added=v['added_points'],lost=v['lost_points'],paired_pass=joint['paired_valid'],control_pass=jc['paired_valid']))
    csvfile('predictive_joint.csv',jointrows)
    auditrows=[]
    for root in ['new-family-phase-resolution-audit-v1','curved-family-phase-resolution-audit-v1']:
        ap=load(s/root/'protocol.json')
        for j in ap['jobs']:
            ar=load(s/root/j['name']/'result.json')
            for arm,v in ar['arms'].items():auditrows.append(dict(cohort=root,scan=ar['job']['label'],case=j['name'],arm=arm,
                phase_step_s=v['steps_s'][0],local_agreement=v['local_agreement'],score_change=v['maximum_score_change'],
                gradient_change=v['gradient_change_per_km']))
    csvfile('phase_integral_audit.csv',auditrows)
    coarse_guard=load(s/'curved-predictive-coarse-guard-v1/result.json')
    smoke=load(s/'curved-predictive-guard-smoke-v1/new_family.json');smoke_control=load(s/'curved-predictive-guard-smoke-v1/control.json')
    smoke_rows=[dict(arm=a,control_error_km=error(smoke_control['arms'][a]),target_error_km=error(v),
        added=v['added_points'],lost=v['lost_points'],numerical_pass=v['phase_resolution_audit']['local_agreement'],
        paired_pass=smoke['paired_valid'],control_pass=smoke_control['paired_valid']) for a,v in smoke['arms'].items()]
    csvfile('integrated_numerical_guard.csv',smoke_rows)
    audit_groups=list(dict.fromkeys(v['case'] for v in auditrows));fig,axs=plt.subplots(2,1,figsize=(15,8),layout='constrained')
    for arm,offset,color in [('c0',-.13,'#4477aa'),('fitted_c',.13,'#ee6677')]:
        rr=[next(v for v in auditrows if v['case']==g and v['arm']==arm) for g in audit_groups]
        for ax,key in zip(axs,['score_change','gradient_change'],strict=True):ax.bar(np.arange(len(rr))+offset,[max(v[key],1e-10) for v in rr],.24,color=color,label=arm)
    for ax,limit,label in zip(axs,[.001,.01],['Max local score change','Gradient change per km'],strict=True):
        ax.axhline(limit,c='black',ls='--');ax.set_yscale('log');ax.set_ylabel(label);ax.grid(axis='y',alpha=.2);ax.legend()
        ax.set_xticks(range(len(audit_groups)),[next(v['scan'] for v in auditrows if v['case']==g)+'\n'+g[-8:] for g in audit_groups],rotation=45,ha='right')
    fig.suptitle('Local quadrature audit: original step versus quarter-step, at endpoint and ±25 m\nThresholds are numerical tolerances, not position accuracy or confidence bounds')
    fig.savefig(figs/'phase_integral_audit.png',dpi=145);plt.close(fig)
    previous=Path(__file__).resolve().parents[1]/'reports/2026_10_29_family_position_transfer/annotation_ledger.csv';sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();prior={v['track_id']:v for v in csv.DictReader(previous.open())}
    q=s/'systematic-annotation-v1';ledger=[]
    for t in load(q/'protocol.json')['rows']:
        row=dict(prior[t['track_id']]);row.update(predictive_role_status='',predictive_role_norad='',annotation_result_kind='',original_execution_completed='')
        if not row.get('annotation_source'):
            p=(Path(t['known_validation']) if t['known_validation'] else q/t['track_id'])/'result.json'
            if p.exists():
                r=load(p);a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'));row.update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(p),
                    annotation_result_kind=r.get('result_kind',''),original_execution_completed=r.get('original_execution_completed',''))
            else:
                receipts=sorted(q.glob('attempt-*/'+t['track_id']+'-terminal.json'))
                if receipts:row['state']='execution_'+load(receipts[-1])['status']
        if t['track_id'] in role_status:row.update(predictive_role_status=role_status[t['track_id']]['status'],predictive_role_norad=role_status[t['track_id']]['norad'])
        ledger.append(row)
    csvfile('annotation_ledger.csv',ledger);assessed=sum(bool(v['annotation_source']) for v in ledger);ds=[v for v in ledger if 'DS24' in v['scopes']];ds_assessed=sum(bool(v['annotation_source']) for v in ds)
    ds_states=[dict(outcome=k,tracks=v) for k,v in Counter(r['state'] for r in ds).items()]
    small=[]
    for v in rolefits:
        if v['arm']=='fitted_c':small.append(dict(component=v['component'],mode=v['mode'],error_km=f"{v['control_error_km']:.3f} → {v['target_error_km']:.3f}",added=v['added'],control_pass=v['control_passes'],target_pass=v['target_passes']))
    text=f'''# Curved-family recovery, predictive roles and an artificial phase-grid minimum

The inventory now has **{assessed:,}/1,630 assessed tracks**, including **{ds_assessed}/289 DS24 tracks**. These counts include unresolved outcomes and do not claim all labels are correct. The complete ledger retains all pending and timed-out cases, previous phase-audit corrections, and new role-dependent identity results.

DS24-0015's final scheduled fit hit the 600-second cap. Its saved geometry had already made one of the three declared random partitions unusable, proving that the required three-partition identity consensus could not be achieved. It is explicitly classified as insufficient partitions using that certificate; the execution remains recorded as timed out, unfinished candidate fits are not claimed complete, and no satellite identity is assigned.

DS24 outcomes under each track's declared annotation role:

{table(ds_states,list(ds_states[0]))}

These are conditional annotations, not accepted recoveries. The two DS24-0065 curves that become unstable in the new predictive-role test remain explicitly flagged in separate ledger columns.

## What this iteration tested

We selected the four largest DS24 groups among annotations available when this cohort was frozen, requiring at least two separately conditionally supported curved tracks, ranked by graph-point count and without GPS selection. Later annotation results do not alter that frozen cohort. All 13 selected curves already carried the same satellite nominations in the original model. None had active calibration points. Thus their absence was caused after nomination; these tests do not establish that every original nomination is true.

Each trial retains the original noise, confidence weights, receiver priors, existing predictive rows, causal TLEs and orbital-support rule. Both c=0 and fitted-c start at the regional center in the same 25 × 25 km box, with five phase-refresh rounds and 48 bounded Gauss–Newton iterations per round. We fit no-target controls, every target separately, and all same-family targets together. There is no trimming, residual-gate relaxation or GPS-guided choice.

{table(group_table,list(group_table[0]))}

Errors are kilometres. Added points are proposed memberships before acceptance, including any additional post-fit associations; they can exceed the target graph-point count. All four combined curved-role proposals fail existing checks, despite some improving evaluation error. Improving GPS error does not authorize them.

## Why clean-looking tracks still disappear

We replayed every saved objective and every retained-track gate. The new diagnostic separates profile residual noise, conditional residual noise, alias, bias, visibility and the multiple-owner rule. That rule requires two passing receiver/channel owners for certain learned orbital corrections. A clean curve can consequently be rejected when its companion fails.

Six individual curves pass all residual and physical screens in both c arms and fail solely on owner support. DS24-0095 RX2 CH2 T000 is a clear example: 62 points, approximately 20 Hz conditional RMS, and no conditional residual structure. Other failures are real structured residuals under the tested model, such as DS24-0065's combined CH1/CH4 fits. Removing the ownership check would not repair those discrepancies.

## Use a curve as predictive evidence before allowing it to calibrate

For all six owner-only cases, we tested a predictive-only role: the curve does not change receiver calibration at fixed position. Its contribution integrates receiver uncertainty, a causal phase prior and three physical orbit-error modes. A frozen label with zero active calibration is explicitly distinguished from a calibrated satellite. Existing same-family predictive evidence is rejected by this prototype until a joint conditioning implementation is provided; it is not counted twice.

Before inclusion, all six curves received fresh full-catalogue nominations and randomized 12-second-block prediction tests (2-second guards; seeds 20261029, 94721, 4081), with fixed training-only preprocessing. Four preserve their conditional identities; both DS24-0065 curves become unstable. The ledger keeps that disagreement rather than declaring either label confirmed.

{table(roles,list(roles[0]))}

## A numerical source of a local minimum

In the initial DS24-0095 CH2 predictive fit, the inferred phase standard deviation was only 0.024–0.033 s, finer than the 0.1 s integration grid. A fixed-position line probe, with five phase refreshes at each position, shows two sampled minima in the fitted-c objective at 0.1 s spacing. At 0.05, 0.025 and 0.0125 s, only one remains on this line. The coarse objective differs from the finest by up to 0.251 score units; 0.025 versus 0.0125 differs by less than 0.000008 on the same sampled line.

This is a numerical defect in the new phase-grid recovery prototype. It is not evidence that every ALGO baseline failure shares this cause. The line probe is neither a full two-dimensional search nor a proof of a global optimum.

![Phase grid and objective minima](figures/phase_resolution_loss_line.png)

## Solver and quadrature comparisons

All four identities that survive role revalidation are tested with the original L-BFGS-B at 0.1 s, Powell at 0.1 s, Powell at 0.025 s and Powell at 0.0125 s. Controls and targets share the same solver within each comparison, the same regional start, five rounds and maximum budgets of 48 iterations and 240 function evaluations per round. Function evaluations cost more at finer phase resolution. Optimizer warnings remain visible; failed controls are not presented as certified baselines.

{table(small,list(small[0]))}

![Position errors for both c arms](figures/role_position_errors.png)

The full refits at 0.025 and 0.0125 s differ by at most **{max(v['endpoint_change_m'] for v in convergence):.3f} metres** across these four individual cases and both c arms. This is numerical reproducibility, not position accuracy. [All endpoint differences](position_grid_convergence.csv) are retained.

The largest surviving family group by graph points, DS24-0095 / 66886, is also tested jointly with one shared phase and three shared orbital modes, using Powell and both fine phase spacings:

{table(jointrows,list(jointrows[0]))}

These are research inclusion tests, not an ALGO promotion. Predictive inclusion can pass and still worsen position; more associated points alone do not establish more accurate localization. GPS at 37.849061591561885, −122.48574968092912 is used only in this report. The inference box remains centered at 37.906, −122.545.

## GLRT and residual figures

The following show each combined curved-role proposal. Lines include receiver terms and orbital predictions; they are not bare orbital Doppler. Residual structure and rejected companion curves remain visible.

{''.join(gallery)}

## Predictive-role GLRT and residuals

These use the finest tested phase grid and fitted-c arm. The receiver calibration is learned from the incumbent observations at the proposed position; these target points do not recalibrate it. The orbit correction is shared within the tested satellite family. Residuals below remove the separately profiled track bias used by the gate.

{''.join(role_gallery)}

## Remaining work and audit scope

We also audited all ten preceding new-family proposals and the five new finest-grid fits. At each saved endpoint and at ±25 m east/north, we compare the fitted phase step, half-step and quarter-step. The predeclared local tolerances are 0.001 score units and 0.01 score units/km gradient change; the final refinement must agree four times more closely. **{sum(not v['local_agreement'] for v in auditrows)}/{len(auditrows)} c-arm audits fail this local numerical screen.** Exact source-likelihood replay is required before any comparison. This is an exploratory numerical certificate, not a calibrated uncertainty bound or a proof of global convergence.

![Local phase integral audit](figures/phase_integral_audit.png)

The research new-family inclusion command now requires this post-fit numerical audit by default, in addition to its existing identity, residual, membership and optimizer checks. A coarse proposal that fails remains rejected until refit with adequate phase resolution. The audit adds 15 likelihood evaluations per c arm outside the position-search budget. An explicit `--skip-phase-audit` option exists only to reproduce historical results and marks the output as unchecked. The tables above retain the original trial checks and the separate audit outcomes rather than silently rewriting historical qualifications. The standard curved calibration solver uses its own phase-refresh approximation and is not replaced by this experiment.

The original 0.1 s CH2 endpoints fail the new numerical screen in both c arms. A full rerun through the command with its default numerical guard, at 0.025 s, produces:

{table(smoke_rows,list(smoke_rows[0]))}

The full annotation queue remains active. Correct annotation includes explicit ambiguity: two curves now show different identity conclusions when their permitted calibration role changes. Frozen graph selection, aliases and incumbent identities remain conditional inputs to these tests. Joint inclusion and observational consistency are still distinct from independent end-to-end position validation. No production algorithm or scientific golden fixture is changed.

Artifacts: [complete ledger](annotation_ledger.csv), [all curved trials](curved_trials.csv), [gate failures](gate_failures.csv), [role annotations](predictive_role_annotations.csv), [paired role trials](predictive_role_trials.csv), [joint role trial](predictive_joint.csv), [numerical checks](phase_resolution.csv), [source hashes](sources.json), and [compact evidence](evidence.json.gz). Repetitive observation IDs and history arrays are represented by counts and hashes; raw files remain on the study volume.

The focused suite passes 22 tests, covering atomic multi-track reassignment, preservation of other memberships, scoped queue claims, prohibition on predictive reuse of active calibration points, and the existing dense Gaussian likelihood and phase-mixture oracles. A new continuous Gaussian integral oracle demonstrates that the local audit rejects underresolved phase integration and accepts a converged integral. A separate regression requires an explicit geometry certificate before classifying a timed-out case as insufficient; it preserves the timeout and cannot manufacture a supported identity. Real-data replay verifies objectives within 1e−5 and exact agreement with the original gate decisions. The [preceding report](../2026_10_29_family_position_transfer/README.md) documents independent-family transfer limitations.
'''
    (out/'README.md').write_text(text);write(out/'sources.json',sources)
    write(out/'summary.json',dict(assessed=assessed,ds24_assessed=ds_assessed,annotation_states=dict(Counter(v['state'] for v in ledger)),groups=group_table,role_trials=rolefits,joint=jointrows))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    print(dict(assessed=assessed,ds24_assessed=ds_assessed,role_trials=len(rolefits)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['study','output']:p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
