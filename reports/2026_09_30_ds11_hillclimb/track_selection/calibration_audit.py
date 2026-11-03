"""Descriptive frozen-model probability audit; no coefficient or gate tuning."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import expit
from model import arrays, design

HERE = Path(__file__).resolve().parent

def summarize_groups(keys, probabilities, labels, weights):
    groups = defaultdict(list)
    for i, key in enumerate(keys):
        groups[key].append(i)
    result = []
    for key, indices in sorted(groups.items()):
        ix = np.array(indices)
        predicted = float(np.average(probabilities[ix], weights=weights[ix]))
        observed = float(np.average(labels[ix], weights=weights[ix]))
        result.append(dict(group=key, candidates=len(ix), weight=float(weights[ix].sum()),
            predicted_retention=predicted, observed_retention=observed,
            observed_minus_predicted=observed-predicted,
            brier=float(np.average((probabilities[ix]-labels[ix])**2, weights=weights[ix]))))
    return result

def probability_bins(probabilities):
    if not np.isfinite(probabilities).all() or np.any((probabilities<0)|(probabilities>1)):
        raise ValueError('probabilities must be finite and inside [0,1]')
    return np.minimum((probabilities*10).astype(int),9).tolist()

def main():
    path = HERE/'qualified-summary.json'
    fit = json.loads(path.read_text())
    for source, sha in fit['sources'].items():
        assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==sha, source
    outputs = []
    for index in (16,17):
        doc = json.loads((HERE/f'donor-{index:02d}.json').read_text())
        # Donor16 held visits were not used to fit; donor17 remains the separate
        # recording. All candidates retained in each assessment panel.
        rows = [r for r in doc['rows'] if not r['training']] if index==16 else doc['rows']
        models = {}
        for name, strength in (('receiver_rf',False), ('detector_scores',True)):
            f,y,w = arrays(rows,strength)
            m = fit['fits'][name]
            p = expit(design(f,np.array(m['mean']),np.array(m['scale']))@np.array(m['beta']))
            overall = summarize_groups(['all']*len(rows),p,y,w)[0]
            bins = summarize_groups(probability_bins(p),p,y,w)
            by_receiver_rf = summarize_groups([f"rx{r['rx']}:{r['rf_hz']:.0f}" for r in rows],p,y,w)
            ece = sum(b['weight']*abs(b['observed_minus_predicted']) for b in bins)/w.sum()
            models[name] = dict(overall=overall,bins=bins,receiver_rf=by_receiver_rf,
                weighted_bin_absolute_calibration_error=float(ece),
                worst_receiver_rf_absolute_gap=max(abs(g['observed_minus_predicted']) for g in by_receiver_rf))
        outputs.append(dict(index=index,split='within_record_held' if index==16 else 'separate_record',models=models))
    paths = [path, HERE/'model.py', Path(__file__),HERE/'test_calibration_audit.py',
             HERE/'donor-16.json',HERE/'donor-17.json']
    result = dict(rows=outputs,descriptive_only=True,model_refitted=False,
        ds11_position_fits=0,uncertainty_intervals_established=False,
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with (HERE/'calibration-audit.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    for row in outputs:
        print(json.dumps(dict(index=row['index'],models={k:{n:v for n,v in m.items() if n not in ('bins','receiver_rf')} for k,m in row['models'].items()})))

if __name__=='__main__':main()
