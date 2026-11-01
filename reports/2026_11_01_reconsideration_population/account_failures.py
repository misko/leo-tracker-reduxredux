"""Account for bounded execution failures without calling them successful searches.

ALGO06 has already been exactly replayed in these cases. No partially searched
candidate is published when the predeclared process budget is exhausted.
"""
import evaluate as e


def main():
    jobs=[]
    for stage in ('evaluation','validation'):
        jobs+=e.read(e.OUT/(stage+'-jobs.json'))
    if len(jobs)!=len(e.read(e.OUT/'protocol.json')['cohort']):raise ValueError('Jobs still pending')
    failed=[];completed_before_wrapper_timeout=[]
    tail={r['case']:r for r in e.read(e.OUT/'tail-jobs.json')} if (e.OUT/'tail-jobs.json').exists() else {}
    if (e.OUT/'ds27-jobs.json').exists():
        for r in e.read(e.OUT/'ds27-jobs.json'):
            if r['status'] in ('failed','timeout'):tail[r['case']]=r
    for job in jobs:
        folder=e.OUT/job['case']
        if (folder/'result.json').exists():
            if job['status']=='timeout':completed_before_wrapper_timeout.append(job)
            continue
        if tail.get(job['case'],{}).get('status') in ('failed','timeout'):job=tail[job['case']]
        if job['status'] not in ('failed','timeout'):raise ValueError('Missing successful job output')
        if not (folder/'baseline.json').exists():raise ValueError('Cannot assign baseline before exact replay')
        baseline=e.read(folder/'baseline.json');history=e.read(folder/'history.json') if (folder/'history.json').exists() else dict(requested=[],available=[],missing=[],changed=False)
        targets=e.read(folder/'trigger.json')['selected'] if (folder/'trigger.json').exists() else []
        result=dict(case=job['case'],baseline=baseline,methods={m:dict(selected=None,final=baseline) for m in e.METHODS},
            history=history,history_records=[],records={m:[] for m in ('reassociation_only','combined')},targets=targets,
            failures=[dict(stage='bounded_process',reason=job['status'],log=job['log'])],propagation_failures=[],
            seconds=job['seconds'],execution_status='compute_fallback',execution=job,production_changed=False)
        e.write(folder/'result.json',result);failed.append(job)
    e.write(e.OUT/'compute_fallbacks.json',dict(cases=failed,completed_before_wrapper_timeout=completed_before_wrapper_timeout,
        scope='Exact ALGO06 fallback after incomplete bounded search; complete atomic result before wrapper shutdown timeout remains a complete scientific outcome'))
    print('Recorded',len(failed),'explicit compute fallbacks')


if __name__=='__main__':main()
