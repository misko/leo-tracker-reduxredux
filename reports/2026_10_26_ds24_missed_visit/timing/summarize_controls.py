"""Offline compact control diagnostics; frozen inference remains unchanged."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
def read(name):
    with gzip.open(HERE/'outcomes'/(name+'.json.gz'),'rt') as f:return json.load(f)
def write(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def upper95(k,n):
    if k==n:return 1.
    if not k:return 1-.05**(1/n)
    lo,hi=0.,1.
    for _ in range(80):
        p=(lo+hi)/2;cdf=sum(math.comb(n,j)*p**j*(1-p)**(n-j) for j in range(k+1))
        if cdf>.05:lo=p
        else:hi=p
    return (lo+hi)/2


def result_counts(rows,method):
    items=[r['result'].get(method) for r in rows];evaluations=[r.get('evaluation',{}).get(method,{}) for r in rows]
    n=len(rows);confirmed=sum(bool(i and i['evaluation']['pilot_confirmed']) for i in items)
    admitted=sum(bool(i and i['evaluation']['admitted']) for i in items)
    return dict(n=n,complete=sum(bool(i) for i in items),pilot_confirmed=confirmed,admitted=admitted,
        accurate100=sum(bool(e.get('accurate100',False)) for e in evaluations),
        accurate500=sum(bool(e.get('accurate500',False)) for e in evaluations),
        correct_timing=sum(bool(e.get('correct_timing',False)) for e in evaluations),
        admitted_gt1k_errors=sum(bool(e.get('admitted',False) and abs(e['cfo_error_hz'])>1000) for e in evaluations),
        confirmed_upper95=upper95(confirmed,n),admitted_upper95=upper95(admitted,n))


def main():
    sources={kind:read(kind) for kind in ['signal','boundary','null','wrong']}
    signals=sources['signal']['rows'];nulls=sources['null']['rows'];methods=['point','search']
    strong=[r for r in signals if r['db']==-12]
    strata=[]
    for edge in ['lower','upper']:
        for db in [-12,-18,-24]:
            for forecast in ['zero_rate_fallback','rate_propagated']:
                rows=[r for r in signals if r['edge']==edge and r['db']==db and r['forecast']==forecast]
                strata.append(dict(edge=edge,db=db,forecast=forecast,methods={m:result_counts(rows,m) for m in methods}))
    null_stats=[]
    for edge in ['lower','upper']:
        for modes in [1,8]:
            rows=[r for r in nulls if r['edge']==edge and r['modes']==modes]
            values={m:result_counts(rows,m) for m in methods}
            for name in ['pilot_confirmed','admitted']:
                k=sum(any(bool(r['result'].get(m) and r['result'][m]['evaluation'][name]) for m in methods) for r in rows)
                values['union_'+name]=dict(n=len(rows),count=k,upper95=upper95(k,len(rows)))
            null_stats.append(dict(edge=edge,modes=modes,methods=values))
    strong_stats={m:result_counts(strong,m) for m in methods}
    screen={m:dict(strong_n=len(strong),strong_accuracy_pass=strong_stats[m]['accurate500']/len(strong)>=.9,
        strong_no_admitted_gt1k=strong_stats[m]['admitted_gt1k_errors']==0,
        null_pilot_pass=all(x['methods'][m]['pilot_confirmed']/32<=.05 and x['methods'][m]['confirmed_upper95']<=.1 for x in null_stats),
        null_admission_pass=all(x['methods'][m]['admitted']/32<=.05 and x['methods'][m]['admitted_upper95']<=.1 for x in null_stats)) for m in methods}
    summary=dict(schema='missed-visit-controls-summary/v1',protocol_sha256=sha(HERE/'protocol.json'),
        exact_counts={kind:len(value['rows']) for kind,value in sources.items()},
        seconds={kind:value['seconds'] for kind,value in sources.items()},
        strong=strong_stats,signal_strata=strata,
        by_strength={str(db):{m:result_counts([r for r in signals if r['db']==db],m) for m in methods} for db in [-12,-18,-24]},
        by_true_rate={str(rate):{m:result_counts([r for r in signals if r['true_rate_hz_s']==rate],m) for m in methods} for rate in [-2000.,2000.]},
        by_forecast={f:{m:result_counts([r for r in signals if r['forecast']==f],m) for m in methods} for f in ['zero_rate_fallback','rate_propagated']},
        null_strata=null_stats,boundary={m:result_counts(sources['boundary']['rows'],m) for m in methods},
        wrong_signal={m:result_counts(sources['wrong']['rows'],m) for m in methods},
        screening=screen,independent_draws_per_signal_row=True,
        no_raw_panel_scored=True,uncertainty_qualified=False,
        outcome_hashes={kind:sha(HERE/'outcomes'/(kind+'.json.gz')) for kind in sources})
    write('control_summary.json',summary)
    compact=[]
    for kind,value in sources.items():
        for r in value['rows']:
            for method in methods:
                item=r['result'].get(method);e=r.get('evaluation',{}).get(method,{})
                compact.append(dict(kind=kind,trial=r['trial'],edge=r['edge'],modes=r.get('modes',1),
                    db=r.get('db',''),timing_offset_samples=r.get('timing_offset_samples',''),
                    true_rate_hz_s=r.get('true_rate_hz_s',''),donor_error_hz=r.get('donor_error_hz',''),
                    forecast=r.get('forecast',''),method=method,owner_id=r['result']['owner_id'],
                    target_sha256=r['target_sha256'],complete=bool(item),
                    pilot_confirmed=bool(item and item['evaluation']['pilot_confirmed']),
                    admitted=bool(item and item['evaluation']['admitted']),
                    timing_error_samples=e.get('timing_error_samples',''),cfo_error_hz=e.get('cfo_error_hz',''),
                    selected_mode=item['selected']['mode_index'] if item else '',
                    selected_offset_samples=item['selected']['score']['offset_samples'] if item else '',
                    search_margin=item['selected']['score']['margin'] if item else '',
                    confirmation_margin=item['confirmation']['margin'] if item else '',
                    search_frames=item['selected']['score']['frames'] if item else '',
                    confirmation_frames=item['confirmation']['frames'] if item else '',
                    full_search_exposure=len(r['result']['exposure']),
                    selection_receipt_sha256=r['result'].get('selection_receipt',{}).get('selection_sha256','')))
    with (HERE/'control_trials.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
    # Frozen outcome sources remain local; compact table keeps every trial.
    print(json.dumps(dict(exact_counts=summary['exact_counts'],seconds=summary['seconds'],strong=strong_stats,screening=screen,
        null=[dict(edge=x['edge'],modes=x['modes'],point=x['methods']['point']['pilot_confirmed'],search=x['methods']['search']['pilot_confirmed']) for x in null_stats]),indent=2),flush=True)


if __name__=='__main__':main()
