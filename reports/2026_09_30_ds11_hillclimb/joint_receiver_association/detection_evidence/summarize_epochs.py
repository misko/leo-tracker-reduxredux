"""Freeze a descriptive 95%-same-pair timing gate on donor16 training only."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def quantile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values)*fraction)-1)] if values else None


def summarize(rows, threshold):
    out = dict(pair_counts=dict(Counter(r['label'] for r in rows)), windows=len({r['window_id'] for r in rows}))
    for label in ('same', 'different', 'unknown'):
        selected = [r for r in rows if r['label'] == label]
        values = [abs(r['delta_us']) for r in selected]
        out[label] = dict(n=len(values), absolute_delta_us={str(q):quantile(values, q) for q in (.1,.5,.9,.95,.99)}, gate_accept_fraction=sum(v <= threshold for v in values)/len(values) if values else None)
    return out


def main():
    paths = [HERE/f'epoch-pairs-{i:02d}.json' for i in (16,17)]
    docs = [json.loads(p.read_text()) for p in paths]
    for doc in docs:
        for path, sha in doc['sources'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
    training = [r for r in docs[0]['rows'] if r['training']]
    threshold = quantile([abs(r['delta_us']) for r in training if r['label']=='same'], .95)
    assert threshold is not None
    result = dict(threshold_us=threshold, rule='absolute wrapped epoch difference <= donor16 training same-label 95th percentile; no centering or validation tuning', inferred_labels=True, caveat='Pairs share candidates and windows; counts are not independent trials. Duplicate waveform candidates are retained. Labels derive from Doppler and do not authenticate satellite IDs.', splits={f"donor{doc['index']}-{split}":summarize([r for r in doc['rows'] if bool(r['training'])==flag], threshold) for doc in docs for split,flag in (('training',True),('held',False))}, sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths+[Path(__file__)]}, position_improvement_established=False)
    with (HERE/'epoch-summary.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
