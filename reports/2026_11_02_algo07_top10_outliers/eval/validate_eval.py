"""Post-run artifact consistency checks for retrospective ALGO07 replay."""
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('evaluation_report',HERE/'run_eval.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    from algo07_history import collect_private
    from algo07_production_worker import verify_release
    verify_release()
    freeze=m.read(HERE/'code-freeze.json');code=freeze['sha256']
    unchanged=all(m.sha(Path(p) if p.startswith('/') else m.REPO/p)==s for p,s in code.items())
    rows=[]
    for case in freeze['cases']:
        root=HERE/case;inp=root/'input';out=root/'output';summary=m.read(root/'summary.json')
        protocol=m.read(out/'protocol.json');baseline=protocol['baselines']['SCAN']
        result_path=out/'SCAN/worker_result.json'
        result=m.read(result_path) if result_path.exists() else m.read(root/'supervisor_fallback.json')
        exports=[]
        for path in sorted((out/'SCAN').rglob('export.json')):
            saved=m.read(path)
            exports.append(dict(path=str(path.relative_to(root)),
                exact_full_history_bank_replay=saved['export']==collect_private(inp/'history-bank.json',saved['request'])))
        public=m.read(out/'SCAN/public_replay.json')
        accepted=next((r for r in result.get('records',[]) if r['name']==result.get('selected')),None)
        paired=(not accepted or all(accepted['pair'][a]['qualified']
             and accepted['pair'][a]['native_ids_sha256']==accepted['control'][a]['native_ids_sha256']
             and accepted['gains'][a]>0 for a in ('c0','fitted_c')))
        history=m.read(inp/'history-bank.json');z=m.read(inp/'inputs/SCAN.json')
        row=dict(case=case,execution_status=summary['execution_status'],selected=summary['selected'],
            saved_research_preflight=public.get('saved_research_owner_maps_equal') is True and public.get('saved_research_objectives_equal') is True,
            public_terminal_available=public['public_terminal_available'],
            input_hashes_unchanged=all(m.sha(inp/p)==s for p,s in protocol['input_sha256'].items()),
            code_hashes_match_protocol=protocol['source_sha256']==code,
            history_cutoff_matches=history['cutoff_utc_ns']==z['scan_receipt']['cutoff_utc_ns'],
            history_full_causal_inventory=m.read(root/'history-export.json')['scope']=='All causal archive satellite versions; unrestricted candidate requests',
            history_requests=exports,
            final_exact_fallback=(result['final']==baseline) if result['selected'] is None else None,
            paired_qualified_native_matched=paired,
            within_bound=summary['seconds']<=1206,
            process_succeeded=summary['subprocess_returncode']==0)
        row['passed']=bool(row['saved_research_preflight'] and not row['public_terminal_available']
            and row['input_hashes_unchanged'] and row['code_hashes_match_protocol'] and row['history_cutoff_matches']
            and row['history_full_causal_inventory'] and all(r['exact_full_history_bank_replay'] for r in exports)
            and row['final_exact_fallback'] is not False and paired and row['within_bound'] and row['process_succeeded'])
        rows.append(row)
    value=dict(passed=unchanged and all(r['passed'] for r in rows),code_unchanged=unchanged,
        release_manifest_verified=True,case_count=len(rows),rows=rows,
        limitation='Saved research ALGO06 authority; does not validate live public terminals or a production job')
    m.write(HERE/'validation.json',value)
    print(json.dumps(value,indent=2))
    if not value['passed']: raise SystemExit('Evaluation artifact validation failed')


if __name__=='__main__':main()
