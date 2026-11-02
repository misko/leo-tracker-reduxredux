"""Compact postfit diagnostics; never called by inference or selection."""
import csv
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('evaluation_report', HERE/'run_eval.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def read(path): return json.loads(path.read_text())


def main():
    rows=[]
    for summary_path in sorted(HERE.glob('DS26-*/summary.json')):
        summary=read(summary_path);case=summary['source_case'];out=summary_path.parent/'output/SCAN'
        result=read(out/'worker_result.json') if (out/'worker_result.json').exists() else {}
        candidates=[]
        for decision_path in sorted(out.glob('*/*-combined/decision.json')):
            decision=read(decision_path);fits=read(decision_path.parent/'fits.json')
            candidates.append(dict(name=decision['name'],accepted=decision['accepted'],
                gains=decision['gains'],bounds=decision['bounds'],
                matched_published_objectives=decision.get('matched_published_objectives'),
                starts=[dict(arm=f['arm'],start=f['start'],
                    **{k:f.get(k) for k in ('status','qualified','reason','objective','rms_hz','phase_closed','optimizer_success','all_gates_pass','failed_gates','mixture_phase_interior')},
                    error_m=module.report_endpoint(f)['error_m'] if 'x' in f else None,
                    phase_boundary_masses=f.get('phase_boundary_masses'),
                    unexpected_reassigned_ids_count=len(f.get('unexpected_reassigned_ids',[])),
                    lost_ids_count=len(f.get('lost_ids',[])),
                    optimizer_messages=[h.get('message') for h in f.get('history',[])]) for f in fits]))
        row=dict(case=case,execution_status=summary['execution_status'],selected=summary.get('selected'),
            seconds=summary.get('seconds'),exact_fallback_equal=summary.get('exact_fallback_equal'),
            before=summary.get('baseline'),after=summary.get('final'),
            targets=summary.get('targets'),ranking=(summary.get('trigger') or {}).get('ranking'),
            screens=summary.get('screens'),review=result.get('review'),candidate_fits=candidates,
            history=result.get('history'),propagation_failures=result.get('propagation_failures'),
            failure=summary.get('supervisor_failure'),replay=read(out/'replay.json') if (out/'replay.json').exists() else None)
        rows.append(row)
    rows.sort(key=lambda r:-(r.get('after') or {}).get('fitted_c',{}).get('error_m',-1))
    for rank,row in enumerate(rows,1): row['rank_within_twelve']=rank
    module.write(HERE/'diagnostics.json',dict(research_only=True,public_terminal_available=False,
        evaluation_coordinate=[37.849061591561885,-122.48574968092912],
        reporting_radius_m=6371000,coordinate_used_only_after_selection=True,rows=rows))
    with (HERE/'diagnostics.csv').open('w',newline='') as stream:
        fields=['rank_within_twelve','case','execution_status','selected','seconds','exact_fallback_equal','arm',
            'before_error_m','after_error_m','before_associated','after_associated','before_objective','after_objective',
            'targets','screen_rejections','review_rejections']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            rejects=[h['name']+':'+','.join(h['rejection_reasons']) for s in row.get('screens') or [] for h in s['proposals'] if h['rejection_reasons']]
            reviews=[r['name']+':'+','.join(r['reasons']) for r in row.get('review') or [] if not r['eligible']]
            for arm,before in (row.get('before') or {}).items():
                after=row['after'][arm]
                writer.writerow(dict(**{k:row[k] for k in fields[:6]},arm=arm,
                    before_error_m=before['error_m'],after_error_m=after['error_m'],
                    before_associated=before['associated'],after_associated=after['associated'],
                    before_objective=before['objective'],after_objective=after['objective'],
                    targets=json.dumps(row['targets']),screen_rejections='; '.join(rejects),review_rejections='; '.join(reviews)))
    print(json.dumps([dict(case=r['case'],status=r['execution_status'],selected=r['selected'],
        before_m=r['before']['fitted_c']['error_m'],after_m=r['after']['fitted_c']['error_m']) for r in rows],indent=2))


if __name__=='__main__': main()
