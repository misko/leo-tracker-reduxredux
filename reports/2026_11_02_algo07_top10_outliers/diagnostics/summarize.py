"""Report measured diagnostics without choosing models by GPS error."""
import csv, hashlib, subprocess
from pathlib import Path
import numpy as np
from diagnose import ROOT,INPUT,CASES,ARMS,read,write

def summarize(case):
    out=ROOT/case
    if not (out/'audit.json').exists():return None
    a=read(out/'audit.json');plan=read(out/'fit-plan.json');inv=read(out/'inventory.json');rr=read(out/'track_residuals.json')
    zin=read(INPUT/'inputs'/(case+'.json'));pos=read(INPUT/'position'/case/'result.json');decision=pos['decisions']['72h_30s']
    saved=pos['trials'][decision['trial']]['arms'] if decision['status']=='qualified' else zin['baseline_arms']
    write(out/'published_optimizer_metadata.json',{arm:dict(history=saved[arm].get('history'),phase_stability_required=saved[arm].get('phase_stability_required'),final_phase_change_s=saved[arm].get('final_phase_change_s'),algo06_recovery=decision) for arm in ARMS})
    names=['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]
    trials={name:read(out/(name+'.json')) for name in names if (out/(name+'.json')).exists()}
    lines=[f'# {case}: composed ALGO06 / ALGO07 fallback diagnostics','',
        'These are bounded offline RF diagnostics. Published satellite identities and ownership were not changed. Every family was audited; the four largest summed c-arm local RF omission sensitivities received full position/phase refits. Evaluation GPS was used only after fitting and to draw the explicitly labeled oracle loss grid. Family omission is a diagnostic control, not an approved removal.', '',
        '| Arm | Published position error (m) | Curved residual RMS (Hz) | Native GLRT associated | Phase-reference movement (s) | Base/exact/mixture gates |',
        '|---|---:|---:|---:|---:|---|']
    summary=dict(case=case,arms={},top_rf_influence=plan['selected'],families_audited=plan['total_families'],ablation_families=plan['selected'])
    for arm in ARMS:
        r=a['arms'][arm];g=read(out/('published_gates_'+arm+'.json'));v=inv['arms'][arm]
        lines.append(f"| {arm} | {r['error_m']:.1f} | {r['rms_hz']:.2f} | {v['associated']}/{v['native']} ({v['percent']:.2f}%) | {r['phase_reference_check']['phase_change_s']:.5f} | {g['all_gates_pass']} |")
        rows=[t for t in rr if t['arm']==arm];worst=sorted(rows,key=lambda t:-t['rms_hz'])[:3]
        params=r['parameters'];phase=max(params,key=lambda p:abs(p['phase_standardized']))
        orbit=max(params,key=lambda p:max(abs(np.asarray(p['orbital_standardized'])),default=0))
        group={}
        for t in rows:group.setdefault(f"RX{t['receiver']}-CH{t['channel']}",[]).extend(t['residual_hz'])
        groups={k:dict(n=len(v),mean_hz=float(np.mean(v)),rms_hz=float(np.sqrt(np.mean(np.square(v))))) for k,v in group.items()}
        summary['arms'][arm]=dict(error_m=r['error_m'],rms_hz=r['rms_hz'],objective=r['objective'],native=v,
            phase_reference_change_s=r['phase_reference_check']['phase_change_s'],all_gates_pass=g['all_gates_pass'],minimum_gate_slack=g['minimum_gate_slack'],published_optimizer_last_round=saved[arm].get('history',[None])[-1],
            largest_phase_pull=phase,largest_orbit_pull=orbit,worst_tracks=[{k:t[k] for k in ['component','kind','norad','receiver','channel','n','rms_hz','mean_hz','slope_hz_s','lag1','noise']} for t in worst],receiver_band_residuals=groups,
            trials={tag:dict({k:t[arm].get(k) for k in ['error_m','rms_hz','objective','phase_closed','optimizer_success','all_gates_pass','minimum_gate_slack','fixed_fitted_native_count','intentional_omitted_native_count']},
                proposed_lost_native_count=len(t[arm]['lost_ids']),proposed_added_native_count=len(t[arm]['added_ids']),proposed_reassigned_native_count=len(t[arm]['reassigned_ids']),
                proposed_unrelated_lost_native_count=len(t[arm].get('proposed_unrelated_lost_ids',[])),proposed_reassigned_non_omitted_native_count=len(t[arm].get('proposed_reassigned_non_omitted_ids',[]))) for tag,t in trials.items()})
    lines += ['', 'Matched tests use the same regional bounds, candidate identities, other priors and 15-round / 140 objective-evaluation-per-round budgets in both c arms. Each arm starts at its own saved endpoint; the regional-center test starts both at (0, 0). The phase-SD test doubles the shared prior multiplier. Omission objectives/RMS use reduced observations, so their raw likelihoods are not comparable evidence for deleting a family.', '',
        '| Diagnostic (own published RF start unless center) | c0 error (m) | fitted-c error (m) | c0 / fitted-c RMS (Hz) | Phase closed | Optimizer success | All gates pass |',
        '|---|---:|---:|---|---|---|---|']
    for tag,t in trials.items():
        q=[t[arm] for arm in ARMS]
        lines.append(f"| {tag} | {q[0]['error_m']:.1f} | {q[1]['error_m']:.1f} | {q[0]['rms_hz']:.2f} / {q[1]['rms_hz']:.2f} | {q[0]['phase_closed']} / {q[1]['phase_closed']} | {q[0]['optimizer_success']} / {q[1]['optimizer_success']} | {q[0]['all_gates_pass']} / {q[1]['all_gates_pass']} |")
    lines += ['', 'Only the frozen fitted IDs enter each RMS/objective. The post-fit membership helper also screens graph extensions; those proposals are never adopted in these diagnostics or counted as published coverage. Delta references are the exact composed published incumbent, including accepted ALGO06 additions.', '',
        '| Trial / arm | Fixed fitted native IDs | Intentional omitted family IDs | Proposed unrelated losses | Proposed additions | Proposed non-omitted reassignments |', '|---|---:|---:|---:|---:|---:|']
    for tag,t in trials.items():
        for arm in ARMS:
            q=t[arm]
            lines.append(f"| {tag} / {arm} | {q.get('fixed_fitted_native_count')} | {q.get('intentional_omitted_native_count')} | {len(q.get('proposed_unrelated_lost_ids',[]))} | {len(q['added_ids'])} | {len(q.get('proposed_reassigned_non_omitted_ids',[]))} |")
    common={p.stem:read(p) for p in out.glob('matched_*.json') if not p.stem.endswith(('-c0','-fitted_c'))}
    summary['common_start_controls']={tag:{arm:{k:row.get(k) for k in ['error_m','rms_hz','objective','phase_closed','optimizer_success','all_gates_pass','minimum_gate_slack','fixed_fitted_native_count','intentional_omitted_native_count']} for arm,row in pair.items()} for tag,pair in common.items()}
    if common:
        lines += ['', 'A separate paired control starts both arms at the same published fitted-c RF position and phase reference. Continuation is checked for all ten cases; only three predeclared headline omissions receive this extra start control. This is one shared RF start, not an independent random-start study.', '',
            '| Shared-start diagnostic | c0 / fitted-c error (m) | c0 / fitted-c RMS (Hz) | Phase closed | Optimizer success | Surviving gates pass |', '|---|---|---|---|---|---|']
        for tag,t in sorted(common.items()):
            q=[t[arm] for arm in ARMS]
            lines.append(f"| {tag} | {q[0]['error_m']:.1f} / {q[1]['error_m']:.1f} | {q[0]['rms_hz']:.2f} / {q[1]['rms_hz']:.2f} | {q[0]['phase_closed']} / {q[1]['phase_closed']} | {q[0]['optimizer_success']} / {q[1]['optimizer_success']} | {q[0]['all_gates_pass']} / {q[1]['all_gates_pass']} |")
    lines += ['', 'RF influence is local position sensitivity at the saved solution. It does not establish a wrong satellite identity. Full omission refits provide a nonlinear control; any apparent position gain with failed phase closure, optimizer or gates remains unqualified.', '', '| Family | c0 local displacement (km) | fitted-c local displacement (km) | Native associated points (fitted-c) |', '|---|---:|---:|---:|']
    lookup={arm:{f['norad']:f for f in a['arms'][arm]['family_influence']} for arm in ARMS}
    for n in sorted(lookup['fitted_c'],key=lambda n:-sum(lookup[arm].get(n,{}).get('shift_norm_km',0) for arm in ARMS)):
        lines.append(f"| {n} | {lookup['c0'].get(n,{}).get('shift_norm_km',0):.3f} | {lookup['fitted_c'][n]['shift_norm_km']:.3f} | {lookup['fitted_c'][n]['associated_points']} |")
    for arm in ARMS:
        s=summary['arms'][arm];phase=s['largest_phase_pull'];orb=s['largest_orbit_pull'];worst=s['worst_tracks'][0]
        lines += ['',f"{arm}: the largest phase standardized coefficient is family {phase['norad']} ({phase['phase_standardized']:.3f} in original prior units; adaptive precision {phase['phase_prior_precision']:.3g}). The largest orbital coefficient magnitude is family {orb['norad']} ({max(abs(np.asarray(orb['orbital_standardized'])),default=0):.3f}). The highest-RMS retained track is {worst['component']} ({worst['kind']}, {worst['rms_hz']:.2f} Hz, mean {worst['mean_hz']:.2f} Hz, slope {worst['slope_hz_s']:.2f} Hz/s). These fitted nuisance quantities are not independent orbit-error measurements."]
    longest=inv['longest_unassociated'][0] if inv['longest_unassociated'] else None
    if longest:lines += ['',f"Longest native graph unassociated source after splitting gaps >5 s: {longest['component']}, RX{longest['receiver']} CH{longest['channel']}, {longest['n']} unique points spanning {longest['span_s']:.2f} s. This duration rank is independent of fit-error ranking."]
    lines += ['', 'Receiver/band residual structure is tabulated numerically in summary.json and visualized below. Attribution to receiver calibration versus satellite orbit remains unresolved by these same-data diagnostics; independent family/receiver transfer and causal-versus-later TLE comparisons are required. Candidate search and identity conclusions are reported separately by the orbit investigation.', '',
        '![Native GLRT context](native_context.png)', '![GLRT score context](glrt_score.png)', '![Matched ablations](ablations.png)', '![Receiver/family residuals](residual_by_receiver_family.png)', '![Nuisance pulls](nuisance_pulls.png)', '![Oracle loss grid](oracle_loss_grid.png)', '',
        'Exact per-gate dimensionless margins, exact-orbit linearization differences, native owner changes and mixture gate witnesses are saved in published_gates_*.json and each trial arm JSON. Track residual arrays and native observation IDs are saved in track_residuals.json. No identities, priors or model complexity were selected using the evaluation site.']
    (out/'report.md').write_text('\n'.join(lines)+'\n');write(out/'summary.json',summary);return summary

if __name__=='__main__':
    results=[s for case in CASES if (s:=summarize(case)) is not None];write(ROOT/'summaries.json',results)
    controls=[]
    for s in results:
        for tag,pair in s['common_start_controls'].items():
            for arm in ARMS:
                r=pair[arm];controls.append(dict(case=s['case'],trial=tag,arm=arm,error_m=r['error_m'],rms_hz=r['rms_hz'],phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],all_gates_pass=r['all_gates_pass']))
    if controls:
        with (ROOT/'common_start_controls.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=controls[0]);w.writeheader();w.writerows(controls)
    source=['tools/algo07_science/engine.py','tools/algo07_science/diagnose.py','tools/algo07_science/previous.py','tools/algo06_science/common.py','tools/algo06_science/position.py']
    source += [str(p.relative_to(Path.cwd())) for p in ROOT.glob('*.py')]
    manifest=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),source_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in source},
        cases=CASES,baseline='actual composed ALGO06 72h_30s guarded policy reconstructed by algo07_science.engine.load_case; ALGO07 fallback requires fresh evaluation confirmation',
        priors='inherited matched; phase_sigma_x2 changes inherited multiplier only',observations='frozen published native IDs, exact composed owners; omission controls explicitly remove one entire family',
        candidate_policy='baseline identities frozen; full family influence audit, top-four RF-influence ablation coverage',phase_rounds=15,maxfun_per_round=140,maxiter_per_round=35,
        per_case_time_cap_s=1200,max_parallel_processes=6,python='/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python',pythonpath='src:tools',blas_threads=1,
        regional_prior_km=[-12.5,12.5],truth_policy='GPS only post-fit evaluation and separately labeled fixed-association 7x7 oracle diagnostic',
        no_new_rf_collection=True,no_production_ownership_changes=True,command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:tools python diagnostics/diagnose.py CASE',
        limitations=['same-data omission sensitivity is not satellite identity validation','omission likelihoods use reduced observations','conditional residual scales differ from predictive/raw family residuals; scopes labeled','oracle loss grid freezes phase references and associations'])
    write(ROOT/'run_manifest.json',manifest)
