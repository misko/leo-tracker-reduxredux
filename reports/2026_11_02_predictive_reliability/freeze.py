"""Freeze this bounded explanatory challenge panel before predictive fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OLD=REPO/'reports/2026_11_02_family_reliability'
CASES=['DS26-0070','DS26-0309','DS26-0040','DS26-0044','FRSH-0004']


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')


def roster():
    out=ROOT/'roster.json'
    if out.exists():raise FileExistsError(out)
    previous=read(OLD/'population/protocol.json');rows=[]
    for i,case in enumerate(CASES):
        old=next(r for r in previous['cases'] if r['case']==case)
        receipt=OLD/'population/cases'/case/'audited_result.json'
        decision=read(receipt)
        assert sha(Path(old['input_path']))==old['input_sha256']
        rows.append(dict(case=case,input_path=old['input_path'],input_sha256=old['input_sha256'],
            family=decision['selected_family'],seed=2026110208+i,
            previous_RF_receipt=str(receipt),previous_RF_receipt_sha256=sha(receipt)))
    write(out,dict(cases=rows,scope='Known helpful/harmful challenge panel; identities previously RF nominated; no new GPS-based family selection'))


def freeze():
    out=ROOT/'protocol.json'
    if out.exists():raise FileExistsError(out)
    plan=ROOT/'predictive/plan.json';assert plan.exists()
    local=[p for sub in ['predictive','preprocessing'] for p in (ROOT/sub).glob('*.py')]
    local += [ROOT/'decision.py',ROOT/'test_decision.py',Path(__file__)]
    dependencies=[OLD/'family/prototype.py',OLD/'predictive/bounded/bounded.py',
                  REPO/'tools/algo07_science/engine.py',REPO/'tools/dsx01_hierarchical_bound.py',
                  REPO/'tools/ds23_frequency_events.py']
    write(out,dict(created_utc_ns=time.time_ns(),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        cases=read(ROOT/'roster.json')['cases'],roster_sha256=sha(ROOT/'roster.json'),plan_sha256=sha(plan),
        predictive=dict(plan_sha256=sha(plan)),
        source_sha256={str(p):sha(p) for p in sorted(set(local+dependencies))},
        models=[1.,4.],arms=['c0','fitted_c'],phase_solver='half damping',
        starts=dict(position_km=[0.,0.],phase_reference='zeros; verified causal means remain in prior'),
        position_box_km=[-12.5,12.5],regional_center='existing operational center; unchanged from ALGO07',
        preprocessing=dict(base_noise_hz=150.,powers=1.,noise_precision='training-only Gamma(2,2) posterior',
            predictive_variance='150^2 E[1/tau], alpha=2+n_train/2; unseen group inverse moment2',
            ancillary_likelihoods='excluded from training/scoring',
            conditional_inputs=['fixed graph and GLRT discovery','original masks','integer aliases','satellite identities and RF target nomination','physical-mode support']),
        partitions=dict(time_folds=3,group_seconds=5.,held_group_fraction=.2,adjacent_guard_seconds=5.,
            minimum_target_train_points=5,minimum_target_held_points=2,minimum_training_points_per_receiver_band=5,
            receiver_transfers=2,target_points_each_receiver=20,target_time_overlap_seconds=10.,
            calibration='at least2 other families in each held-target band on heldRX, each>=10training points within held interval spanning>=10s'),
        solver_budget=dict(max_rounds=15,maxiter=25,maxfun=100),
        execution=dict(workers=4,BLAS_threads=1,preload_total_seconds=120,preload_case_seconds=60,
                       fitting_total_seconds=600,cell_seconds=120,retries=0),
        score='joint normalized localGaussian held density with shared nuisance/position covariance and exact bounded-box correction within that Gaussian; moment-matched Gamma noise, not exact mixture',
        qualification=['both SD models and both c arms optimizer success','raw phase gap<=0.01s',
            'inner VI log precision change<=1e-5','no regional boundary or position-curvature floor',
            'finite positive covariance and score','quadrature relativeerror<=1e-6',
            'identical frozen native partitions','training predictions above horizon',
            'four train-only covariance-axis1sigma probes in box with abs(delta(-2ELBO)-1)<=0.5'],
        decision='All5 supported/qualified partitions required. SD4 favored iff joint gains exceed max(1e-4,integration-error bound) in every partition/both arms and other-family timefold gains nonnegative within numerical tolerance. Reciprocal forSD1; otherwise inconclusive. No dropping failed or contradictory cells.',
        limitations=['Explanatory panel selected using known localization contrasts; not independent validation.',
            'Fixed nomination/masks/aliases remain conditional full-data inputs.',
            'Gamma tails and residual short-time correlation not integrated; local Gaussian validity only checked, not established.',
            'Overlapping randomized folds do not supply independent significance tests.'],
        geography='No evaluation location/error in fitting or decision. Root may compare sealed preferences to previously stored full-data endpoint errors afterward; this is a retrospective selector replay, not fresh pipeline inference.',
        publication='Research report and artifacts only; no deployment or production changes'))
    print('Frozen',sha(out))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--roster',action='store_true');args=p.parse_args()
    roster() if args.roster else freeze()
