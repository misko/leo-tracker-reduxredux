"""Separately frozen full193 evaluation and static report entrypoint."""
import json
from pathlib import Path
import sys
import evaluation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NUMERICAL_SHA = '41b1acba455805344d17f5ecf92b0827e645defd5f5ffaafb69da86f71c3f0f6'
NUMERICAL_DIGEST = 'sha256:b5fb8cbbd6c950d85ef0ae21912eff286a052c430e84b037740358116857db6c'
SOURCES = ('evaluation.py','report_metrics.py','publish.py','report.py',
           'test_evaluation.py','test_report_metrics.py','test_publish.py',
           'EVALUATION_PLAN.md','EVALUATION_REVIEW.md')


def prepare_evaluation():
    """Metadata only; root explicitly freezes and publishes before evaluation."""
    if evaluation.sha(HERE/'protocol.json') != NUMERICAL_SHA:
        raise ValueError('frozen numerical protocol changed')
    plan = json.loads((HERE/'protocol.json').read_text())
    sources = dict(plan['evaluation_source_sha256'])
    for name in SOURCES:
        path = HERE/name
        sources[str(path.relative_to(ROOT))] = evaluation.sha(path)
    for name, expected in sources.items():
        if evaluation.sha(ROOT/name) != expected:
            raise ValueError('evaluation source changed: '+name)
    return dict(numerical_protocol_sha256=NUMERICAL_SHA,
                numerical_protocol_digest=NUMERICAL_DIGEST,source_sha256=sources,
                references='only after exact193 terminal authentication',
                missing='preserve failures and withhold incomplete full-membership metrics',
                scope='Consumed single-pass policy sensitivity; no deployment or unseen-validation claim')


def main():
    plan = json.loads((HERE/'protocol.json').read_text())
    if sys.executable != plan['runtime']['interpreter']:
        raise ValueError('immutable47e interpreter required')
    if evaluation.sha(HERE/'protocol.json') != NUMERICAL_SHA:
        raise ValueError('numerical protocol changed')
    for name in ('SUMMARY.json','METRICS.json','RESULTS.md','REPORT_INTEGRITY.json',
                 'paired-position.png','error-ecdf.png','c-contrast.png','member-errors.png'):
        if (HERE/name).exists():
            raise ValueError('report artifact already exists; review rather than overwrite: '+name)
    summary = evaluation.build(plan,HERE/'results',NUMERICAL_DIGEST)
    from report_metrics import aggregate
    from publish import publish
    metrics = aggregate(plan['members'],summary['rows'])
    with (HERE/'SUMMARY.json').open('x') as stream:
        json.dump(summary,stream,indent=2,allow_nan=False);stream.write('\n')
    images = publish(summary,metrics,HERE)
    paths = [HERE/name for name in ('protocol.json','evaluation_protocol.json',
             'SUMMARY.json','METRICS.json','RESULTS.md')] + images
    with (HERE/'REPORT_INTEGRITY.json').open('x') as stream:
        json.dump({p.name:evaluation.sha(p) for p in paths},stream,indent=2);stream.write('\n')


if __name__ == '__main__':
    main()
