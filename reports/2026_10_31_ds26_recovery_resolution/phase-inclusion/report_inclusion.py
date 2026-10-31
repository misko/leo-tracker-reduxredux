"""Reporting-only comparison of already sealed inclusion trials."""
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from run_inclusion import CASES,qualified_points

ROOT=Path(__file__).resolve().parent
COLORS={'c0':'#2166ac','fitted_c':'#d97706'}
LABELS={'c0':'c = 0','fitted_c':'fitted c'}


def read(path):return json.loads(path.read_text())


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_seal(path):
    seal=read(path)
    if not all(sha(p)==digest for p,digest in seal['artifacts_sha256'].items()):raise ValueError(f'seal mismatch: {path}')
    return seal


def position_error_m(latlon):
    # Known site enters only this post-seal reporting module.
    known=(37.849061591561885,-122.48574968092912)
    a,b,c,d=map(math.radians,(*known,*latlon))
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371008.8*2*math.asin(min(1.,math.sqrt(h)))


def target_stats(v,audit_row,route,norad,component):
    if route=='new_family':
        detail=v['family'];diag=detail['diagnostics'][0];noise=diag['noise']
        return dict(RMS_hz=diag['profile_RMS_hz'],bias_hz=diag['profile_bias_hz'],
            quadratic_BIC_gain=noise['quadratic_bic_gain'],maximum_step_z=noise['maximum_step_z'],
            phase_mean_s=detail['phase_mean_s'],phase_boundary_mass=detail['phase_boundary_mass'],
            phase_resolution_agreement=v['phase_resolution_audit']['local_agreement'],
            gates=detail['gates'],source='exact new-family grid; original receiver mean')
    exact=next(r for r in audit_row['exact_family_replays'] if r['norad']==norad)
    prefix=component+'/linear/';slacks=exact['all_gate_slacks'];diag=v['target_diagnostics'][0]
    return dict(RMS_hz=diag['RMS_hz'],bias_hz=diag['bias_hz'],
        quadratic_BIC_gain=10*(1-slacks[prefix+'quadratic']),maximum_step_z=4*(1-slacks[prefix+'step']),
        gates=v['targets'],source='exact shared target replacement; original fitted coefficients')


def row_summary(case,limit,role,arm,saved,audit_row,protocol):
    v=saved['arms'][arm];route=protocol['route'];target=protocol['target'];norad=protocol['norad']
    exacts=audit_row.get('exact_family_replays',audit_row.get('exact_incumbent_family_replays'))
    negative={key:value for q in exacts for key,value in q['all_gate_slacks'].items() if value<0}
    target_detail=target_stats(v,audit_row,route,norad,target['component']) if role=='addition' else None
    optimizer=[]
    for h in v['history']:
        if 'fit' in h:
            f=h['fit'];optimizer.append(dict(termination=f.get('stopped'),evaluations=f.get('evaluations'),iterations=f.get('iterations')))
        else:optimizer.append(dict(success=h['success'],message=h['message'],evaluations=h['nfev']))
    return dict(case=case,reference_limit_s=limit,role=role,arm=arm,route=route,norad=norad,
        paired_valid=saved['paired_valid'],exact_owner_verified=audit_row['verified'],
        final_phase_change_s=v['final_phase_change_s'],curved_RMS_hz=v['RMS_hz'],objective=v['negative_twice_elbo'],
        endpoint_east_north_km=v['endpoint_east_north_km'],position_error_m=position_error_m(v['endpoint_latlon']),
        proposed_added_points=v['added_points'],lost_points=v['lost_points'],
        incumbent_ownership_changes=len(audit_row['incumbent_ownership_changes']),
        control_ownership_changes=len(audit_row['control_ownership_changes']),
        maximum_exact_orbit_difference_hz=max(q['maximum_linearization_difference_hz'] for q in exacts),
        exact_negative_global_gate_slacks=negative,
        exact_replay_note='Each family replacement reruns global gates; a failure does not identify that family as bad.',
        failed_curved=[g['component'] for g in v['gates']['tracks'] if not g['compatible']],
        failed_predictive=[g['component'] for g in v['linear_gates'] if not g['compatible']],
        target=target_detail,optimizer_rounds=optimizer,
        optimizer_evaluations=sum(r.get('evaluations') or 0 for r in optimizer))


def main():
    verify_seal(ROOT/'batch_inference_seal.json');execution=read(ROOT/'execution.json')
    rows=[];cases=[]
    for case in CASES:
        root=ROOT/'cases'/case
        if not (root/'inference_seal.json').exists():
            cases.append(dict(case=case,completed=False,failure=read(root/'failure.json')));continue
        verify_seal(root/'inference_seal.json');protocol=read(root/'protocol.json')
        route=protocol['route'];terminal=read(root/'terminal.json');limits=[]
        for limit in (15,30):
            folder=root/f'reference{limit}/inclusion';control=read(folder/'control.json')
            add_name='target_0' if route=='shared' else 'new_family';addition=read(folder/(add_name+'.json'))
            audit=read(folder/'exact_owner_replay.json')
            for role,actual,saved in (('control','control',control),('addition',add_name,addition)):
                for arm in ('c0','fitted_c'):
                    audited=next(r for r in audit['rows'] if r['role']==actual and r['arm']==arm)
                    rows.append(row_summary(case,limit,role,arm,saved,audited,protocol))
            added=min(v['added_points'] for v in addition['arms'].values())
            qualified=qualified_points(control['paired_valid'],addition['paired_valid'],audit['all_verified'],added)
            limits.append(dict(reference_limit_s=limit,control_paired_valid=control['paired_valid'],
                addition_paired_valid=addition['paired_valid'],exact_owner_all_verified=audit['all_verified'],
                proposed_points=added,qualified_recovery_points=qualified,production_accepted_points=0))
        cases.append(dict(case=case,completed=terminal['completed'],route=route,norad=protocol['norad'],
            target_points=len(protocol['target']['observation_ids']),seconds=terminal['seconds'],budget_seconds=590,limits=limits))
    summary=dict(cases=cases,rows=rows,source_batch_inference_seal_sha256=sha(ROOT/'batch_inference_seal.json'),
        source_reporter_sha256=sha(Path(__file__)),all_inference_seals_valid=True,
        GPS_used_for_inference=False,position_reporting_only=True,production_accepted_points=0,
        qualified_recovery_definition='Both c arms pass matched control/addition, phase, RF, incumbent, exact-orbit and owner audits.',
        total_qualified_points_reference30=sum(v['qualified_recovery_points'] for c in cases for v in c.get('limits',[]) if v['reference_limit_s']==30),
        total_proposed_points_reference30=sum(v['proposed_points'] for c in cases for v in c.get('limits',[]) if v['reference_limit_s']==30),
        wall_seconds=execution['seconds'])
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    flat=[]
    for r in rows:
        q={k:v for k,v in r.items() if not isinstance(v,(dict,list))}
        if r['target']:q.update({'target_'+k:v for k,v in r['target'].items() if not isinstance(v,(dict,list))})
        flat.append(q)
    with (ROOT/'paired-table.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=sorted({k for r in flat for k in r}));writer.writeheader();writer.writerows(flat)
    figure(summary)
    markdown(summary)


def figure(summary):
    fig,axes=plt.subplots(3,3,figsize=(15,12),layout='constrained')
    width=.3;positions=np.arange(4);settings=[(15,'control'),(15,'addition'),(30,'control'),(30,'addition')]
    for column,case in enumerate(CASES):
        case_summary=next(c for c in summary['cases'] if c['case']==case)
        if not case_summary['completed']:
            for row in range(3):axes[row,column].text(.5,.5,'Incomplete; see failure receipt',ha='center',transform=axes[row,column].transAxes)
            continue
        rr=[r for r in summary['rows'] if r['case']==case]
        phase=axes[0,column];rf=axes[1,column];gps=axes[2,column]
        for offset,arm in ((-width/2,'c0'),(width/2,'fitted_c')):
            selected=[next(r for r in rr if r['reference_limit_s']==limit and r['role']==role and r['arm']==arm) for limit,role in settings]
            phase.bar(positions+offset,[r['final_phase_change_s'] for r in selected],width,color=COLORS[arm],label=LABELS[arm])
            gps_values=[r['position_error_m'] for r in selected]
            bars=gps.bar(positions+offset,gps_values,width,color=COLORS[arm],label=LABELS[arm])
            for b,value in zip(bars,gps_values,strict=True):gps.text(b.get_x()+b.get_width()/2,b.get_height(),f'{value:.0f}',ha='center',va='bottom',fontsize=8)
            additions=[next(r for r in rr if r['reference_limit_s']==limit and r['role']=='addition' and r['arm']==arm) for limit in (15,30)]
            values=[r['target']['RMS_hz'] for r in additions]
            bars=rf.bar(np.arange(2)+offset,values,width,color=COLORS[arm],label=LABELS[arm])
            for b,value in zip(bars,values,strict=True):rf.text(b.get_x()+b.get_width()/2,b.get_height()+4,f'{value:.1f}',ha='center',va='bottom',fontsize=8)
        phase.set(yscale='log',ylim=(1e-8,10),xticks=positions,xticklabels=['Ctl15','Add15','Ctl30','Add30'],
            title=f"{case} · {case_summary['route'].replace('_',' ')}\nNORAD {case_summary['norad']}; {case_summary['target_points']} proposed points")
        phase.axhline(.01,color='#a71930',ls='--',lw=1,label='0.01 s gate')
        phase.legend(fontsize=8,frameon=False,loc='upper right')
        rf.axhline(450,color='#a71930',ls='--',lw=1);rf.set(xticks=[0,1],xticklabels=['15 s reference','30 s reference'],ylim=(0,max(510,max(r['target']['RMS_hz'] for r in rr if r['target'])*1.35)))
        for limit,x in ((15,0),(30,1)):
            qualified=next(v['qualified_recovery_points'] for v in case_summary['limits'] if v['reference_limit_s']==limit)
            rf.text(x,.9, f'{qualified} qualified points',ha='center',transform=rf.get_xaxis_transform(),fontsize=9,
                color='#176b3a' if qualified else '#a71930')
        gps.set(xticks=positions,xticklabels=['Ctl15','Add15','Ctl30','Add30']);gps.set_ylim(0,gps.get_ylim()[1]*1.15)
        for ax in (phase,rf,gps):
            ax.axvline(1.5 if ax!=rf else .5,color='#aaaaaa',lw=.6)
            ax.grid(axis='y',alpha=.15);ax.spines[['top','right']].set_visible(False)
    axes[0,0].set_ylabel('Final phase movement (s; log scale)')
    axes[1,0].set_ylabel('Target profile RMS (Hz; gate ≤450 Hz)')
    axes[2,0].set_ylabel('Known-site position error (m; reporting only)')
    fig.suptitle('RF-selected clipped-phase cases: matched 15 s / 30 s full inclusion',fontsize=17,weight='bold')
    fig.supxlabel('Ctl = matched control; Add = proposed addition • Qualified counts require every gate, including residual structure • Production acceptance: 0 points',fontsize=10)
    for suffix in ('png','pdf'):fig.savefig(ROOT/f'phase-inclusion.{suffix}',dpi=180,bbox_inches='tight')


def markdown(summary):
    lines=['# Full inclusion after numerical phase repair','',
        'Three cases were selected by the frozen RF-only phase panel, without position-error selection. Each uses the same 30 s validated nomination for matched 15 s and 30 s numerical-reference trials, both `c = 0` and fitted-`c` arms, and matched control/addition starts, masks, physical priors, noise policy, and budgets. No gate is relaxed. The two uncalibrated families retain the original ±15 s physical target-phase integration support; only calibration reference coordinates change.','',
        '| Case | Route | Proposed points | Qualified at 15 s | Qualified at 30 s | Wall time / limit |',
        '|---|---|---:|---:|---:|---:|']
    for case in summary['cases']:
        if not case['completed']:
            lines.append(f"| {case['case']} | incomplete | — | — | — | see receipt |");continue
        limits={v['reference_limit_s']:v for v in case['limits']}
        lines.append(f"| {case['case']} | {case['route'].replace('_',' ')} | {case['target_points']} | {limits[15]['qualified_recovery_points']} | {limits[30]['qualified_recovery_points']} | {case['seconds']:.1f} / 590 s |")
    lines += ['',f"**Research-qualified recovery: {summary['total_qualified_points_reference30']} of {summary['total_proposed_points_reference30']} proposed points at 30 s. Production-accepted points: 0.** A qualified count requires both c arms and the matched control/addition to pass all original RF, phase, incumbent-membership, exact-orbit and ownership checks. These are isolated research trials; no persisted production associations changed.",'',
        '| Case / 30 s | Target RMS, c0 / fitted c (Hz) | Position error: control → addition, c0 / fitted c (m) | Remaining failures |',
        '|---|---:|---|---|']
    for case in summary['cases']:
        if not case['completed']:continue
        name=case['case'];r=[v for v in summary['rows'] if v['case']==name and v['reference_limit_s']==30]
        addition=[next(v for v in r if v['role']=='addition' and v['arm']==a) for a in ('c0','fitted_c')]
        controls=[next(v for v in r if v['role']=='control' and v['arm']==a) for a in ('c0','fitted_c')]
        failures=[]
        for v in addition+controls:
            context=f"{v['role']} {LABELS[v['arm']]}"
            if v['final_phase_change_s']>.01:failures.append('phase convergence')
            failures += [key.rsplit('/',1)[-1] for key in v['exact_negative_global_gate_slacks']]
            if v['target'] and v['target'].get('phase_resolution_agreement') is False:failures.append('target phase-grid resolution')
            if v['target'] and v['target'].get('phase_boundary_mass',0)>=.01:failures.append('target phase boundary')
            if v['optimizer_rounds'][-1].get('success') is False:failures.append(context+' final optimizer: '+v['optimizer_rounds'][-1]['message'].strip())
            if v['failed_predictive'] and not v['exact_negative_global_gate_slacks']:failures.append('target/predictive RF gate')
            if v['incumbent_ownership_changes'] or v['control_ownership_changes']:failures.append('incumbent ownership')
        failure_text=', '.join(sorted(set(failures))) or 'none'
        rms=' / '.join(f"{v['target']['RMS_hz']:.1f}" for v in addition)
        gps=' / '.join(f"{c['position_error_m']:.0f} → {a['position_error_m']:.0f}" for c,a in zip(controls,addition,strict=True))
        lines.append(f'| {name} | {rms} | {gps} | {failure_text} |')
    lines += ['',
        'DS26-0044 qualifies under both numerical limits once the same 30 s validated identity is supplied: its full-data calibration fit itself was not clipped. The 30 s change repairs its randomized identity-validation fold, rather than improving full-data inclusion numerics. DS26-0154 passes every 30 s RF, phase and exact-owner replay, including the addition, but the matched fitted-c control ends with L-BFGS-B `ABNORMAL` after 51 final-round evaluations. The unchanged optimizer-success requirement keeps its 30 points unqualified; this is a control numerical-termination blocker, not target RF rejection. DS26-0106 still fails target slope, step and lag-one structure checks despite RMS near 75 Hz.','',
        'Position errors use the known site only after all inference artifacts are sealed. Frequency-fit changes and localization accuracy are reported separately; a lower in-sample score or a qualified association alone does not establish better localization. The qualified DS26-0044 addition changes errors from 3.660 to 3.594 km (`c = 0`) and 3.790 to 3.715 km (fitted `c`); this small reduction does not establish accurate localization. The other two additions worsen error in both arms.','',
        'Each case is limited to 590 s, with one numerical-library thread and three case subprocesses running in parallel. Every fit uses five phase rounds and at most 48 position iterations per round. New-family trials also use the original 240 function-evaluation limit per round and the unchanged local phase-resolution audit. All reference updates, physical target phase boxes, and exact endpoint orbit evaluations are checked against the existing bank; no extrapolation, orbit-bank extension, future TLE, or RF collection is used.','',
        '![Matched reference, target-RMS and reporting-only position comparisons](phase-inclusion.png)','',
        'Evidence: [paired CSV](paired-table.csv), [full summary](summary.json), [execution receipts](execution.json), [batch inference seal](batch_inference_seal.json). Case folders contain matched control/addition JSON, optimizer termination records, exact-orbit/owner audits, bank-domain checks, and source hashes. Three focused tests cover route selection, prohibited extrapolation, and rejection of proposals when any required qualification gate fails.','']
    (ROOT/'SUMMARY.md').write_text('\n'.join(lines))


if __name__=='__main__':main()
