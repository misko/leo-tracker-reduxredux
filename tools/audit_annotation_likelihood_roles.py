"""Resolve recorded annotation roles without turning old support into acceptance."""
import argparse,csv,hashlib
from collections import Counter
from pathlib import Path
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus


def describe(result):
    predictive=result.get('inclusion_mode')=='predictive_only' and result.get('identity_score_name')=='conditional_target'
    role='predictive_only' if predictive else 'older_calibration_participating'
    a=identity_consensus(result['folds'],score_name='conditional_target' if predictive else result.get('identity_score_name','joint'))
    return dict(role=role,status=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'))


def next_action(row,description):
    # These fields record separate hypotheses; never silently overwrite them.
    if any(row.get(k) for k in ('inclusion_source','predictive_inclusion_source','bundle_inclusion_source','inactive_fragment_inclusion_source')):
        return 'review_recorded_inclusion'
    if any(row.get(k) for k in ('predictive_role_status','distinct_retest_status','inactive_fragment_state','pulse_research_source')):
        return 'reconcile_separate_role_or_fragment_evidence'
    if description is None:return 'reconcile_missing_primary_source'
    if description['role']!='predictive_only':return 'needs_predictive_role_assessment_in_primary_ledger'
    if description['status']=='conditionally_supported_identity':return 'supported_predictive_identity_needs_inclusion_source'
    return 'resolve_'+description['status']


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    source=list(csv.DictReader(args.ledger.open()));rows=[];hashes={str(args.ledger):hashlib.sha256(args.ledger.read_bytes()).hexdigest()}
    for r in source:
        name=r.get('predictive_recheck_source') or r.get('annotation_source');description=None
        if name:
            path=Path(name);result=read(path);hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            if result['track_id']!=r['track_id']:raise ValueError('annotation belongs to another curve')
            description=describe(result)
        rows.append(dict(track_id=r['track_id'],job_id=r['job_id'],scan=r['label'],points=int(r['points']),
            recorded_original_state=r['state'],primary_source=name,
            **({} if description is None else description),next_action=next_action(r,description)))
    if len({r['track_id'] for r in rows})!=len(rows):raise ValueError('duplicate inventory IDs')
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (args.output/'roles.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
    queued=sorted([r for r in rows if r['next_action']=='needs_predictive_role_assessment_in_primary_ledger'],key=lambda r:(-r['points'],r['track_id']))
    write(args.output/'review_queue.json',queued)
    write(args.output/'summary.json',dict(total=len(rows),primary_roles=dict(Counter(r.get('role','no_primary_source') for r in rows)),
        actions=dict(Counter(r['next_action'] for r in rows)),
        predictive_states=dict(Counter(r['status'] for r in rows if r.get('role')=='predictive_only')),
        does_not_assert_no_other_research_exists=True,position_acceptance_not_inferred=True,
        primary_precedence='explicit predictive_recheck_source, otherwise annotation_source; no filesystem timestamp ordering',
        source_hashes=hashes))
    print('audited',len(rows),'rows; primary-ledger predictive review queue',len(queued),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ledger','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
