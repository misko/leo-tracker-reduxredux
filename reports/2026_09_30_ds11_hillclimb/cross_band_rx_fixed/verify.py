"""Independently replay scalar corrections and check source/score accounting."""
import hashlib
import json
import math
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
PERIOD = 1/4.4e-6
def wrap(x):
    return (x+PERIOD/2)%PERIOD-PERIOD/2


def main():
    path = HERE/'outcome.json'
    data = json.loads(path.read_text())
    for name,expected in data['sources'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected
    screen = json.loads((HILL/'cross_band_rx_drift/outcome.json').read_text())
    plan = json.loads((HILL.parent/'2026_09_30_ds11_single10/plan.json').read_text())
    largest = 0.
    checked = 0
    for row in data['rows']:
        entry = plan['inputs'][row['index']]
        artifact = next(a for a in entry['artifacts'] if a['kind']=='observations')
        tracks = {t['track_id']:t for t in json.loads(Path(artifact['path']).read_text())['tracks']}
        seen = set()
        excluded = {t for pair in row['excluded_conflicting_pairs'] for t in pair}
        for correction in row['corrections']:
            assert not seen.intersection(correction['tracks']) and not excluded.intersection(correction['tracks'])
            seen.update(correction['tracks'])
            pair = next(p for p in screen['rows'] if p['scan_index']==row['index'] and p['tracks']==correction['tracks'])
            a,b = (tracks[t] for t in correction['tracks'])
            train = []
            for v in sorted(set(a['visits']) & set(b['visits'])):
                if a['visits'].count(v)!=1 or b['visits'].count(v)!=1:
                    continue
                i,j = a['visits'].index(v),b['visits'].index(v)
                if not (a['training_mask'][i] and b['training_mask'][j]) or abs(a['times_s'][i]-b['times_s'][j])>1e-4:
                    continue
                train.append(((a['times_s'][i]+b['times_s'][j])/2,
                              wrap((a['measured_hz'][i]-b['measured_hz'][j])*a['rf_hz']/11.2e9)))
            values = sorted(wrap(y) for t,y in train)
            center = min(values,key=lambda x:(sum(abs(wrap(y-x)) for y in values),x))
            slope,lower,upper = pair['fit']
            origin = median(t for t,y in train)
            constant = median(center+wrap(y-center) for t,y in train)
            intercept = median(center+wrap(y-center)-slope*(t-origin) for t,y in train)
            for track,key in ((a,'canonical_delta_rx1'),(b,'canonical_delta_rx0')):
                saved = correction[key]
                assert len(saved)==len(track['times_s'])
                for t,actual in zip(track['times_s'],saved):
                    expected = (intercept+slope*(t-origin)-constant)*11.2e9/track['rf_hz'] if lower<=t<=upper else 0.
                    largest = max(largest,abs(actual-expected))
                    checked += 1
        assert abs(row['baseline_replay_error'])<1e-6
        for name,arm in row['arms'].items():
            assert abs(arm['held_gain']-(arm['held']-row['arms']['baseline']['held']))<1e-9
            assert arm['map_changes']==sum(a!=b for a,b in zip(arm['map'],row['arms']['baseline']['map']))
    for name,summary in data['summary'].items():
        gains = [r['arms'][name]['held_gain'] for r in data['rows']]
        assert abs(summary['total_gain']-math.fsum(gains))<1e-9
        assert summary['wins']==sum(g>0 for g in gains)
        assert summary['gate_pass']==(sum(g>0 for g in gains)>=5 and sum(gains)>0 and median(gains)>0)
    assert largest<1e-8
    result = dict(source_and_correction_verification_pass=True,checked_corrections=checked,
                  maximum_correction_discrepancy_hz=largest,independently_replays_likelihood=False,
                  outcome_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
