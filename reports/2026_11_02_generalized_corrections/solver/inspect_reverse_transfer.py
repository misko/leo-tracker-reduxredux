"""No-fit replay of the saved reverse-transfer optimizer failure and gradient."""
import importlib.util
import json
from pathlib import Path
import signal
import time
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo07_science.validation import clean
from numerical import gradient_probe

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PREVIOUS = REPO/'reports/2026_11_02_predictive_reliability'


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('90s no-fit inspection cap')))
    signal.alarm(90)
    began = time.monotonic()
    spec = importlib.util.spec_from_file_location('saved_predictive', PREVIOUS/'predictive/engine.py')
    pred = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pred)
    plans = json.loads((PREVIOUS/'predictive/plan.json').read_text())
    record = next(r for r in plans['cases'] if r['case'] == 'DS26-0309')
    split = next(s for s in record['partitions'] if s['name'] == 'family_to_rx1')
    input_root = Path(record['input_path']).parent.parent
    e.configure(input_root, ROOT/'inspection_engine')
    e.ROOTS['DS26'] = input_root
    d, z, replay = e.load_case(record['case'])
    native = pred.native(d['problems']['fitted_c'][0])
    train = np.isin(native['ids'], split['train_ids'])
    dd = pred.family.candidate_context(d, z, 4., family=int(record['family']))
    dd, zz, receipt = pred.adapter.prepare_context(dd, z, train)
    rows = []
    for arm in ('c0', 'fitted_c'):
        path = PREVIOUS/'predictive/cells'/f'DS26-0309_family_to_rx1_{arm}_SD4.json'
        saved = json.loads(path.read_text())
        p, context = e.build(dd, zz, arm, np.asarray(saved['reference']))
        x = np.asarray(saved['x_km'])
        fun = lambda at: objective(p, context, at)
        f0 = fun(x)
        central = gradient_probe(fun, x)
        forward = [(fun(x + step) - f0)/.001 for step in np.eye(2)*.001]
        rows.append(dict(arm=arm, source_endpoint=str(path),
                         optimizer_message=saved['history'][-1]['optimizer_message'],
                         phase_change_s=saved['phase_change_s'], objective=f0,
                         replay_difference=f0-saved['history'][-1]['objective'],
                         exact_repeat_difference=fun(x)-f0,
                         central_gradient_probe=central, original_forward_gradient=forward))
    result = dict(no_fitting=True, no_truth=True, seconds=time.monotonic()-began,
                  preprocessing=receipt, rows=rows,
                  interpretation='ABNORMAL termination is not alone a stationarity certificate; gradient diagnostics precede the new solver protocol')
    path = ROOT/'reverse_transfer_gradient_inspection.json'
    path.write_text(json.dumps(clean(result), indent=2, allow_nan=False)+'\n')
    print(json.dumps(clean(result), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
