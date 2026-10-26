"""Offline exact control strata, innovation and grid-origin diagnostics."""
import csv
import gzip
import json
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
def read(kind):
    with gzip.open(HERE/'outcomes'/(kind+'.json.gz'),'rt') as f:return json.load(f)
def write(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def upper95(k,n):
    if k==n:return 1.
    if not k:return 1-.05**(1/n)
    lo,hi=0.,1.
    for _ in range(80):
        p=(lo+hi)/2;cdf=sum(math.comb(n,j)*p**j*(1-p)**(n-j) for j in range(k+1))
        if cdf>.05:lo=p
        else:hi=p
    return (lo+hi)/2


def metrics(rows,name):
    e=[r['evaluation'][name] for r in rows];admit=[x for x in e if x['admitted']]
    return dict(n=len(rows),admitted=len(admit),admitted_within500=sum(x['admitted'] and abs(x['cfo_error_hz'])<=500 for x in e),
        all_within500=sum(abs(x['cfo_error_hz'])<=500 for x in e),all_within100=sum(abs(x['cfo_error_hz'])<=100 for x in e),
        carry_within500=sum(abs(x['carry_error_hz'])<=500 for x in e),
        admitted_gt1k=sum(abs(x['cfo_error_hz'])>1000 for x in admit),all_gt1k=sum(abs(x['cfo_error_hz'])>1000 for x in e),
        actual_CFO_RMSE_hz=float(np.sqrt(np.mean([x['cfo_error_hz']**2 for x in e]))),
        carry_RMSE_hz=float(np.sqrt(np.mean([x['carry_error_hz']**2 for x in e]))))


def main():
    signal=read('signal');null=read('null');wrong=read('wrong');s=signal['rows'];methods=['linear','quadratic_or_fallback','legacy_adapter_linear']
    primary=[r for r in s if r['db']==-12 and abs(r['timing_error_samples'])==.5]
    stress=[r for r in s if r['db']==-12 and abs(r['timing_error_samples'])==3.5]
    weak=[r for r in s if r['db']==-24];large=[r for r in primary if abs(r['donor_CFO_error_hz'])>500]
    strata=[]
    for edge in ['lower','upper']:
        for distinct in [False,True]:
            rows=[r for r in null['rows'] if r['edge']==edge and r['distinct_method_points']==distinct]
            values={}
            for m in methods:
                k=sum(r['result']['methods'][m]['admitted'] for r in rows)
                kp=sum(r['result']['methods'][m]['pilot_confirmed'] for r in rows)
                values[m]=dict(n=len(rows),admitted=k,pilot_confirmed=kp,upper95=upper95(k,len(rows)),pilot_upper95=upper95(kp,len(rows)))
            union=sum(any(r['result']['methods'][m]['admitted'] for m in methods) for r in rows)
            strata.append(dict(edge=edge,distinct_method_points=distinct,methods=values,union_admitted=union,union_upper95=upper95(union,len(rows))))
    primary_stats={m:metrics(primary,m) for m in methods};stress_stats={m:metrics(stress,m) for m in methods}
    screens={m:dict(primary_frequency_availability=primary_stats[m]['admitted_within500']/len(primary)>=.9,
        no_strong_admitted_gt1k=primary_stats[m]['admitted_gt1k']+stress_stats[m]['admitted_gt1k']==0,
        null_admission=all(x['methods'][m]['admitted']/32<=.05 and x['methods'][m]['upper95']<=.1 for x in strata),
        null_pilot=all(x['methods'][m]['pilot_confirmed']/32<=.05 and x['methods'][m]['pilot_upper95']<=.1 for x in strata)) for m in methods}
    weak_failures=[dict(trial=r['trial'],edge=r['edge'],timing_error_samples=r['timing_error_samples'],
        donor_CFO_error_hz=r['donor_CFO_error_hz'],evaluation=r['evaluation']) for r in weak
        if any(abs(r['evaluation'][m]['cfo_error_hz'])>1000 for m in methods)]
    summary=dict(schema='round2-timing-controls-summary/v2',signal_n=len(s),null_n=len(null['rows']),wrong_n=len(wrong['rows']),
        primary_strong=primary_stats,strong_stress=stress_stats,weak={m:metrics(weak,m) for m in methods},
        large_prior_error_primary={m:metrics(large,m) for m in methods},null_strata=strata,screening=screens,
        operational_screens_pass=all(screens['quadratic_or_fallback'].values()),weak_catastrophes=weak_failures,
        wrong={m:dict(n=len(wrong['rows']),pilot_confirmed=sum(r['result']['methods'][m]['pilot_confirmed'] for r in wrong['rows']),
            admitted=sum(r['result']['methods'][m]['admitted'] for r in wrong['rows'])) for m in methods},
        seconds=dict(signal=signal['seconds'],null=null['seconds'],wrong=wrong['seconds']),
        controls_share_method_points_in_signal=True,primary_acceptance_never_selects_best_method=True,
        no_raw_development_scored_at_summary=True,uncertainty_qualified=False)
    write('control_summary.json',summary)
    rows=[]
    for kind,data in [('signal',signal),('null',null),('wrong',wrong)]:
        for r in data['rows']:
            for name,item in r['result']['methods'].items():
                e=r['evaluation'].get(name,{})
                rows.append(dict(kind=kind,trial=r['trial'],edge=r['edge'],db=r['db'],true_rate_hz_s=r['true_rate_hz_s'],
                    timing_error_samples=r['timing_error_samples'],donor_CFO_error_hz=r['donor_CFO_error_hz'],
                    distinct_method_points=r['distinct_method_points'],method=name,owner_id=r['result']['owner_id'],
                    target_sha256=r['target_sha256'],admitted=item['admitted'],pilot_confirmed=item['pilot_confirmed'],
                    margin=item['score']['margin'],CFO_hz=item['score']['tracking_cfo_hz'],innovation_hz=item['frequency_innovation_hz'],
                    cfo_error_hz=e.get('cfo_error_hz',''),carry_error_hz=e.get('carry_error_hz',''),
                    grid_origin_modulo_bin_hz=item['grid_origin_modulo_bin_hz']))
    with (HERE/'control_trials.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(dict(primary=primary_stats['quadratic_or_fallback'],stress=stress_stats['quadratic_or_fallback'],
        weak=summary['weak']['quadratic_or_fallback'],large_prior_error=summary['large_prior_error_primary']['quadratic_or_fallback'],
        screen=summary['operational_screens_pass'],seconds=summary['seconds']),indent=2),flush=True)


if __name__=='__main__':main()
