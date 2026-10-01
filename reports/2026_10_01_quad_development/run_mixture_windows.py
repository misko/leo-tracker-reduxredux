"""Six bounded window prerequisites and paired conditional warm fits."""
import fcntl
import os
from pathlib import Path
import sys
import time
import numpy as np
from run_window import prepare_window
from check_receiver_curvature import save
from mixture_localization import MixtureObjective
from mixture_optimizer import fit, audit
from mixture_window_groups import group_keys
from shared_scale_port import SharedScalePort
from fixed_association_port import FixedAssociationPort
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent
UNITS = tuple(f'{ds}-B01-{size}' for size in ('D1', 'Q') for ds in ('DS9', 'DS10', 'DS11'))


def worker(unit, directory):
    started = time.monotonic(); inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    single_gate = read(HERE/'mixture-localization-evaluation-v1.json'); assert single_gate['gate_passed']
    verify_sources(single_gate['sources']); verify_sources(single_gate['inputs'])
    parent_dir = HERE/'one-start-blas-window-cold-v1'/unit/'blas'
    parent = read(parent_dir/(unit+'.json')); frozen = read(parent_dir/'sources.json')
    parent_audit = read(parent_dir/'evaluation.json'); assert len(parent_audit['rows']) == 1 and parent_audit['rows'][0]['accepted']
    assert parent_audit['rows'][0]['receipt_sha256'] == digest(parent_dir/(unit+'.json'))
    assert process_ok(read(parent_dir/(unit+'.launch.json')))
    sources = dict(frozen['source_sha256']); inputs.update(frozen['inputs'])
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == parent['binding'] and parent['observations'] == [list(p.observation_ids) for p in ports]
    assert parent['columns'] == [c.tolist() for c in columns]
    np.testing.assert_array_equal(parent['precision'], precision)
    initial = np.asarray(parent['best']['mean']); labels = parent['best']['associations']
    keys = group_keys(binding['scans'], [s[0].bank.norad_ids for s in scans], [len(s[2]) for s in scans], labels)
    members = {}; backgrounds = []
    for p, i, key in zip(ports, labels, keys):
        if key is None: assert i == p.candidate_count; backgrounds.append(FixedAssociationPort(p, i))
        else: members.setdefault(key, []).append((p, i))
    models = {mode:MixtureObjective(ports, labels, keys, precision, initial, mode) for mode in ('independent', 'shared', 'mixture')}
    references = dict(independent=[FixedAssociationPort(p, i) for p,i in zip(ports, labels)],
                      shared=[SharedScalePort(m) for m in members.values()]+backgrounds)
    sources.update({str(Path(m.__file__).resolve()):digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('MIXTURE_WINDOW_PLAN.md', 'test_mixture_window_groups.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    checks = {}
    for mode, reference in references.items():
        model = models[mode]; F,g,H,_ = model.evaluate(initial); active = model.active
        f = float(.5*(precision*initial)@initial); gradient = (precision*initial)[active].copy(); metric = np.diag(precision[active])
        for p in reference:
            i = int(np.argmax(p.score_all(initial))); f -= p.score_selected(initial, i)
            if i == p.candidate_count: continue
            pred = p.predict_selected(initial, i); r = p.observation-pred.mean; v = np.linalg.solve(pred.covariance, r)
            w = (4+len(r))/(4+float(r@v)); J = pred.jacobian[:,active]
            gradient -= w*J.T@v; metric += w*J.T@np.linalg.solve(pred.covariance,J)
        check = dict(objective=abs(F-f), gradient=float(np.max(abs(g-gradient))), metric=float(np.max(abs(H-metric))))
        assert check['objective'] < 1e-8 and check['gradient'] < 1e-8 and check['metric'] < 1e-7
        checks[mode] = check
    model = models['mixture']; F,g,H,rho = model.evaluate(initial); np.linalg.cholesky(H)
    numeric_errors = {}
    for h in (.0005, .0001):
        numeric = []
        for j in model.active:
            step = np.zeros(len(initial)); step[j] = h
            numeric.append((model.evaluate(initial+step,False)[0]-model.evaluate(initial-step,False)[0])/(2*h))
        numeric_errors[str(h)] = float(np.max(abs(g-numeric))); assert numeric_errors[str(h)] < .005
    save(directory/'prerequisite.json', dict(unit=unit, endpoint_errors=checks, mixture_gradient_errors=numeric_errors,
        groups=[dict(scan=k[0],norad=k[1],tracks=len(v)) for k,v in members.items()], background_tracks=len(backgrounds)))
    for arm in ('independent','mixture'):
        model = models[arm]; t = time.monotonic(); result = fit(model, initial, t+60*binding['size']); seconds=time.monotonic()-t
        numeric_audit = audit(model,result); x=np.asarray(result['mean'])
        position_delta=float(np.linalg.norm(x[:2]-initial[:2])*1000)
        objective_delta=abs(model.evaluate(x,False)[0]-parent['best']['objectives'][-1]) if arm=='independent' else None
        control=bool(position_delta<=1 and objective_delta<=1e-5) if arm=='independent' else None
        save(directory/(arm+'.json'),dict(unit=unit,arm=arm,binding=binding,fit=result,audit=numeric_audit,
            fit_seconds=seconds,baseline_position_delta_m=position_delta,control_objective_difference=objective_delta,
            control_equivalent=control,final_responsibilities=model.evaluate(x,False)[3] if numeric_audit['accepted'] else None))
        print(unit,arm,numeric_audit,control,flush=True)
    verify_sources(sources);verify_sources(inputs)
    save(directory/'completion.json',dict(unit=unit,elapsed_seconds=time.monotonic()-started,verified=True))


def main():
    if len(sys.argv)==3:worker(sys.argv[1],Path(sys.argv[2]));return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=HERE/'mixture-window-pilot-v1';root.mkdir(exist_ok=False)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory=root/unit;directory.mkdir();size=4 if unit.endswith('-Q') else 2
            launch=execute([sys.executable,str(Path(__file__).resolve()),unit,str(directory)],directory,unit,timeout_s=90*size,env=env)
            save(directory/'launch.json',launch);print(unit,launch['returncode'],launch['elapsed_seconds'],flush=True)


if __name__=='__main__':main()
