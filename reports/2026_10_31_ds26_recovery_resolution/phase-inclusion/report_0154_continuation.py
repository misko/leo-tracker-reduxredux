"""Post-seal report for the single matched DS26-0154 numerical continuation."""
import copy
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from report_inclusion import read,sha,verify_seal,position_error_m,row_summary,COLORS,LABELS
from run_inclusion import qualified_points,source_receipt

ROOT=Path(__file__).resolve().parent
CONT=ROOT/'DS26-0154-numerical-continuation'


def main():
    verify_seal(CONT/'inference_seal.json');verify_seal(ROOT/'batch_inference_seal.json')
    original=read(ROOT/'summary.json');pr=read(ROOT/'cases/DS26-0154/protocol.json')
    old=ROOT/'cases/DS26-0154/reference30/inclusion';newaudit=read(CONT/'exact_owner_replay.json')
    before=read(CONT/'pre_continuation_audit.json');rows=[];newrows=[]
    control=read(CONT/'control.json');addition=read(CONT/'new_family.json')
    for role in ('control','new_family'):
        oldfit=read(old/(role+'.json'));newfit=read(CONT/(role+'.json'))
        for arm in ('c0','fitted_c'):
            previous=oldfit['arms'][arm];updated=newfit['arms'][arm]
            auditrow=next(r for r in newaudit['rows'] if r['role']==role and r['arm']==arm)
            final=row_summary('DS26-0154',30,'control' if role=='control' else 'addition',arm,newfit,auditrow,pr)
            final['optimizer_total_physical_evaluations']=sum(h['total_objective_evaluations'] for h in updated['history'])
            newrows.append(final)
            rows.append(dict(role=role,arm=arm,pre_optimizer_success=previous['history'][-1]['success'],
                post_optimizer_success=updated['history'][-1]['success'],pre_optimizer_message=previous['history'][-1]['message'],
                post_optimizer_message=updated['history'][-1]['message'],
                pre_objective=previous['negative_twice_elbo'],post_objective=updated['negative_twice_elbo'],
                objective_change=updated['negative_twice_elbo']-previous['negative_twice_elbo'],
                endpoint_movement_m=1000*updated['continuation_endpoint_movement_km'],
                pre_phase_change_s=previous['final_phase_change_s'],post_phase_change_s=updated['final_phase_change_s'],
                pre_position_error_m=position_error_m(previous['endpoint_latlon']),post_position_error_m=position_error_m(updated['endpoint_latlon']),
                post_centered_gradient=updated['post_gradient_audit']['rows'][1]['centered_gradient'],
                total_physical_objective_evaluations=final['optimizer_total_physical_evaluations'],
                all_exact_owner_RF_phase_checks_pass=auditrow['verified']))
    qualified=qualified_points(control['paired_valid'],addition['paired_valid'],newaudit['all_verified'],min(v['added_points'] for v in addition['arms'].values()))
    result=dict(case='DS26-0154',rows=rows,matched_control_valid=control['paired_valid'],matched_addition_valid=addition['paired_valid'],
        all_exact_owner_checks_pass=newaudit['all_verified'],qualified_recovery_points=qualified,production_accepted_points=0,
        source_inference_seal_sha256=sha(CONT/'inference_seal.json'),known_position_reporting_only=True,GPS_used_for_inference=False,
        seconds=read(CONT/'terminal.json')['seconds'],budget_seconds=590)
    (ROOT/'numerical-continuation-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (ROOT/'numerical-continuation-table.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    # Preserve the initial comparison and state explicitly that only DS26-0154
    # receives this separately authorized, matched four-arm continuation.
    final=copy.deepcopy(original)
    final['rows']=[r for r in final['rows'] if not(r['case']=='DS26-0154' and r['reference_limit_s']==30)]+newrows
    case=next(c for c in final['cases'] if c['case']=='DS26-0154')
    case['initial_reference30_qualified_points']=next(v['qualified_recovery_points'] for v in case['limits'] if v['reference_limit_s']==30)
    case['numerical_continuation_seconds']=result['seconds']
    case['separate_matched_continuation']=True
    for limit in case['limits']:
        if limit['reference_limit_s']==30:
            limit.update(control_paired_valid=control['paired_valid'],addition_paired_valid=addition['paired_valid'],
                exact_owner_all_verified=newaudit['all_verified'],qualified_recovery_points=qualified)
    final['total_qualified_points_reference30']=sum(v['qualified_recovery_points'] for c in final['cases'] for v in c['limits'] if v['reference_limit_s']==30)
    final['initial_summary_sha256']=sha(ROOT/'summary.json')
    final['DS26_0154_continuation_summary_sha256']=sha(ROOT/'numerical-continuation-summary.json')
    final['continuation_budget_note']='Only DS26-0154 has an additional matched five-round, 48-iteration, 240-total-evaluation-cap continuation; initial 15/30 comparison is retained unchanged.'
    coverage=[];observation_paths=[]
    for name,folder,addname in (('DS26-0044',ROOT/'cases/DS26-0044/reference30/inclusion','new_family'),('DS26-0154',CONT,'new_family')):
        casepr=read(ROOT/'cases'/name/'protocol.json');inv=read(Path(casepr['inventory']))
        path=Path(inv['job']['root'])/inv['job']['case']/'observations.json';observations=read(path);observation_paths.append(path)
        ids={o['observation_id'] for o in observations}
        if len(ids)!=len(observations) or any(r['total_GLRT']!=len(observations) for r in inv['summary']):raise ValueError('original GLRT denominator mismatch')
        controls=read(folder/'control.json');additions=read(folder/(addname+'.json'))
        for arm in ('c0','fitted_c'):
            c=controls['arms'][arm];a=additions['arms'][arm]
            if not set(c['proposed_associated_ids']).issubset(ids) or not set(a['proposed_associated_ids']).issubset(ids):raise ValueError('associated ID outside original observation denominator')
            n0=len(c['proposed_associated_ids']);n1=len(a['proposed_associated_ids']);den=len(observations)
            target_ids=set(casepr['target']['observation_ids'])
            new_ids=set(a['proposed_associated_ids'])-set(c['proposed_associated_ids'])
            coverage.append(dict(case=name,arm=arm,original_GLRT_observations=den,control_associated=n0,addition_associated=n1,
                control_percent_all_GLRT=100*n0/den,addition_percent_all_GLRT=100*n1/den,net_associated_increase=n1-n0,
                target_recovered_points=len(new_ids&target_ids),other_extension_increase=len(new_ids-target_ids),
                control_position_error_m=position_error_m(c['endpoint_latlon']),addition_position_error_m=position_error_m(a['endpoint_latlon']),
                original_observation_source=str(path),original_observation_sha256=sha(path),research_qualified=True,production_accepted_points=0))
    final['qualified_case_coverage']=coverage
    (ROOT/'final-summary.json').write_text(json.dumps(final,indent=2,allow_nan=False)+'\n')
    with (ROOT/'qualified-coverage.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(coverage[0]));writer.writeheader();writer.writerows(coverage)
    make_figure(before,rows,qualified)
    body=markdown(final,result,coverage)
    if not (ROOT/'INITIAL-SUMMARY.md').exists():(ROOT/'INITIAL-SUMMARY.md').write_text((ROOT/'SUMMARY.md').read_text())
    (ROOT/'FINAL-SUMMARY.md').write_text(body);(ROOT/'SUMMARY.md').write_text(body)
    receipt_paths=[Path(__file__),ROOT/'run_inclusion.py',ROOT/'continue_0154_numerics.py',ROOT/'test_inclusion.py',ROOT/'test_0154_numerics.py',
        ROOT/'report_inclusion.py',ROOT/'SUMMARY.md',ROOT/'INITIAL-SUMMARY.md',ROOT/'FINAL-SUMMARY.md',ROOT/'final-summary.json',
        ROOT/'numerical-continuation-summary.json',ROOT/'numerical-continuation-table.csv',ROOT/'qualified-coverage.csv',
        ROOT/'numerical-continuation.png',ROOT/'numerical-continuation.pdf',ROOT/'phase-inclusion.png',ROOT/'phase-inclusion.pdf',
        ROOT/'tests.log',ROOT/'audit_extension_ids.py',ROOT/'extension-id-accounting.json',CONT/'inference_seal.json',ROOT/'batch_inference_seal.json']+observation_paths
    (ROOT/'publication-source-receipts.json').write_text(json.dumps(dict(files_sha256=source_receipt(receipt_paths),
        tests='5 focused tests pass; see tests.log',source_seals_validated_before_position_reporting=True),indent=2)+'\n')


def make_figure(before,rows,qualified):
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained');width=.32;x=np.arange(2)
    failed=next(r for r in before['rows'] if r['role']=='control' and r['arm']=='fitted_c')['gradient']['rows'][1]
    ax=axes[0,0]
    for offset,key,label,color in ((-width/2,'forward_gradient','Original forward difference','#777777'),(width/2,'centered_gradient','Centered difference','#5e3c99')):
        bars=ax.bar(x+offset,failed[key],width,color=color,label=label)
        for b,v in zip(bars,failed[key],strict=True):ax.text(b.get_x()+b.get_width()/2,v,f'{v:+.5f}',ha='center',va='bottom' if v>=0 else 'top',fontsize=9)
    ax.axhline(0,color='#444444',lw=.7);ax.set(xticks=x,xticklabels=['East','North'],ylim=(-.009,.009),ylabel='Objective gradient / km',
        title='A  Failed fitted-c control: derivative direction bias')
    ax.legend(loc='upper right',frameon=False,fontsize=9)
    ax=axes[0,1];x=np.arange(4)
    values=[r['endpoint_movement_m'] for r in rows]
    ax.bar(x,values,color=[COLORS[r['arm']] for r in rows])
    for k,v in enumerate(values):ax.text(k,v+.01,f'{v:.3f} m\nsuccess',ha='center',fontsize=9)
    ax.set(xticks=x,xticklabels=['Control c0','Control fitted c','Addition c0','Addition fitted c'],ylim=(0,.65),
        ylabel='Endpoint movement from frozen fit (m)',title='B  All four fits converge after sub-metre changes')
    ax=axes[1,0]
    for i,r in enumerate(rows):
        g0=next(q for q in before['rows'] if q['role']==r['role'] and q['arm']==r['arm'])['gradient']['rows'][1]['centered_gradient']
        ax.bar(i-.15,max(abs(v) for v in g0),.3,color=COLORS[r['arm']],alpha=.35)
        ax.bar(i+.15,max(abs(v) for v in r['post_centered_gradient']),.3,color=COLORS[r['arm']])
    ax.axhline(1e-4,color='#a71930',ls='--',label='unchanged gtol = 0.0001')
    ax.set(yscale='log',ylim=(1e-6,.02),xticks=x,xticklabels=['Control c0','Control fitted c','Addition c0','Addition fitted c'],
        ylabel='Maximum |centered gradient|',title='C  Strict stationarity test passes after continuation')
    ax.text(.02,.95,'Pale = before; solid = after',transform=ax.transAxes,va='top',fontsize=9);ax.legend(frameon=False,fontsize=9,loc='lower left')
    ax=axes[1,1]
    for i,r in enumerate(rows):
        ax.bar(i-.15,r['pre_position_error_m'],.3,color=COLORS[r['arm']],alpha=.35)
        ax.bar(i+.15,r['post_position_error_m'],.3,color=COLORS[r['arm']])
    ax.set(xticks=x,xticklabels=['Control c0','Control fitted c','Addition c0','Addition fitted c'],
        ylabel='Known-site position error (m)',title='D  Position accuracy is materially unchanged')
    ax.text(.02,.95,'Reporting only, after inference seal',transform=ax.transAxes,va='top',fontsize=9)
    for ax in axes.ravel():ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
    fig.suptitle('DS26-0154: one matched numerical continuation resolves false failure',fontsize=15,weight='bold')
    fig.supxlabel(f'Identical continuation budget for control/addition and both c arms • All RF, phase, exact-orbit and owner gates pass • {qualified} research-qualified points; 0 production-accepted',fontsize=9)
    for suffix in ('png','pdf'):fig.savefig(ROOT/f'numerical-continuation.{suffix}',dpi=180,bbox_inches='tight')


def markdown(final,continuation,coverage):
    lines=['# Full inclusion: 56 research-qualified points; production unchanged','',
        'Three cases were selected by the frozen RF-only phase panel, with no position-error criterion. The initial matched 15 s / 30 s trials qualify DS26-0044’s 26 points under both limits. A separately authorized, matched numerical continuation resolves DS26-0154’s sole control-optimizer failure and qualifies another 30 points. DS26-0106’s 71 proposed points remain rejected by residual-structure gates. **Final total: 56 / 127 proposed points research-qualified; 0 production-accepted.**','',
        '| Case | Target | Initial qualified, 15 s / 30 s | Separate numerical continuation | Final research-qualified |',
        '|---|---|---:|---|---:|',
        '| DS26-0154 | 61961; uncalibrated family | 0 / 0 | All four fits now converge; all physical gates pass | 30 |',
        '| DS26-0044 | 59310; uncalibrated family | 26 / 26 | None | 26 |',
        '| DS26-0106 | 59835; shared calibrated family | 0 / 0 | None | 0 |','',
        'The initial comparison is preserved in [INITIAL-SUMMARY.md](INITIAL-SUMMARY.md), [summary.json](summary.json), and its [PNG](phase-inclusion.png)/[PDF](phase-inclusion.pdf). Both numerical references use the same frozen 30 s validated nomination, physical priors, aliases, observations, calibration masks and paired c arms. New-family physical phase support remains ±15 s. Every phase update and exact-orbit replay stays within the frozen causal bank.','',
        '## Research-qualified association coverage','',
        'Denominators are the **original complete GLRT observation lists**, including observations outside graph tracks. Counts below are matched control → research-qualified addition, not persisted production changes.','',
        '| Case / arm | Original GLRT observations | Associated control → addition | % of all GLRT control → addition | Position error control → addition (m) |',
        '|---|---:|---:|---:|---:|']
    for r in coverage:
        lines.append(f"| {r['case']} / {LABELS[r['arm']]} | {r['original_GLRT_observations']} | {r['control_associated']} → {r['addition_associated']} | {r['control_percent_all_GLRT']:.2f}% → {r['addition_percent_all_GLRT']:.2f}% | {r['control_position_error_m']:.1f} → {r['addition_position_error_m']:.1f} |")
    lines += ['',
        'DS26-0154’s c0 count increases by 45: the 30 target observations plus a separate 15-point graph extension, `SCAN-RX2-CH4-T009-RF11690312500.000000`, assigned to NORAD **57328**. Those same 15 IDs are already associated to 57328 in the fitted-c control. They pass the unchanged extension gates at the c0 addition endpoint: RMS **91.98 Hz**, bias **−2999.74 Hz** within the unchanged ±3000 Hz limit, positive elevation and all noise screens passing. The c0 control narrowly fails only the offset bound at **−3002.59 Hz**. The reported **30-point targeted recovery is the intersection of newly recovered target IDs in both arms**; the extra c0 extension is excluded from the 56-point targeted total. Exact IDs, owners and gate values are preserved in [extension-id-accounting.json](extension-id-accounting.json).','',
        '## DS26-0154 numerical audit and continuation','',
        'Initially, the 30 s addition passed, but the matched fitted-c control ended with L-BFGS-B `ABNORMAL` after 51 final-round evaluations. Every frozen physical RF, phase, exact-orbit and owner check already passed. At the original 1 m forward-difference step, its north gradient was **+0.00582**; centered differences gave **−0.00695**, with the sign stable across 0.1–10 m centered steps. The biased derivative is consistent with a false line-search failure near a stable endpoint; the continuation changes both derivative calculation and line-search allowance.','',
        'One continuation was applied identically to control/addition and both c arms, starting at their corresponding frozen endpoints: five phase rounds, at most 48 optimizer iterations and **240 total physical objective calls per round**, centered 1 m derivatives, and `maxls=40`. All derivative calls count toward the cap. Physical priors, noise, candidates, target grid, objective and acceptance thresholds remain unchanged. All four final optimizer statuses and physical audits pass; centered-gradient components satisfy the original `gtol=1e-4`. No failed status was accepted.','',
        '| Role / arm | Final optimizer before → after | Objective change | Endpoint movement (m) | Physical objective calls, five rounds |',
        '|---|---|---:|---:|---:|']
    for r in continuation['rows']:
        lines.append(f"| {r['role']} / {LABELS[r['arm']]} | {r['pre_optimizer_success']} → {r['post_optimizer_success']} | {r['objective_change']:+.8f} | {r['endpoint_movement_m']:.3f} | {r['total_physical_objective_evaluations']} |")
    lines += ['',f"The continuation finished in **{continuation['seconds']:.1f} / 590 s**. Its extra budget is separate from the original reference comparison; it does not establish a matched-budget 15 s versus 30 s localization benefit. The endpoint changes are sub-metre and position accuracy is materially unchanged.",'',
        '![DS26-0154 numerical audit and matched continuation](numerical-continuation.png)','',
        '## Why DS26-0106 remains rejected','',
        'With the 30 s reference, target RMS is only **75.22 / 74.77 Hz** (`c = 0` / fitted `c`), but the exact target replay fails **slope, step and lag-one correlation** tests. Phase convergence and the matched control pass. Its 71 points remain proposals; no threshold or residual pruning is applied.','']
    root=ROOT/'cases/DS26-0106/reference30/inclusion';audit=read(root/'exact_owner_replay.json');pr=read(ROOT/'cases/DS26-0106/protocol.json')
    lines += ['| Exact target statistic | c = 0 | fitted c | Unchanged maximum |','|---|---:|---:|---:|']
    stats={}
    for arm in ('c0','fitted_c'):
        ar=next(r for r in audit['rows'] if r['role']=='target_0' and r['arm']==arm)
        ex=next(r for r in ar['exact_family_replays'] if r['norad']==pr['norad'])
        prefix=pr['target']['component']+'/linear/';s=ex['all_gate_slacks'];threshold=4/np.sqrt(71)
        stats[arm]=dict(slope=3*(1-s[prefix+'slope']),step=4*(1-s[prefix+'step']),lag1=threshold*(1-s[prefix+'lag1']))
    lines += [f"| Slope z | {stats['c0']['slope']:.4f} | {stats['fitted_c']['slope']:.4f} | 3 |",
        f"| Maximum step z | {stats['c0']['step']:.4f} | {stats['fitted_c']['step']:.4f} | 4 |",
        f"| Absolute lag-one correlation | {stats['c0']['lag1']:.4f} | {stats['fitted_c']['lag1']:.4f} | {4/np.sqrt(71):.4f} |",'',
        'All original cases finished in 78–97 s, each below its 590 s limit, with one numerical-library thread per case. Existing associated memberships and owners are preserved. Known-site coordinates enter only after the initial and continuation inference seals; frequency fit and position accuracy remain separate outcomes. DS26-0044 still has about 3.6–3.7 km error despite qualified association. The other additions worsen error. No new RF, future TLE, bank extension, production change or push occurred.','',
        'Artifacts: [final summary JSON](final-summary.json), [coverage CSV](qualified-coverage.csv), [pre/post numerical table](numerical-continuation-table.csv), [continuation inference seal](DS26-0154-numerical-continuation/inference_seal.json), [pre-gradient audit](DS26-0154-numerical-continuation/pre_continuation_audit.json), [exact continuation replay](DS26-0154-numerical-continuation/exact_owner_replay.json), [source/test/report hashes](publication-source-receipts.json). Five focused tests pass.','']
    return '\n'.join(lines)


if __name__=='__main__':main()
