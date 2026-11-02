"""Postfit RF-only coverage, cost and cell-status summary."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
LABELS=('A','A+B','A+B+C')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def started(row,folder):
    return bool(row['status']!='total_deadline_fallback' or 'wall_seconds' in row
                or any(key in row for key in ('baseline_replay','reconstruction','numerical_trigger_diagnostics','traceback'))
                or any(p.name!='result.json' for p in folder.iterdir()))


def summarize(path):
    path=Path(path);combined=read(path);waves=[];cells=[];case_rows=[];by_case_cells={}
    for component in combined['components']:
        source=Path(component['path']);packet=read(source)
        if sha(source)!=component['sha256']:raise ValueError('Component changed')
        partial=[r for r in packet['rows'] if r['status']=='total_deadline_fallback'
                 and started(r,source.parent/'cases'/r['case'])]
        waves.append(dict(path=str(source),cases=len(packet['rows']),wall_seconds=packet['wall_seconds'],
            status_counts=dict(Counter(r['status'] for r in packet['rows'])),
            started_or_preserved=sum(started(r,source.parent/'cases'/r['case']) for r in packet['rows']),
            completed_worker_wall_seconds=sum(r.get('wall_seconds',0.) for r in packet['rows']),
            global_partial_started_cases=[r['case'] for r in partial],
            global_partial_accepted_stages={k:sum(r['variants'][k]['accepted'] for r in partial) for k in LABELS},
            all_workers_joined=packet['workers_joined']))
        for cell_path in (source.parent/'cases').glob('*/*.rf.json'):
            cell=read(cell_path);case=cell_path.parent.name
            cells.append(dict(cell,case=case,path=str(cell_path)))
            key=(case,cell['model'],cell['arm'])
            if key in by_case_cells:raise ValueError('A raw model-arm cell was attempted twice')
            by_case_cells[key]=cell
    pair_counts={}
    for model in ('A','B'):
        pairs=[[by_case_cells.get((r['case'],model,arm)) for arm in ('c0','fitted_c')] for r in combined['rows']]
        pair_counts[model]=dict(complete=sum(all(c and c['status']=='complete' for c in pair) for pair in pairs),
            qualified=sum(all(c and c.get('qualified') for c in pair) for pair in pairs))
    for row in combined['rows']:
        item=dict(case=row['case'],dataset=row['dataset'],status=row['status'],
                  source_results=combined['provenance'][row['case']]['results_path'])
        for label in LABELS:
            item[label+'_status']=row['variants'][label]['status']
            item[label+'_accepted']=row['variants'][label]['accepted']
            item[label+'_selected_source']=row['variants'][label]['selected_output']['fitted_c']['source']
        for model in ('A','B'):
            for arm in ('c0','fitted_c'):
                cell=by_case_cells.get((row['case'],model,arm))
                item[model+'_'+arm+'_cell_status']=cell['status'] if cell else 'not_completed'
        case_rows.append(item)
    summary=dict(combined_results_sha256=sha(path),available=combined['available'],
        total_source_members=combined['total_source_members'],unavailable_source_members=combined['unavailable_source_members'],
        never_started_remaining=combined['never_started_remaining'],waves=waves,
        completed_worker_wall_seconds=sum(w['completed_worker_wall_seconds'] for w in waves),
        worker_time_scope='Exact sum of terminal worker elapsed receipts; excludes global-deadline partial worker time',
        raw_model_arm_cell_status_counts=dict(Counter(c['status'] for c in cells)),
        qualified_raw_model_arm_cells=sum(c.get('qualified',False) for c in cells),
        raw_fit_pairs=pair_counts,policy_accepted_pairs=combined['accepted_pairs'],
        failed_cells=[dict(case=c['case'],model=c['model'],arm=c['arm'],status=c['status'],reason=c.get('reason'))
                      for c in cells if c['status']!='complete'],
        status_counts=combined['status_counts'],geography_read=False)
    cap_details=[]
    for row in combined['rows']:
        if row['status']!='preload_or_guard_cap':continue
        trace=row.get('traceback','')
        stage=next((name for token,name in [('guard_module.evaluate_guard','geometry_guard'),
            ('covariance.candidate_context','causal_covariance_preparation'),
            ('e.rank_families','family_ranking'),('numerical.baseline_diagnostic','baseline_numerical_probe'),
            ('e.load_case','baseline_reconstruction')] if token in trace),'unclassified')
        cap_details.append(dict(case=row['case'],stage=stage))
    summary['worker_cap_stages']=dict(Counter(r['stage'] for r in cap_details))
    summary['worker_caps']=cap_details
    summary['frequency_fit_scope']='Curved-point conditional RMS; saved-baseline RMS was not recorded; full native union/owners remain fixed'
    summary['B_accepted_incremental_RMS_where_A_RMS_recorded']={}
    for arm in ('c0','fitted_c'):
        pairs=[]
        for row in combined['rows']:
            left=row['variants']['A']['selected_output'][arm]
            right=row['variants']['A+B']['selected_output'][arm]
            if row['variants']['A+B']['accepted'] and 'rms_hz' in left and 'rms_hz' in right:
                pairs.append(dict(case=row['case'],A_rms_hz=left['rms_hz'],B_rms_hz=right['rms_hz'],
                                  B_minus_A_hz=right['rms_hz']-left['rms_hz']))
        summary['B_accepted_incremental_RMS_where_A_RMS_recorded'][arm]=dict(
            cases=len(pairs),mean_B_minus_A_hz=statistics.mean(p['B_minus_A_hz'] for p in pairs) if pairs else None,
            median_B_minus_A_hz=statistics.median(p['B_minus_A_hz'] for p in pairs) if pairs else None,pairs=pairs)
    (HERE/'rf_execution_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    with (HERE/'rf_case_ledger.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(case_rows[0]));writer.writeheader();writer.writerows(case_rows)
    lines=['# RF execution and coverage','',
           f"All {summary['available']} available recordings retain explicit paired policy decisions; {summary['unavailable_source_members']} unavailable source members remain outside this denominator.",'',
           '| Wave | Enqueued | Started or preserved | Wall seconds | Global partial starts |',
           '|---|---:|---:|---:|---:|']
    for index,w in enumerate(waves,1):
        lines.append(f"| {index} | {w['cases']} | {w['started_or_preserved']} | {w['wall_seconds']:.2f} | {len(w['global_partial_started_cases'])} |")
    lines+=['',f"Complete raw fit pairs: A {pair_counts['A']['complete']} ({pair_counts['A']['qualified']} qualified), B {pair_counts['B']['complete']} ({pair_counts['B']['qualified']} qualified). C evaluates the same B endpoints and performs no additional position fit.",'',
            f"Policy-accepted pairs: A {summary['policy_accepted_pairs']['A']}, A+B {summary['policy_accepted_pairs']['A+B']}, A+B+C {summary['policy_accepted_pairs']['A+B+C']}. Acceptance is distinct from completed raw fits and all fallback rows remain in the population.",'',
            f"Raw model-arm cell statuses: `{summary['raw_model_arm_cell_status_counts']}`. These cell caps are separate from interrupted starts at a global wave deadline.",'',
            f"Outer preparation/guard cap stages, classified from sealed tracebacks: `{summary['worker_cap_stages']}`.",'',
            f"Summed elapsed time from terminal worker receipts is {summary['completed_worker_wall_seconds']:.2f} worker-seconds. This excludes worker time for global-deadline partial starts and is not a total-compute or speedup claim.",'',
            'No attempted case or capped cell was retried. Additional waves admit only never-started queue placeholders. All pools were joined. Position accuracy is evaluated separately by the parent after the combined RF audit.','',
            'The [receipt archive](../evaluation_receipts.tar.gz) preserves exact component ledgers, case evidence, eligibility plans and the combined ledger. See [RF summary](rf_execution_summary.json), [case ledger](rf_case_ledger.csv) and [prospective completion methods](COVERAGE_COMPLETION.md).','']
    (HERE/'EXECUTION.md').write_text('\n'.join(lines))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('waves','failed_cells')},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,default=HERE/'combined_results.json')
    summarize(ap.parse_args().results)
