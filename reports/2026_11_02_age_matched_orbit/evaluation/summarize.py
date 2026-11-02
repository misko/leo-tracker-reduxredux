"""RF-only execution and frequency contrasts; no new fitting or geography."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
ARMS=('c0','fitted_c')
POLICIES=('Age3','Age2')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def moments(values):
    return dict(cases=len(values),mean=statistics.mean(values) if values else None,
                median=statistics.median(values) if values else None,
                minimum=min(values) if values else None,maximum=max(values) if values else None)


def summarize(path):
    packet=read(path);rows=packet['rows'];cells=[];ledger=[]
    for row in rows:
        item=dict(case=row['case'],dataset=row['dataset'],target_family=row['target_family'],
            frozen_pair_count=(row.get('age_support') or {}).get('pair_count'),
            frozen_history_status=(row.get('age_support') or {}).get('status'),
            attempt_started=row['new_model_attempt_started'],status=row['status'])
        for label in POLICIES:
            item[label+'_accepted']=row['policies'][label]['accepted']
            item[label+'_selected_source']=row['policies'][label]['selected_output']['fitted_c']['source']
        for arm in ARMS:
            cell_path=ROOT/'cases'/row['case']/('age-'+arm+'.rf.json')
            cell=read(cell_path) if cell_path.exists() else None
            if cell is not None:cells.append(dict(cell,case=row['case']))
            item[arm+'_cell_status']=cell['status'] if cell else 'not_completed'
            item[arm+'_qualified']=bool(cell and cell.get('qualified'))
            item[arm+'_failed_qualification']=';'.join(cell.get('failed_qualification',[])) if cell else ''
            control=row.get('selected_A_control_replay',{}).get(arm,{})
            item[arm+'_A_curved_RMS_hz']=control.get('rms_hz')
            item[arm+'_age_curved_RMS_hz']=cell.get('rms_hz') if cell else None
        ledger.append(item)
    frequencies={}
    for subset in ('complete_pair','qualified_pair',*POLICIES):
        subset_rows=[]
        for row in rows:
            endpoints=row.get('raw_endpoints',{})
            complete=set(endpoints)==set(ARMS) and all(endpoints[a]['status']=='complete' for a in ARMS)
            eligible=complete if subset=='complete_pair' else complete and row.get('candidate_qualified') if subset=='qualified_pair' else row['policies'][subset]['accepted']
            if eligible:subset_rows.append(row)
        frequencies[subset]={}
        for arm in ARMS:
            comparable=[r for r in subset_rows if 'rms_hz' in r.get('selected_A_control_replay',{}).get(arm,{})]
            rms=[r['raw_endpoints'][arm]['rms_hz']-r['selected_A_control_replay'][arm]['rms_hz'] for r in comparable]
            objective=[r['immutable_comparators']['A'][arm]['objective']-r['raw_endpoints'][arm]['objective'] for r in comparable]
            frequencies[subset][arm]=dict(age_minus_A_curved_RMS_hz=moments(rms),A_minus_age_objective_diagnostic=moments(objective))
    snapshot_counts=Counter()
    for row in rows:
        for value in row.get('selected_A_control_replay',{}).values():snapshot_counts['A_'+value.get('nuisance',{}).get('status','absent')]+=1
        for value in row.get('raw_endpoints',{}).values():
            if value['status']=='complete':snapshot_counts['age_'+value.get('nuisance',{}).get('status','absent')]+=1
    summary=dict(results_sha256=sha(path),protocol_sha256=packet['protocol_sha256'],available=packet['available'],
        total_source_members=packet['total_source_members'],unavailable_source_members=packet['unavailable_source_members'],
        candidate_subset=packet['candidate_subset'],actual_started=sum(r['new_model_attempt_started'] for r in rows),
        status_counts=packet['status_counts'],policy_accepted=packet['policy_accepted'],
        wall_seconds=packet['wall_seconds'],completed_worker_wall_seconds=sum(r.get('wall_seconds',0.) for r in rows),
        worker_time_scope='Sum of terminal worker elapsed receipts; excludes global-deadline partial workers',
        workers_joined=packet['workers_joined'],raw_cell_status_counts=dict(Counter(r['status'] for r in cells)),
        qualified_raw_cells=sum(r.get('qualified',False) for r in cells),nuisance_snapshot_counts=dict(snapshot_counts),
        frequency_contrasts=frequencies,
        frequency_scope='Same fixed curved observation rows; conditional coefficient representation with declared predictive attachments; ancillary mixtures are not a joint residual RMS',
        objective_scope='Diagnostic normalized contrasts across different covariance/phase approximations; never an acceptance rule or localization accuracy',
        caps=[dict(case=r['case'],status=r['status'],reason=r.get('reason')) for r in rows if r['status'] in ('preparation_cap','global_deadline_partial','global_deadline_unattempted','failed')],
        cell_caps=[dict(case=r['case'],arm=r['arm'],status=r['status'],reason=r.get('reason')) for r in cells if r['status']!='complete'],
        no_position_fit=True,no_geography_read=True)
    (ROOT/'execution_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    with (ROOT/'case_ledger.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(ledger[0]));writer.writeheader();writer.writerows(ledger)
    text=['# Bounded age-prior execution','',
        f"The policy ledger retains all {summary['available']} available recordings and {summary['unavailable_source_members']} unavailable source members. Exactly {summary['candidate_subset']} cases had a predeclared ready age covariance; {summary['actual_started']} reached the one fresh attempt.",'',
        f"Wall time: {summary['wall_seconds']:.2f} seconds with eight BLAS=1 workers; all workers joined. Summed terminal worker elapsed time: {summary['completed_worker_wall_seconds']:.2f} worker-seconds; global partial worker time is excluded.",'',
        f"Policy adoption counts: Age3 primary {summary['policy_accepted']['Age3']}, Age2 exploratory {summary['policy_accepted']['Age2']}. Both use the same raw endpoints, fixed shrinkage and unchanged RF qualification. Every other row retains immutable selected A.",'',
        f"Raw model-arm statuses: `{summary['raw_cell_status_counts']}`; {summary['qualified_raw_cells']} qualified. Case statuses: `{summary['status_counts']}`. Cell caps and global partials are explicit and were never retried.",'',
        'No original A/B fit, failed cell, family ranking or numerical baseline probe was rerun. Baseline and immutable A control objectives/native unions were replayed before the new covariance fit. RF and position outcomes remain separate; frequency contrasts and objective scope are in the JSON summary.','',
        'Compact base-coefficient, block-layout, receiver/phase/smooth state and orbital-coordinate snapshots are diagnostic only. They are conditional on the model and declared predictive attachments; ancillary phase-mixture families are not a jointly fitted nuisance posterior.','',
        'See [execution summary](execution_summary.json), [case ledger](case_ledger.csv) and the [exact receipt archive](../evaluation_receipts.tar.gz).','']
    (ROOT/'EXECUTION.md').write_text('\n'.join(text))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('frequency_contrasts','caps','cell_caps')},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,default=ROOT/'results.json')
    summarize(ap.parse_args().results)
