"""Independent saved-number summary/predicate check, without model evaluation."""

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
SYNTHETIC=HERE.parent/'synthetic'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def main():
    seal=read(SYNTHETIC/'scientific_seal.json')
    for path,digest in seal['files'].items():
        assert sha(path)==digest,path
    summary=read(SYNTHETIC/'summary.json');replay=read(SYNTHETIC/'gate_replay.json')
    with (SYNTHETIC/'per_fit.csv').open() as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==24 and summary['completed']==24 and summary['failures']==0
    for exported in summary['summaries']:
        selected=[row for row in rows if row['arm']==exported['arm'] and
            (row['variant']=='noiseless_null' if exported['mode']=='noiseless_null' else row['variant'].startswith('stochastic'))]
        values=[float(row['error_km']) for row in selected]
        independent=dict(fits=len(values),qualified=sum(row['qualified']=='True' for row in selected),
            mean_error_km=statistics.mean(values),median_error_km=statistics.median(values),
            minimum_error_km=min(values),maximum_error_km=max(values))
        for key,value in independent.items():assert math.isclose(value,exported[key],abs_tol=1e-12,rel_tol=0),(key,value,exported[key])
    count=0;counts={}
    for row in replay['rows']:
        counts.setdefault(row['variant'],dict(curved=Counter(),predictive=Counter()))
        for role in ('curved','predictive'):
            for track in row[role]:
                failures={key for key,passed in track['checks'].items() if not passed}
                if role=='curved':
                    assert track['before_support_passed']==all(track['checks'].values())
                    if track['before_support_passed'] and not track['after_support_passed']:
                        failures.add('owner_support_cascade')
                    screens=(('profile_',track['profile_noise']),('conditional_',track['conditional_noise']))
                    assert track['checks']['profile_RMS']==(track['profile_RMS_hz']<=450)
                    assert track['checks']['profile_bias']==(abs(track['profile_bias_hz'])<=3000)
                    assert track['checks']['conditional_RMS']==(track['conditional_RMS_hz']<=450)
                else:
                    screens=(('predictive_',track['noise']),)
                    assert track['checks']['RMS']==(track['RMS_hz']<=450)
                    assert track['checks']['bias']==(abs(track['bias_hz'])<=3000)
                for prefix,screen in screens:
                    thresholds=dict(mean_z=3.,slope_z=3.,quadratic_bic_gain=10.,maximum_step_z=4.,lag1_acf=4/math.sqrt(track['points']))
                    for key,limit in thresholds.items():
                        actual=abs(screen[key])<=limit if key=='lag1_acf' else screen[key]<=limit
                        assert track['checks'][prefix+key]==actual
                assert failures==set(track['failed_predicates'])
                counts[row['variant']][role].update(failures);count+=1
    counts={variant:{role:dict(counter) for role,counter in roles.items()} for variant,roles in counts.items()}
    assert counts==summary['gate_failure_counts']
    result=dict(all_passed=True,scope='independent saved-number aggregates and explicit gate-threshold bookkeeping; no propagation or position fitting',
        rows=24,gate_track_records=count,summary_aggregates_checked=len(summary['summaries']),
        scientific_seal_sha256=sha(SYNTHETIC/'scientific_seal.json'),
        summary_sha256=sha(SYNTHETIC/'summary.json'),gate_replay_sha256=sha(SYNTHETIC/'gate_replay.json'),
        source_sha256=sha(__file__),position_fits=0,
        finding='All16 stochastic fits qualify; all8 noiseless fits have millimetric errors but fail relative whiteness gates and support cascades. No noiseless qualification claim or gate relaxation justified.')
    with (HERE/'synthetic_readonly_check.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
