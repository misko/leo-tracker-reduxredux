"""Audit domain-only hypothesis rejection and preservation of completed fits."""

from calibrate_ds23_excluded_catalogue import OUT, context
from complete_ds23_excluded_catalogue import prepare
from ds23_excluded_catalogue import apply_changes
from ds23_receiver_family_search import orphan_predictive_labels
from run_algo01_ds23_sample import ROOT, read, write, sha


def main():
    protocol = prepare()
    initial = read(OUT/'cohort_execution.json')
    completion = read(OUT/'support_completion_execution.json')
    if not initial['all_terminal'] or not completion['all_terminal'] or completion['errors']:
        raise ValueError('both initial and support-completion jobs must be terminal')
    sealed = read(OUT/'unchanged_initial_result_bindings.json')
    for case, digest in sealed['results'].items():
        if sha(OUT/case/'result.json')!=digest:
            raise ValueError('a completed initial scientific result changed')
    repaired = {r['case'] for r in completion['receipts']}
    failed = {r['case'] for r in initial['errors']}
    if repaired!=failed or repaired!=set(sealed['support_completion_cases']):
        raise ValueError('initial error population was not completed exactly')
    rejections = []
    for case in sorted(repaired):
        _,node,_,_,_,_,_,_,_,entries,_ = context(case)
        result = read(OUT/case/'result.json')
        for row in result['rejected_hypotheses']:
            changed,predictive = apply_changes(node,entries,row['choices'])
            missing = orphan_predictive_labels(changed,predictive)
            if not missing or missing!=row['unsupported_predictive_indices']:
                raise ValueError('a representable hypothesis was rejected as unsupported')
            if [e['observation_ids'] for e in predictive]!=[e['observation_ids'] for e in entries]:
                raise ValueError('observations were removed while rejecting a hypothesis')
            rejections.append(dict(case=case,index=row['index'],unsupported_labels=missing))
        for trial in result['reused_partial_trials']:
            if sha(ROOT/trial['path'])!=trial['sha256']:
                raise ValueError('a reused partial trial changed after its replay')
    cases = protocol['development_cases']+protocol['confirmation_cases']
    bindings = {c:sha(OUT/c/'result.json') for c in cases}
    if len(bindings)!=40:
        raise ValueError('complete 40-recording cohort required')
    write(OUT/'completed_cohort_audit.json',dict(all_terminal=True,qualified=True,
        result_sha256=bindings,initial_completed_results_unchanged=len(sealed['results']),
        repaired_cases=sorted(repaired),rejected_hypotheses=rejections,
        no_observations_removed=True,no_GPS_used=True,
        initial_execution_sha256=sha(OUT/'cohort_execution.json'),
        completion_execution_sha256=sha(OUT/'support_completion_execution.json')))
    print('All 40 scans complete;',len(rejections),'unrepresentable hypotheses rejected;',len(sealed['results']),'initial results unchanged.',flush=True)


if __name__=='__main__':
    main()
