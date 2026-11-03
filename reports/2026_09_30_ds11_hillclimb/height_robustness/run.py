"""Bounded hypothetical heights; no reference-error or height selection."""
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
spec = importlib.util.spec_from_file_location('fixed_height_diagnostic', HILL/'fixed_height/model.py')
fixed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixed)
fast = fixed.physical.fast
BOUNDS = [(-12, 12), (-12, 12), (-5, 5)]

def read(path):
    return json.loads(Path(path).read_text())

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)

def verify(plan):
    for path, expected in plan['sources'].items():
        assert digest(path) == expected, path

def select(results):
    valid = [r for r in results if r is not None and r['qualified']]
    return max(valid, key=lambda r: r['score']) if valid else None

def prepare():
    base = HILL.parent/'2026_09_30_ds11_single10'
    original = read(base/'plan.json')
    sources = dict(read(HILL/'fixed_height/preflight.json')['sources'])
    jobs = []
    for index in (0, 16):
        control_path = base/f'runs/{index:02d}_iid.json'
        control = read(control_path)['selected']
        assert control['qualified']
        sources[str(control_path)] = digest(control_path)
        for height in (-50, 0, 50):
            for seed in (control['x'], [0., 0., 0.]):
                jobs.append(dict(index=index, height_m=height, seed=seed))
    for path in (Path(__file__), HERE/'test_run.py', HERE/'PROTOCOL.md',
                 HILL/'fixed_height/compass_antenna_evidence.json'):
        sources[str(path)] = digest(path)
    plan = dict(config=original['config'], inputs=original['inputs'], jobs=jobs,
                sources=sources, reference_used=False, height_selected=False)
    verify(plan)
    write(HERE/'plan.json', plan)
    print(json.dumps(dict(jobs=len(jobs), plan_sha256=digest(HERE/'plan.json'))))

def fit(number):
    start = time.monotonic()
    plan = read(HERE/'plan.json'); verify(plan)
    job = plan['jobs'][number]
    doc = fast.load_documents(dict(config=plan['config'], inputs=[plan['inputs'][job['index']]]))[0]
    model = fixed.Model(doc, plan['config'], job['height_m'])
    def objective(x):
        result = model.evaluate(x)
        return -result['score'], -result['gradient']
    opt = minimize(objective, job['seed'], jac=True, method='L-BFGS-B', bounds=BOUNDS,
                   options=dict(maxiter=100, maxfun=160, ftol=1e-13, gtol=1e-6, maxls=25))
    result = model.evaluate(opt.x)
    fd = []
    for axis, step in enumerate((1e-3, 1e-3, 1e-4)):
        delta = np.eye(3)[axis]*step
        fd.append((model.evaluate(opt.x+delta, False)['score']-model.evaluate(opt.x-delta, False)['score'])/(2*step))
    error = float(np.max(np.abs(result['gradient']-fd)))
    maximum = float(np.max(np.abs(result['gradient'])))
    boundary = any(min(x-lo, hi-x)<.001 for x, (lo, hi) in zip(opt.x, BOUNDS))
    qualified = bool(opt.success and not boundary and np.isfinite(opt.x).all()
                     and np.isfinite(result['score']) and maximum<=.01 and error<=.02)
    labels = []
    for track in doc['tracks']:
        pred, visible = model.prediction(track, opt.x)
        train, _, audits, _ = fast.profile(track['y'][None, :]-pred, track['mask'])
        assert all(a['converged'] for a in audits)
        labels.append(int(np.argmax(np.where(visible, train, -np.inf))))
    write(HERE/f'runs/{number:02d}.json', dict(job=job, x=opt.x.tolist(), score=result['score'],
          qualified=qualified, success=bool(opt.success), message=str(opt.message), boundary=boundary,
          gradient_max_abs=maximum, finite_difference_error=error, map_indices=labels,
          elapsed_s=time.monotonic()-start, plan_sha256=digest(HERE/'plan.json')))

def batch():
    plan = read(HERE/'plan.json'); verify(plan)
    (HERE/'runs').mkdir(exist_ok=True)
    def launch(number):
        stem = HERE/f'runs/{number:02d}'
        started = time.monotonic()
        with stem.with_suffix('.log').open('x') as log:
            result = subprocess.run(['timeout', '--kill-after=5s', '90s', sys.executable,
                str(Path(__file__)), 'fit', str(number)], stdout=log, stderr=subprocess.STDOUT)
        write(stem.with_suffix('.receipt.json'), dict(exit_code=result.returncode,
              wall_s=time.monotonic()-started, plan_sha256=digest(HERE/'plan.json')))
        print(json.dumps(dict(job=number, exit_code=result.returncode)), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(launch, range(len(plan['jobs']))))

def summarize():
    plan = read(HERE/'plan.json'); verify(plan)
    results = []; sources = dict(plan['sources'])
    for number, job in enumerate(plan['jobs']):
        rp = HERE/f'runs/{number:02d}.receipt.json'
        receipt = read(rp); sources[str(rp)] = digest(rp)
        assert receipt['plan_sha256'] == digest(HERE/'plan.json')
        result = None
        if receipt['exit_code'] == 0:
            path = HERE/f'runs/{number:02d}.json'
            result = read(path); sources[str(path)] = digest(path)
            assert result['job'] == job and result['plan_sha256'] == receipt['plan_sha256']
        results.append(result)
    rows = []
    for index in (0, 16):
        selected = {h: select([r for r in results if r and r['job']['index']==index
                              and r['job']['height_m']==h]) for h in (-50, 0, 50)}
        zero = selected[0]
        for h, result in selected.items():
            row = dict(index=index, height_m=h, selected=result)
            if result and zero:
                delta = np.array(result['x'])-zero['x']
                row.update(horizontal_displacement_m=float(np.linalg.norm(delta[:2])*1000),
                           timing_shift_s=float(delta[2]),
                           changed_map_tracks=sum(a!=b for a,b in zip(result['map_indices'], zero['map_indices'])),
                           total_tracks=len(result['map_indices']))
            rows.append(row)
    sources[str(HERE/'plan.json')] = digest(HERE/'plan.json')
    outcome = dict(rows=rows, attempted=len(results), qualified=sum(bool(r and r['qualified']) for r in results),
                   reference_used=False, height_selected=False, accuracy_improvement_established=False, sources=sources)
    write(HERE/'summary.json', outcome)
    print(json.dumps({k:v for k,v in outcome.items() if k!='sources'}, indent=2))

if __name__ == '__main__':
    if sys.argv[1]=='fit': fit(int(sys.argv[2]))
    else: dict(prepare=prepare, batch=batch, summarize=summarize)[sys.argv[1]]()
