"""Compact endpoint/gate/weight/vector facts from immutable saved artifacts."""
import csv
import json
from pathlib import Path
import numpy as np
import geometry_cache as gc

HERE=Path(__file__).resolve().parent
OLD=Path('/srv/bulk/leo/research/ds24-ambiguity-position-r01/ambiguity')
read=lambda path:json.loads(Path(path).read_bytes())


def table(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    for seal in [HERE/'RF_seal.json',HERE/'geographic/seal.json']:
        for name,digest in read(seal)['files'].items():
            if gc.sha(name)!=digest:raise ValueError('immutable file changed:'+name)
    out=HERE/'compact';out.mkdir(exist_ok=False)
    weak=np.asarray(read(OLD/'prepared/DS24-0011/metadata.json')['weak'])
    previous=read(OLD/'DS24-0011/execution.json')['contrasts']
    execution=read(HERE/'execution.json');endpoints=[];weights=[];vectors=[]
    for arm in ('c0','fitted_c'):
        saved={method:read(HERE/arm/method/'raw_endpoint.json') for method in ('no_addition','hard','mixture')}
        for method,raw in saved.items():
            g=read(HERE/arm/method/'gates.json');n=read(HERE/arm/method/'numerical_qualification.json')
            result=next(row for row in execution['all6_slots'] if row['arm']==arm and row['method']==method)
            endpoints.append(dict(arm=arm,method=method,status=result['status'],endpoint_east_north_km=raw['endpoint_east_north_km'],
                completed_outer_rounds=len(raw['history']),fit_seconds=raw['scientific_fit_seconds'],
                parent_negative_twice_ELBO=raw['parent_negative_twice_elbo'],target=raw['target_prediction'],
                parent_original_valid=g['parent_original_valid'],Gamma_converged=g['Gamma_converged'],
                final_phase_change_s=g['final_phase_change_s'],maximum_unclipped_phase_s=g['maximum_unclipped_phase_s'],
                numerical_qualification=n['passed'],numerical_max_score_error=n.get('maximum_score_error'),
                numerical_max_gradient_error=n.get('maximum_gradient_error'),
                original_likelihood_counts={name:g['membership'][name] for name in ('curved_points','predictive_points','likelihood_points','total_GLRT')},
                original_accepted_IDs_lost=g['original_accepted_IDs_lost'],original_source=g['source'],
                operational_policy='exact_original_reference',target_association_qualified=False))
        p=saved['mixture']['target_prediction'];log=np.r_[[row['logZ'] for row in p['candidates']],-.5*p['unknown_objective']]
        prior=np.r_[np.repeat(.5/8,8),.5];log+=np.log(prior);posterior=np.exp(log-log.max());posterior/=posterior.sum()
        labels=[row['norad'] for row in p['candidates']]+['unresolved']
        for label,value in zip(labels,posterior,strict=True):
            weights.append(dict(arm=arm,hypothesis=label,conditional_density_weight=float(value),
                physical_class_prior=.5,calibrated_identity_probability=False))
        old=next(row for row in previous if row['arm']==arm and row['weight']==.5)
        for left,right in [('no_addition','hard'),('no_addition','mixture'),('hard','mixture')]:
            delta=np.asarray(saved[right]['endpoint_east_north_km'])-saved[left]['endpoint_east_north_km']
            vectors.append(dict(arm=arm,comparison=right+'_minus_'+left,east_m=float(delta[0]*1000),north_m=float(delta[1]*1000),
                endpoint_separation_m=float(np.linalg.norm(delta)*1000),frozen_c0_weak_axis_projection_m=float(delta@weak*1000),
                old_mixture_minus_hard_secant_proxy_m=old['archived_c0_curvature_scaled_secant_proxy_km']*1000,
                old_proxy_lower_m=old['proxy_interval_km'][0]*1000,old_proxy_upper_m=old['proxy_interval_km'][1]*1000,
                separation_is_accuracy_gain=False,proxy_is_displacement_bound=False))
    with (out/'endpoints_and_gates.json').open('x') as stream:json.dump(dict(rows=endpoints,declared_slots=6,complete_slots=6),stream,indent=2);stream.write('\n')
    table(out/'mixture_weights.csv',weights);table(out/'endpoint_vectors.csv',vectors)
    files={str(path):gc.sha(path) for path in out.iterdir() if path.is_file()}
    for path in [Path(__file__),HERE/'RF_seal.json',HERE/'geographic/seal.json',OLD/'prepared/DS24-0011/metadata.json',OLD/'DS24-0011/execution.json']:
        files[str(path)]=gc.sha(path)
    with (out/'seal.json').open('x') as stream:json.dump(dict(files=files,new_model_evaluations=0),stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
