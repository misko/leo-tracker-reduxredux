"""Inspect rejected gradients and the per-window evidence in the Hard60 worst scan."""
from dataclasses import replace
import numpy as np
import diagnose as d


def rejected_gradients():
    outputs=[]
    for r in d.read(d.HERE/'probes.json')['outputs']:
        if r['kind']!='pipeline' or r['mode']!='calibration_retry':continue
        label,phase,xy=r['label'],r['phase'],r['point']
        _,obs,bank,prior,score=d.engine.CONTEXT[label]
        score=replace(score,relative_sigma_s=d.CONFIGS[phase]['sigma'])
        point=d.read(d.source(label,phase)/'points'/f'{xy[0]:g}_{xy[1]:g}.json')
        region=d.read(d.region_path(d.HERE/'calibration_retry/results'/label/phase,xy,r['radius_km']))
        first=next(c for c in r['calls'] if c['fixed_position'])
        subset=bank.select(point['bootstrap']['satellite_indices'])
        is_post=point['fit']['converged']
        baseline=np.asarray(region['calibration']['correction']['values_hz']) if is_post else None
        obj=d.PenalizedObjective(d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=baseline),d.CONFIGS[phase]['slope_prior'])
        v=np.asarray(first['vector']);value,g,_=obj.evaluate(v)
        scales=np.r_[1.,1.,200.,2.,200.,2.,200.,np.ones(len(v)-7)]
        g[:2]=0.;indices=np.argsort(abs(g*scales))[-4:][::-1]
        differences=[]
        for index in indices:
            # Probe physical displacements corresponding to small scaled steps.
            for hscaled in (1e-5,1e-6,1e-7):
                h=scales[index]*hscaled;delta=np.zeros(len(v));delta[index]=h
                low=obj.evaluate(v-delta)[0];high=obj.evaluate(v+delta)[0]
                differences.append(dict(index=int(index),step=float(h),analytic_scaled_gradient=float(g[index]*scales[index]),
                    left_scaled_gradient=float((value-low)/hscaled),right_scaled_gradient=float((high-value)/hscaled),
                    left_objective_change=float(low-value),right_objective_change=float(high-value)))
        shifts=v[7]+obj.basis@v[8:]
        step=bank.nodes_s[1]-bank.nodes_s[0]
        fractional=(obs.times_s[:,None]+shifts[None,:]-bank.nodes_s[0])/step
        outputs.append(dict(label=label,phase=phase,point=xy,stage='postfit' if is_post else 'prefit',
            stationarity=first['stationarity'],score=first['objective'],
            minimum_time_to_interpolation_knot_s=float(np.min(abs(fractional-np.rint(fractional)))*step),
            finite_differences=differences))
    return outputs


def attribution():
    label,phase='N29','sigma2_60'
    _,obs,bank,prior,score=d.engine.CONTEXT[label]
    score=replace(score,relative_sigma_s=2.)
    paths=d.read(d.HERE/'profile_paths.json')['outputs']
    outputs=[]
    for path,arm in [(paths[0],'zero-c'),(paths[1],'fitted-c')]:
        region=d.read(d.region_path(d.source(label,phase),path['point'],25.))
        subset=bank.select(region['association']['selected_indices'])
        obj=d.run.BASE_NATIVE(obs,subset,prior,score,receiver_baseline_hz=np.asarray(region['calibration']['receiver_baseline_hz']))
        rows=[r for r in path['outputs'] if r['arm']==arm and r['step']!='release']
        endpoints=[]
        for row in [rows[0],rows[-1]]:
            v=np.asarray(row['vector']);value,gradient,terms=obj.evaluate(v)
            shifts=v[7]+obj.basis@v[8:]
            _,visible,_,_=d.run.engine.predict_orbits(subset,obs,prior,v[:2],shifts,derivatives=False)
            q=score.detection_budget/len(subset.numbers)
            lp0=-score.clutter_rate+visible.sum(axis=1)*np.log1p(-q)
            # The clutter constant cancels in the endpoint difference.
            reduced_nll=-lp0+np.log(-np.expm1(lp0))+np.log(terms.clutter_probability)
            endpoints.append((terms,reduced_nll))
        winner,truth=endpoints
        change=truth[1]-winner[1]
        np.testing.assert_allclose(change.sum(),rows[-1]['data_nll']-rows[0]['data_nll'],atol=1e-6,rtol=0)
        def groups(values):
            return sorted([dict(value=float(v),count=int(np.sum(values==v)),
                delta_nll=float(change[values==v].sum())) for v in np.unique(values)],key=lambda r:-r['delta_nll'])
        which=winner[0].responsibilities.argmax(axis=1)
        sat=np.asarray(subset.numbers)[which]
        strong=(winner[0].responsibilities.max(axis=1)>.5)&(truth[0].responsibilities.max(axis=1)>.5)
        outputs.append(dict(label=label,arm=arm,point=path['point'],delta_data_nll=float(change.sum()),
            receiver=groups(obs.receiver),rf_hz=groups(obs.rf_hz),winner_satellite=groups(sat),
            strong_windows=int(strong.sum()),changed_satellite_strong_windows=int(np.sum(strong&(which!=truth[0].responsibilities.argmax(axis=1)))),
            largest_window_contributions=sorted(change.tolist(),reverse=True)[:10]))
    return outputs


def main():
    for label in ['N29','N39','N49']:d.engine.CONTEXT[label]=d.run.data.load(label)
    result=dict(rejected_gradients=rejected_gradients(),hard60_attribution=attribution())
    d.engine.write(d.HERE/'score_inspection.json',result)
    for r in result['rejected_gradients']:
        print('GRADIENT',r['label'],r['point'],r['stage'],'stationarity',r['stationarity'],
              'nearest orbit knot seconds',r['minimum_time_to_interpolation_knot_s'])
        print(r['finite_differences'][:3])
    for r in result['hard60_attribution']:
        print('ATTRIBUTION',r['arm'],'receiver',r['receiver'],'RF',r['rf_hz'][:3],
              'satellites',r['winner_satellite'][:4], 'association_changes',r['changed_satellite_strong_windows'],r['strong_windows'])


if __name__=='__main__':main()
