"""Read saved producer RMS exactly; do not conflate profile and predictive RMS."""
import hashlib
import json
import math
from pathlib import Path

BASE=Path(__file__).resolve().parent;WORK=BASE/'work'
HELPER=Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/probe_ds23_frequency_events.py')
PREDICTIVE_HELPER=HELPER.with_name('probe_ds23_predictive_linear.py')
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    seal=BASE/'later_RF_seal.json'
    for p,h in read(seal)['files'].items():
        if sha(p)!=h:raise ValueError('bound saved output changed')
    rows=[]
    for case in (f'LATER4-{i:04}' for i in range(1,5)):
        path=WORK/'family_cavity/position'/(case+'.json');parent=read(path)
        entries=parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
        for arm,record in parent['policy_arms'].items():
            predictive=sum(len(e['observation_ids']) for e in entries)
            saved_predictive=record.get('predictive_points',record.get('additional_predictive_points'))
            if saved_predictive!=predictive:raise ValueError('saved predictive count differs')
            rows.append(dict(case=case,arm=arm,saved_curved_conditional_RMS_hz=record['RMS_hz'],
                active_curved_points=record['active_points'],predictive_points=predictive,
                full_VI_objective=record['negative_twice_elbo'],curved_VI_objective=record['curved_negative_twice_elbo'],
                full_likelihood_frequency_RMS_hz=None,
                full_likelihood_RMS_status='not_persisted; predictive raw residual arrays absent in saved summary',
                source_parent_path=str(path),source_parent_sha256=sha(path)))
    summary={}
    for arm in ('c0','fitted_c'):
        rr=[r for r in rows if r['arm']==arm];n=sum(r['active_curved_points'] for r in rr)
        summary[arm]=dict(mean_scan_curved_conditional_RMS_hz=sum(r['saved_curved_conditional_RMS_hz'] for r in rr)/len(rr),
            pooled_curved_conditional_RMS_hz=math.sqrt(sum(r['active_curved_points']*r['saved_curved_conditional_RMS_hz']**2 for r in rr)/n),
            active_curved_points=n,predictive_points=sum(r['predictive_points'] for r in rr))
    value=dict(rows=rows,summary=summary,source_helper=str(HELPER),source_helper_sha256=sha(HELPER),
        predictive_source_helper=str(PREDICTIVE_HELPER),predictive_source_helper_sha256=sha(PREDICTIVE_HELPER),
        producer_semantics='probe_ds23_frequency_events.summary line147 / probe_ds23_predictive_linear.refit line69: sqrt(mean(c[conditional_residual_hz][keep]**2))',
        curved_RMS_is_unweighted_by_power_or_Gamma=True,curved_only_even_when_predictive_likelihood_is_present=True,
        profile_RMS_not_summed=True,full_objective_includes_predictive_but_is_not_a_frequency_RMS=True,
        pooled_formula='sqrt(sum(n_curved_i * saved_RMS_i**2)/sum(n_curved_i))',
        baseline_RF_seal_sha256=sha(seal),new_fits_or_geometry_or_GPS_calls=0)
    with (BASE/'frequency_readback.json').open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
