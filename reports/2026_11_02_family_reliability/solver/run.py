"""Freeze bounded protocol before scoring, execute one case/arm per process."""
import argparse, hashlib, importlib.util, json, os, signal, subprocess, time
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from algo06_science.common import read,write
from solver import fit

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
INPUT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
PRIOR=REPO/'reports/2026_11_02_algo07_top10_outliers/diagnostics'
CASES=('DS26-0070','DS26-0309')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze():
    path=ROOT/'protocol.json'
    if path.exists():raise RuntimeError('protocol already frozen')
    sources=[ROOT/'solver.py',ROOT/'run.py',ROOT/'test_solver.py',*sorted((REPO/'tools/algo07_science').glob('*.py')),
        *[REPO/'tools'/s for s in ('dsx01_joint_marginal.py','probe_ds23_history_calibrated_phase.py','phase_reference_checks.py','ds23_frequency_events.py')]]
    sources += [INPUT/'inputs'/f'{c}.json' for c in CASES]
    sources += [PRIOR/c/'matched-start-plan.json' for c in CASES]
    write(path,dict(frozen_before_new_scores=True,created_utc_ns=time.time_ns(),
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        cases=CASES,arms=['c0','fitted_c'],variants=['legacy','damped_half','damped_quarter'],
        optional_variant_rule='run damped_quarter on BOTH c arms of a case only if any damped_half arm is not phase closed',
        new_solver_variants=2,damping=[.5,.25],phase_tolerance_s=.01,reference_limit_s=30,
        max_rounds=15,maxiter=35,maxfun=140,maxls=15,ftol=1e-10,gtol=1e-4,eps=.001,
        starts='shared published fitted-c endpoint and phase reference, both c arms',
        selection='all fixed endpoints reported; no truth-based selection',
        objective='unchanged existing ELBO + family score + elevation penalty at each fixed reference',
        objective_invariance='false for nonlinear geometry; refresh changes the approximation, damping targets same fixed-point equations',
        phase_parameterization='absolute phase / prior sigma; unchanged mean/sigma and latent prior; no delta-phase prior shift',
        bounds_km=[[-12.5,12.5],[-12.5,12.5]],
        input_root=str(INPUT),sources={str(p):sha(p) for p in sources},
        environmental_threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS')},
        max_worker_seconds=840,workers=4,
        controls='published baseline + archived matched 15-round legacy refit; legacy rerun only if missing',
        assessment='phase, optimizer, base/exact/mixture gates and unchanged owner/native IDs; truth read after RF fits'))

def diagnostic_module():
    spec=importlib.util.spec_from_file_location('outlier_diagnostic',PRIOR/'diagnose.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(case,arm):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('840 second worker budget')))
    signal.alarm(840)
    protocol=read(ROOT/'protocol.json')
    for p,h in protocol['sources'].items():
        if sha(p)!=h:raise RuntimeError(f'frozen source changed: {p}')
    out=ROOT/case/arm;out.mkdir(parents=True,exist_ok=True)
    e.configure(INPUT,ROOT);e.ROOTS['DS26']=INPUT
    d,z,replay=e.load_case(case);diag=diagnostic_module()
    start=read(PRIOR/case/'matched-start-plan.json')
    # The archived controls use these exact common starts and declared budgets.
    control=read(PRIOR/case/f'matched_continue-{arm}.json')
    published_p,published_x=d['problems'][arm]
    published=dict(x=published_x,reference=published_p.reference,
        objective=diag.objective(published_p,d,published_x),
        phase_change_s=float(max(abs(published_p.state(published_x)['phases'][published_p.labels]-published_p.reference))),
        optimizer_success=None,optimizer_reason='published metadata inspected separately',
        status='published baseline',source=str(PRIOR/case/'audit.json'))
    write(out/'replay.json',replay)
    row=fit(d,z,arm,start=np.asarray(start['position_start']),reference=np.asarray(start['phase_reference_start']))
    p,dd=e.build(d,z,arm,np.asarray(row['reference']))
    row.update(diag.gates(p,dd,np.asarray(row['x']),z,arm))
    row['qualified']=bool(row['phase_closed'] and row['optimizer_success'] and row['all_gates_pass'] and not row['lost_ids'] and not row['reassigned_ids'])
    row['qualification_scope']='conditional RF/phase/optimizer/gates/ownership only; independent identity evidence unavailable here'
    # Seal fit before evaluation-only truth function is invoked.
    write(out/'fit_without_truth.json',row)
    for label,item in [('published',published),('legacy',control),('damped_half',row)]:
        item['error_m']=diag.error(np.asarray(item['x']))
        item['source_kind']='archived control' if label=='legacy' else 'new experiment' if label=='damped_half' else 'published replay'
        write(out/(label+'.json'),item)
    c=p.calculate(np.asarray(row['x']))
    np.savez_compressed(out/'native_fit.npz',times=p.flat_times,values=p.values,keep=p.keep,residual=c['conditional_residual_hz'],orbit=p.q*c['frequency'],radio_adjusted=p.values-c['conditional_residual_hz'])
    native_ids=sorted(o for tr in row['proposed_owners'] for o in [tr])
    write(out/'evidence_manifest.json',dict(protocol_sha256=sha(ROOT/'protocol.json'),input_sha256=sha(INPUT/'inputs'/f'{case}.json'),
        native_export_sha256=sha(Path(z['native_path'])/'observations.json'),
        owner_sha256=hashlib.sha256(json.dumps(row['proposed_owners'],sort_keys=True).encode()).hexdigest(),
        original_owners_sha256=hashlib.sha256(json.dumps(z['baseline_owners'][arm],sort_keys=True).encode()).hexdigest(),
        unchanged_owner_mapping=row['proposed_owners']==z['baseline_owners'][arm],
        observation_mask_sha256=hashlib.sha256(np.asarray(d['keep']).tobytes()).hexdigest(),
        prior_means=np.asarray(d['means']),prior_sigma=p.phase_sigma,phase_model=d['model'],powers=d['powers']))
    print(case,arm,'damped',row['error_m'],'closed',row['phase_closed'],'gap',row['phase_change_s'],'gates',row['all_gates_pass'],'seconds',row['seconds'],flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--case',choices=CASES);ap.add_argument('--arm',choices=['c0','fitted_c']);a=ap.parse_args()
    freeze() if a.freeze else run(a.case,a.arm)
