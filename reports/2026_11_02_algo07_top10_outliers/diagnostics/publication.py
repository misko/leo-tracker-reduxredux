"""Prepare small review evidence and an explicit publication allowlist."""
import hashlib
from pathlib import Path
from diagnose import ROOT,CASES,ARMS,read,write

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def gate_row(tag,arm,row,baseline=None):
    g=row if baseline is None else baseline
    exact=[dict(norad=v['norad'],all_pass=v['all_pass'],minimum_slack=v['minimum_slack'],
        maximum_linearization_difference_hz=v['maximum_linearization_difference_hz'],failed_gate_names=sorted(v['failed'])) for v in g['exact_orbit_checks']]
    return dict(trial=tag,arm=arm,error_m=row['error_m'],objective=row['objective'],curved_conditional_rms_hz=row['rms_hz'],
        phase_closed=row.get('phase_closed',row.get('phase_reference_check',{}).get('phase_change_s',1e9)<=.01),optimizer_success=row.get('optimizer_success'),
        phase_reference_movement_s=row.get('phase_reference_check',{}).get('phase_change_s',row.get('history',[{}])[-1].get('phase_change_s')),
        all_base_gates_pass=g['all_base_gates_pass'],minimum_base_gate_slack=g['minimum_gate_slack'],failed_base_gates=g['failed_gates'],
        exact_checks=exact,exact_scope=g['exact_check_scope'],mixture_gates_pass=g['mixture_gates_pass'],all_surviving_gates_pass=g['all_gates_pass'],
        active_curved_points=row.get('active_points'),fixed_fitted_native_count=row.get('fixed_fitted_native_count',g.get('published_owners_count')),
        intentional_omitted_native_count=row.get('intentional_omitted_native_count',0),proposed_lost_native_count=len(g['lost_ids']),proposed_added_native_count=len(g['added_ids']),
        proposed_reassigned_native_count=len(g['reassigned_ids']),proposed_unrelated_lost_native_count=len(row.get('proposed_unrelated_lost_ids',g['lost_ids'])),
        proposed_non_omitted_reassigned_native_count=len(row.get('proposed_reassigned_non_omitted_ids',g['reassigned_ids'])),membership_screen_adopted=False,
        phase_optimizer_history=row.get('history'),full_detail_local_path=str(ROOT/row.get('_detail_file','')))

def main():
    selected=set(ROOT.glob('*.py'))
    for name in ['run_manifest.json','validation.json','tests.txt','localization_trials.csv','localization_trials.json','common_start_controls.csv','summaries.json']:
        selected.add(ROOT/name)
    for case in CASES:
        out=ROOT/case;aud=read(out/'audit.json');rows=[]
        for arm in ARMS:
            baseline=read(out/('published_gates_'+arm+'.json'));r=dict(aud['arms'][arm],_detail_file=case+'/published_gates_'+arm+'.json')
            rows.append(gate_row('published',arm,r,baseline))
        plan=read(out/'fit-plan.json');tags=['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]
        tags += [p.name[:-len('-c0.json')] for p in out.glob('matched_*-c0.json')]
        for tag in tags:
            for arm in ARMS:
                r=read(out/(tag+'-'+arm+'.json'));r['_detail_file']=case+'/'+tag+'-'+arm+'.json';rows.append(gate_row(tag,arm,r))
        write(out/'gate_summary.json',dict(rows=rows,gate_units='dimensionless deployed gate slacks; pass iff >=0; full definitions in inherited source',
            note='Exact checks replace one named family orbit, keep coefficients fixed, replay every surviving gate; failed_gate_names may belong to another family. Full exact failed numeric margins remain local.'))
        keep=['report.md','summary.json','audit.json','fit-plan.json','replay.json','inventory.json','native_evidence_validation.json',
            'published_optimizer_metadata.json','matched-start-plan.json','completion.json','matched-completion.json','gate_summary.json']
        selected.update(out/name for name in keep);selected.update(out.glob('*.png'))
    for case in CASES:
        out=ROOT/case;local=[p for p in out.iterdir() if p.is_file() and p not in selected and p.name!='local_artifact_manifest.json']
        write(out/'local_artifact_manifest.json',dict(artifacts=[dict(local_path=str(p),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(local)],
            scope='Local detailed arrays, native IDs/owners and full gate witnesses retained for reproduction; not duplicated in lean Git publication'))
        selected.add(out/'local_artifact_manifest.json')
    selected.add(ROOT/'publication_allowlist.txt')
    selected.add(ROOT/'publication_manifest.json')
    names=sorted(str(p.relative_to(Path.cwd())) for p in selected)
    (ROOT/'publication_allowlist.txt').write_text('\n'.join(names)+'\n')
    artifacts=[dict(path=str(p.relative_to(Path.cwd())),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(selected) if p.exists() and p.name not in ['publication_manifest.json']]
    allowlist=[dict(path=str(Path(a['path']).relative_to(ROOT.parent.relative_to(Path.cwd()))),bytes=a['bytes'],sha256=a['sha256']) for a in artifacts]
    write(ROOT/'publication_manifest.json',dict(allowlist=allowlist,files=artifacts,total_bytes=sum(a['bytes'] for a in artifacts),
        scope='diagnostics only; complete figure/MD/table/test/manifest and compact-gate evidence; excludes dense NPZ/raw residuals/duplicated full trial owner maps'))
    print(len(selected),'files',round(sum(a['bytes'] for a in artifacts)/1e6,2),'MB',flush=True)

if __name__=='__main__':main()
