"""Bounded real physical endpoint and mixture-gradient checks."""
import fcntl
import os
from pathlib import Path
import sys
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from shared_scale_port import SharedScalePort
from fixed_association_port import FixedAssociationPort
from mixture_localization import MixtureObjective
from screen_seed_prefix import sealed, digest
from regression_batch import execute, verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def worker(unit, directory):
    inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    parent_dir = HERE/'one-start-blas-cold-v1'/unit/'blas'
    parent = read(parent_dir/(unit+'.json')); frozen = read(parent_dir/'sources.json')
    audit = read(parent_dir/'evaluation.json'); assert audit['rows'][0]['accepted']
    assert audit['rows'][0]['receipt_sha256'] == digest(parent_dir/(unit+'.json'))
    assert process_ok(read(parent_dir/(unit+'.launch.json')))
    sources = dict(frozen['source_sha256']); inputs.update(frozen['inputs'])
    verify_sources(sources); verify_sources(inputs)
    binding, scans, columns, precision, ports = prepare_window(unit)
    assert binding == parent['binding'] and parent['observations'] == [list(p.observation_ids) for p in ports]
    np.testing.assert_array_equal(parent['precision'], precision)
    x = np.asarray(parent['best']['mean']); labels = parent['best']['associations']
    members = {}; backgrounds = []
    for p, i in zip(ports, labels):
        if i == p.candidate_count: backgrounds.append(FixedAssociationPort(p, i))
        else: members.setdefault(i, []).append((p, i))
    references = dict(independent=[FixedAssociationPort(p, i) for p,i in zip(ports, labels)],
        shared=[SharedScalePort(m) for m in members.values()]+backgrounds)
    checks = {}
    for mode, reference in references.items():
        model = MixtureObjective(ports, labels, labels, precision, x, mode)
        F, g, H, _ = model.evaluate(x); active = model.active
        f = float(.5*(precision*x)@x); gradient = (precision*x)[active].copy(); metric = np.diag(precision[active])
        for p in reference:
            i = int(np.argmax(p.score_all(x))); f -= p.score_selected(x, i)
            if i == p.candidate_count: continue
            pred = p.predict_selected(x, i); r = p.observation-pred.mean; v = np.linalg.solve(pred.covariance, r)
            w = (4+len(r))/(4+float(r@v)); J = pred.jacobian[:, active]
            gradient -= w*J.T@v; metric += w*J.T@np.linalg.solve(pred.covariance, J)
        differences = dict(objective=abs(F-f), gradient=float(np.max(abs(g-gradient))), metric=float(np.max(abs(H-metric))))
        assert differences['objective'] < 1e-8 and differences['gradient'] < 1e-8 and differences['metric'] < 1e-7
        checks[mode] = differences
    model = MixtureObjective(ports, labels, labels, precision, x)
    F, gradient, H, responsibility = model.evaluate(x); np.linalg.cholesky(H)
    sources.update({str(Path(m.__file__).resolve()): digest(m.__file__) for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).suffix == '.py' and Path(m.__file__).resolve().is_relative_to(HERE.parents[1])})
    for name in ('MIXTURE_LOCALIZATION_PLAN.md', 'test_mixture_localization.py'): sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources); verify_sources(inputs); save(directory/'sources.json', dict(source_sha256=sources, inputs=inputs))
    errors = {}
    for h in (.0005, .0001):
        numeric = []
        for j in model.active:
            step = np.zeros(len(x)); step[j] = h
            numeric.append((model.evaluate(x+step, False)[0]-model.evaluate(x-step, False)[0])/(2*h))
        errors[str(h)] = float(np.max(abs(gradient-numeric))); assert errors[str(h)] < .005
    verify_sources(sources); verify_sources(inputs)
    result = dict(unit=unit, endpoint_errors=checks, mixture_gradient_errors=errors, mixture_objective=F,
        full_group_shared_responsibilities={str(scans[0][0].bank.norad_ids[int(k)]):v for k,v in responsibility.items()},
        group_sizes={str(scans[0][0].bank.norad_ids[k]):len(v) for k,v in members.items()},
        observation_ids_preserved=len({v for p in ports for v in p.observation_ids}),
        qualification='Physical endpoint and fixed-state derivative prerequisite; no fits or geographic scoring.')
    save(directory/'result.json', result); print(result, flush=True)


def main():
    if len(sys.argv) == 3: worker(sys.argv[1], Path(sys.argv[2])); return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = HERE/'mixture-localization-check-v1'; root.mkdir(exist_ok=False)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(HERE.parents[1]/'src'))
        for unit in UNITS:
            directory = root/unit; directory.mkdir()
            launch = execute([sys.executable, str(Path(__file__).resolve()), unit, str(directory)], directory, unit, timeout_s=90, env=env)
            save(directory/'launch.json', launch); print(unit, launch['returncode'], flush=True); assert process_ok(launch)


if __name__ == '__main__': main()
