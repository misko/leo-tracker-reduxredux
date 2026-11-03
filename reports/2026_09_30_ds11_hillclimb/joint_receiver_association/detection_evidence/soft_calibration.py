"""Window-balanced, smoothed timing-event calibration from earlier data."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def signature(row):
    # Exact repeated waveform estimates must not multiply evidence.
    return (row['delta_us'], *row['cfo_hz'], *row['exact'], *row['control'])


def windows(rows, threshold):
    grouped = defaultdict(dict)
    for row in rows:
        if row['label'] in ('same', 'different'):
            grouped[row['window_id'], row['label']][signature(row)] = abs(row['delta_us']) <= threshold
    return [(label, sum(events.values())/len(events)) for (_, label), events in sorted(grouped.items())]


def fit(rows, threshold):
    grouped = windows(rows, threshold)
    # Jeffreys smoothing keeps both match and mismatch probabilities nonzero.
    return {label:(.5+sum(y for lab,y in grouped if lab==label))/(1+sum(lab==label for lab,y in grouped)) for label in ('same','different')}


def score(rows, threshold, probabilities):
    out = {}
    for label in ('same', 'different'):
        selected = [y for lab,y in windows(rows, threshold) if lab==label]
        p = probabilities[label]
        out[label] = dict(windows=len(selected), mean_hit=sum(selected)/len(selected) if selected else None, mean_log_probability=sum(y*math.log(p)+(1-y)*math.log1p(-p) for y in selected)/len(selected) if selected else None)
    return out


def main():
    summary = HERE/'epoch-summary.json'
    threshold = json.loads(summary.read_text())['threshold_us']
    paths = [HERE/f'epoch-pairs-{i:02d}.json' for i in (16,17)]
    docs = [json.loads(p.read_text()) for p in paths]
    train = [r for r in docs[0]['rows'] if r['training']]
    probabilities = fit(train, threshold)
    result = dict(threshold_us=threshold, probabilities=probabilities, event_log_ratio={'hit':math.log(probabilities['same']/probabilities['different']), 'miss':math.log((1-probabilities['same'])/(1-probabilities['different']))}, splits={f"donor{doc['index']}-{split}":score([r for r in doc['rows'] if bool(r['training'])==flag], threshold, probabilities) for doc in docs for split,flag in (('training',True),('held',False))}, inferred_labels=True, scope='family2 only; each label/window total weight one after exact waveform-pair deduplication; still temporally correlated', sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths+[summary,Path(__file__)]})
    with (HERE/'soft-calibration.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
