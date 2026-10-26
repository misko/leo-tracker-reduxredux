"""Saved RF outputs, exact equivalence and ordered timing readback only."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ambiguity-policy-r01/position')
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def table(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    spec=importlib.util.spec_from_file_location('prior_RF_report',PRIOR/'rf_report.py')
    report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
    report.HERE=HERE;report.OUT=HERE/'report';report.main()
    equivalence=[];old_seconds=0.;cached_seconds=0.
    for path in sorted((HERE/'equivalence').glob('*.json')):
        row=read(path);old=sum(item['old_seconds'] for item in row['points']);cached=sum(item['cached_seconds'] for item in row['points'])
        old_seconds+=old;cached_seconds+=cached
        equivalence.append(dict(arm=row['arm'],control=row['name'],point_scores=len(row['points']),
            old_seconds=old,cached_seconds=cached,ordered_speed_ratio=old/cached,
            maximum_objective_error=max(item['error'] for item in row['points']),gradient_error=row['gradient_error'],
            geometry_checks=len(row['geometry']),maximum_geometry_frequency_error=max((item['errors']['frequency_hz'] for item in row['geometry']),default=None),
            parent_warm_order_caveat=True))
    table(HERE/'report/equivalence.csv',equivalence)
    controls=[]
    for arm in ('c0','fitted_c'):
        for method in ('no_addition','hard','mixture'):
            result=read(HERE/arm/(method+'_result.json'))
            epochs=[read(path) for path in sorted((HERE/arm/method).glob('epoch*.json'))]
            previous=read(PRIOR/arm/(method+'_result.json'))
            previous_epochs=[read(path) for path in sorted((PRIOR/arm/method).glob('epoch*.json'))]
            match=read(HERE/arm/(method+'_prior_control.json')) if method!='mixture' and (HERE/arm/(method+'_prior_control.json')).exists() else {}
            controls.append(dict(arm=arm,method=method,status=result['status'],prior_status=previous['status'],
                completed_outer_rounds=len(epochs),prior_completed_outer_rounds=len(previous_epochs),
                complete_round_residual_evaluations=sum(item['fit']['evaluations'] for item in epochs),
                prior_complete_round_residual_evaluations=sum(item['fit']['evaluations'] for item in previous_epochs),
                reported_method_seconds=result.get('seconds'),prior_reported_complete_method_seconds=previous.get('seconds'),
                unchanged_fit_cap_seconds=60,prior_control_passed=match.get('passed'),
                prior_endpoint_difference_km=match.get('endpoint_difference_km'),prior_parent_ELBO_difference=match.get('parent_ELBO_difference'),
                interrupted_round_evaluations_are_not_counted=True,operational_policy='original_reference'))
    table(HERE/'report/controls_and_cost.csv',controls)
    with (HERE/'report/cache_timing.json').open('x') as stream:
        json.dump(dict(old80_score_seconds=old_seconds,cached80_score_seconds=cached_seconds,ordered_speed_ratio=old_seconds/cached_seconds,
            caveat='Original score called first, cached second with the same parent; cached call benefits from warm parent. This is ordered paired timing, not a general benchmark.',
            cache_bytes=read(HERE/'cache_manifest.json')['total_bytes'],new_scientific_evaluations=0),stream,indent=2);stream.write('\n')
    files={str(path):sha(path) for path in (HERE/'report').iterdir() if path.is_file()}
    files[str(Path(__file__))]=sha(__file__)
    with (HERE/'report/readback_seal.json').open('x') as stream:json.dump(dict(files=files),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(ordered_speed_ratio=old_seconds/cached_seconds,controls=len(controls))))


if __name__=='__main__':main()
