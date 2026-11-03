"""Frozen calibration and independent-record selection transfer assessment."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize
from model import arrays, standardize, design, objective, log_probability

HERE = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)

def export():
    def launch(index):
        started = time.monotonic()
        with (HERE/f'donor-{index:02d}.log').open('x') as log:
            result = subprocess.run(['timeout', '--kill-after=5s', '90s', sys.executable,
                str(HERE/'export.py'), str(index)], stdout=log, stderr=subprocess.STDOUT)
        receipt = dict(index=index, exit_code=result.returncode, elapsed_s=time.monotonic()-started,
                       export_sha256=digest(HERE/'export.py'), protocol_sha256=digest(HERE/'PROTOCOL.md'))
        write(HERE/f'donor-{index:02d}.receipt.json', receipt)
        print(json.dumps(receipt), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(launch, (16, 17)))

def fit():
    docs = []; sources = {}
    for index in (16,17):
        path = HERE/f'donor-{index:02d}.json'
        doc = json.loads(path.read_text())
        for name, expected in doc['sources'].items():
            assert digest(name)==expected, name
        sources.update(doc['sources']); sources[str(path)] = digest(path)
        receipt_path = HERE/f'donor-{index:02d}.receipt.json'
        receipt = json.loads(receipt_path.read_text())
        assert receipt['exit_code']==0 and receipt['export_sha256']==digest(HERE/'export.py')
        sources[str(receipt_path)] = digest(receipt_path)
        docs.append(doc)
    train = [r for r in docs[0]['rows'] if r['training']]
    validation = docs[1]['rows']
    fits = {}; scores = {}
    for name, strength in (('receiver_rf',False), ('detector_scores',True)):
        features, y, weights = arrays(train, strength)
        mean, scale = standardize(features, weights)
        x = design(features, mean, scale)
        opt = minimize(objective, np.zeros(x.shape[1]), args=(x,y,weights), jac=True,
            method='BFGS', options=dict(maxiter=200, gtol=1e-7))
        _, gradient = objective(opt.x,x,y,weights)
        fd = []
        for delta in np.eye(len(opt.x))*1e-5:
            fd.append((objective(opt.x+delta,x,y,weights)[0]-objective(opt.x-delta,x,y,weights)[0])/2e-5)
        discrepancy = float(np.max(np.abs(gradient-fd)))
        maximum = float(np.max(np.abs(gradient)))
        qualified = bool(opt.success and np.isfinite(opt.x).all() and maximum<=1e-5 and discrepancy<=1e-5)
        fits[name] = dict(beta=opt.x.tolist(), mean=mean.tolist(), scale=scale.tolist(), qualified=qualified,
            success=bool(opt.success), message=str(opt.message), gradient_max_abs=maximum, gradient_audit_error=discrepancy)
        f, v, w = arrays(validation, strength)
        scores[name] = log_probability(opt.x,design(f,mean,scale),v)
    gain = scores['detector_scores']-scores['receiver_rf']
    visits = []
    for visit in sorted({r['visit'] for r in validation}):
        mask = np.array([r['visit']==visit for r in validation])
        visits.append(dict(visit=visit, gain=float(np.average(gain[mask], weights=w[mask]))))
    mean_gain = float(np.average(gain, weights=w))
    wins = sum(v['gain']>0 for v in visits)
    for path in (Path(__file__), HERE/'model.py', HERE/'test_model.py', HERE/'PROTOCOL.md'):
        sources[str(path)] = digest(path)
    result = dict(fits=fits, training_rows=len(train), validation_rows=len(validation),
        validation_mean_log_probability_gain=mean_gain, validation_visit_wins=wins,
        validation_visits=len(visits), visit_results=visits,
        baseline_mean_log_probability=float(np.average(scores['receiver_rf'],weights=w)),
        score_model_mean_log_probability=float(np.average(scores['detector_scores'],weights=w)),
        gate_pass=all(f['qualified'] for f in fits.values()) and mean_gain>.01 and wins>len(visits)/2,
        reference_used=False, ds11_position_fits=0, sources=sources)
    write(HERE/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','visit_results')}, indent=2))

if __name__=='__main__':
    dict(export=export, fit=fit)[sys.argv[1]]()
