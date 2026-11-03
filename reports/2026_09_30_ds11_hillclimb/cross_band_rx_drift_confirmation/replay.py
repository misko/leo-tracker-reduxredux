"""Scalar replay of both panels without importing either numerical runner."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
PERIOD = 1 / 4.4e-6


def wrap(x):
    return (x+PERIOD/2) % PERIOD-PERIOD/2


def medoid(values):
    values = sorted(wrap(x) for x in values)
    return min(values, key=lambda x:(sum(abs(wrap(y-x)) for y in values), x))


def main():
    reports = []
    bindings = {str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for folder in ('cross_band_rx_drift', 'cross_band_rx_drift_confirmation'):
        path = HILL/folder/'outcome.json'
        data = json.loads(path.read_text())
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name, expected in data['sources'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected
        plan_path = HILL.parent/'2026_09_30_ds11_single10/plan.json'
        plan = json.loads(plan_path.read_text())
        paired = []
        docs = {}
        for row in data['rows']:
            index = row['scan_index']
            if index not in docs:
                artifact = next(a for a in plan['inputs'][index]['artifacts'] if a['kind']=='observations')
                raw = Path(artifact['path']).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == artifact['sha256'].removeprefix('sha256:')
                docs[index] = {t['track_id']:t for t in json.loads(raw)['tracks']}
            a,b = (docs[index][tid] for tid in row['tracks'])
            assert a['receiver_id']==1 and b['receiver_id']==0 and a['rf_hz']==b['rf_hz']
            ac,bc = Counter(a['visits']),Counter(b['visits'])
            ai = {v:i for i,v in enumerate(a['visits']) if ac[v]==1}
            bi = {v:i for i,v in enumerate(b['visits']) if bc[v]==1}
            train, held = [], []
            for v in sorted(ai.keys() & bi.keys()):
                i,j = ai[v],bi[v]
                if abs(a['times_s'][i]-b['times_s'][j])>1e-4 or a['training_mask'][i]!=b['training_mask'][j]:
                    continue
                datum = ((a['times_s'][i]+b['times_s'][j])/2,
                         wrap((a['measured_hz'][i]-b['measured_hz'][j])*a['rf_hz']/11.2e9))
                (train if a['training_mask'][i] else held).append(datum)
            assert len(train)==row['training_rows'] and len(held)==row['held_rows']
            paired.append((row,train,held))
        largest = 0.
        applied_total = 0
        for row,train,held in paired:
            by_source = defaultdict(list)
            for other,otrain,_ in paired:
                if other['scan_index']==row['scan_index'] and other['norad']!=row['norad']:
                    by_source[other['norad']].append((median(t for t,y in otrain),medoid([y for t,y in otrain])))
            assert len(by_source)==row['donor_count']
            centers = [(median(t for t,y in v),medoid([y for t,y in v])) for v in by_source.values()]
            center = medoid([y for t,y in centers])
            centers = [(t,center+wrap(y-center)) for t,y in centers]
            slopes = [(b[1]-a[1])/(b[0]-a[0]) for i,a in enumerate(centers) for b in centers[i+1:] if abs(b[0]-a[0])>=1]
            slope = median(slopes)
            expected = [slope,min(t for t,y in centers),max(t for t,y in centers)] if len(centers)>=3 and abs(slope)<=20 else None
            assert expected is not None and row['fit'] is not None
            assert max(abs(a-b) for a,b in zip(expected,row['fit']))<1e-9
            center = medoid([y for t,y in train])
            unwrapped = [(t,center+wrap(y-center)) for t,y in train]
            constant = median(y for t,y in unwrapped)
            origin = median(t for t,y in train)
            intercept = median(y-slope*(t-origin) for t,y in unwrapped)
            changed = 0
            for k,(t,y) in enumerate(held):
                prediction = intercept+slope*(t-origin) if expected[1]<=t<=expected[2] else constant
                changed += prediction!=constant
                largest = max(largest,abs(abs(wrap(y-constant))-row['constant_absolute_errors_hz'][k]),
                              abs(abs(wrap(y-prediction))-row['drift_absolute_errors_hz'][k]))
            assert changed==row['applied_rows']
            applied_total += changed
        assert largest<1e-8
        reports.append(dict(panel=folder, pairs=len(paired),
                            held_rows=sum(len(v) for _,_,v in paired),
                            applied_rows=applied_total, maximum_error_discrepancy_hz=largest))
    result = dict(independent_donor_fit_and_measurement_replay_pass=True, panels=reports, sources=bindings)
    (HERE/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
