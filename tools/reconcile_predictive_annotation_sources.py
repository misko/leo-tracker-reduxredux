"""Find predictive-only annotation evidence before rerunning older-role curves."""
import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from debug_fast_graph_unassociated import read, write
from audit_annotation_likelihood_roles import describe
from annotation_partition_plan import require_distinct_annotation


def matching_evidence(protocol, result, job, observation_ids):
    if protocol.get('target_used_for_calibration') is not False:
        return None
    if result.get('inclusion_mode') != 'predictive_only' or result.get('identity_score_name') != 'conditional_target':
        return None
    target = protocol.get('target', {})
    if result.get('track_id') != job['track_id'] or target.get('track_id') != job['track_id']:
        return None
    if protocol.get('job', {}).get('job_id') != job['job_id']:
        raise ValueError('annotation belongs to a different scan')
    ids = target.get('observation_ids', [])
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('annotation has missing or duplicate physical observation IDs')
    coverage = 'exact_target' if set(ids) == set(observation_ids) else 'different_or_partial_target'
    distinct = False
    try:
        require_distinct_annotation(result, protocol)
        distinct = True
    except ValueError:
        pass
    return dict(coverage=coverage, distinct_partition_receipt=distinct, **describe(result))


def run(args):
    out=args.output; out.mkdir(parents=True,exist_ok=False)
    hashes={}; cache={}
    def load(path):
        data=path.read_bytes(); hashes[str(path)]=hashlib.sha256(data).hexdigest()
        import json
        return json.loads(data)
    jobs={r['track_id']:r for r in load(args.study/'systematic-annotation-v1/protocol.json')['rows']}
    queue=load(args.roles/'review_queue.json'); wanted={r['track_id'] for r in queue}
    physical={}
    for tid in wanted:
        job=jobs[tid]; path=Path(job['inventory'])
        if str(path) not in cache:cache[str(path)]=load(path)
        physical[tid]=next(r['observation_ids'] for r in cache[str(path)]['tracks'] if r['track_id']==tid)
    matches=defaultdict(list); protocols=sorted(args.study.rglob('protocol.json'))
    for path in protocols:
        pr=load(path); tid=pr.get('target',{}).get('track_id')
        resultpath=path.parent/'result.json'
        if tid not in wanted or pr.get('target_used_for_calibration') is not False or not resultpath.exists():continue
        result=load(resultpath); evidence=matching_evidence(pr,result,jobs[tid],physical[tid])
        if evidence is not None:matches[tid].append(dict(source=str(resultpath),protocol=str(path),**evidence))
    rows=[]; pending=[]
    for original in queue:
        tid=original['track_id']; exact=[r for r in matches[tid] if r['coverage']=='exact_target']
        states=sorted({r['status'] for r in exact}); distinct=sum(r['distinct_partition_receipt'] for r in exact)
        state='existing_predictive_annotation' if exact else 'only_partial_or_different_target' if matches[tid] else 'no_predictive_annotation_found'
        rows.append(dict(original,reconciliation=state,predictive_sources=len(exact),distinct_partition_sources=distinct,
            recorded_predictive_states=';'.join(states),sources=';'.join(r['source'] for r in matches[tid])))
        if not exact:pending.append(dict(jobs[tid],state='queued'))
    pending.sort(key=lambda r:(-r['points'],r['track_id']))
    write(out/'source_links.json',dict(matches)); write(out/'pending.json',pending)
    # Existing bounded runner can consume this frozen queue. No annotation is
    # silently selected among differing hypotheses or promoted to acceptance.
    write(out/'protocol.json',dict(rows=pending,likelihood_role='predictive_only',source_registry=str(out),
        selection='no exact predictive-role annotation found; descending point count',no_acceptance_inferred=True))
    with (out/'reconciliation.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write(out/'summary.json',dict(older_role_queue=len(queue),protocols_scanned=len(protocols),
        states=dict(Counter(r['reconciliation'] for r in rows)),pending=len(pending),
        curves_with_distinct_partition_receipt=sum(r['distinct_partition_sources']>0 for r in rows),
        source_hashes=hashes,no_new_associations=True,no_automatic_primary_source_replacement=True))
    print('reconciled',len(queue),'pending',len(pending),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','roles','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
