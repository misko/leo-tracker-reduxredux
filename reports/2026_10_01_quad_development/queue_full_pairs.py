"""Run at most four frozen full-panel pair experiments, preserving failed runs."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from run_constituent_pair import save, digest, verify_sources

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    directory = HERE/'full-pair-queue-v1'
    plan_path = directory/'plan.json'
    selection_path = HERE/'selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    units = [u['unit_id'] for u in json.loads(selection_path.read_text())['evaluation_units'] if u['size'] == 2]
    assert len(units) == 32 and len(set(units)) == 32
    if not plan_path.exists():
        directory.mkdir(exist_ok=False)
        paths = [selection_path,HERE/'FULL_PAIR_PLAN.md',HERE/'CONSTITUENT_START_PLAN.md',
                 HERE/'run_constituent_pair_v3.py',HERE/'run_constituent_pair.py',Path(__file__)]
        save(plan_path,dict(units=units,source_sha256={str(p.resolve()):digest(p) for p in paths}))
    assert digest(plan_path) == plan_path.with_suffix('.sha256').read_text().strip()
    plan = json.loads(plan_path.read_text()); assert plan['units'] == units
    verify_sources(plan['source_sha256'])
    pending = []
    for unit in units:
        target = HERE/'constituent-pair-v3'/unit
        if not target.exists():
            pending.append(unit); continue
        audit = target/'evaluation.json'
        assert audit.exists(), f'Incomplete run requires inspection: {target}'
        assert digest(audit) == audit.with_suffix('.sha256').read_text().strip()
        rows = json.loads(audit.read_text())['rows']
        assert len(rows) == 1 and rows[0]['unit'] == unit
    env = dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(ROOT/'src'))
    for unit in pending[:4]:
        verify_sources(plan['source_sha256'])
        print(json.dumps(dict(stage='start',unit=unit)),flush=True)
        with (directory/(unit+'.log')).open('x') as stream:
            process = subprocess.Popen([sys.executable,str(HERE/'run_constituent_pair_v3.py'),unit],
                cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise RuntimeError(f'Outer timeout; inspect {unit} before continuing')
        assert code == 0, f'{unit} exited {code}; inspect its log'
        audit = HERE/'constituent-pair-v3'/unit/'evaluation.json'
        assert digest(audit) == audit.with_suffix('.sha256').read_text().strip()
        data = json.loads(audit.read_text()); assert len(data['rows']) == 1 and data['rows'][0]['unit'] == unit
        print(json.dumps(dict(stage='audited',rows=data['rows'])),flush=True)
    print(json.dumps(dict(stage='batch_complete',ran=min(4,len(pending)),remaining=max(0,len(pending)-4))),flush=True)


if __name__ == '__main__': main()
