"""Seal sources and archived inputs without propagation or objective calls."""
import time
from pathlib import Path
import runner as k


def freeze():
    r=k.r;began=time.monotonic();bindings={};cases={}
    ledger=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/cohort_ledger.json')
    for row in r.read(ledger)['rows']:
        case=row['case']
        if case not in k.CASES:continue
        for item in row['frozen_scan_files']+[row['baseline']]:
            if r.sha(item['path'])!=item['sha256']:raise ValueError('frozen DS24 corpus changed')
            bindings[item['path']]=item['sha256']
        for suffix in ('.json','_forecast.json'):
            path=r.SOURCE/'causal_phase_history'/(case+suffix);bindings[str(path)]=r.sha(path)
        path=k.OWNERSHIP/case/'parent.json';bindings[str(path)]=r.sha(path)
        cases[case]=dict(original_ownership_path=str(path),original_ownership_sha256=r.sha(path),
            baseline_path=str(r.SOURCE/'family_cavity/position'/(case+'.json')))
    if set(cases)!=set(k.CASES):raise ValueError('four frozen cases required')
    # Bind imported local numerical code, including transitive research/geometry
    # modules. No original file is copied, patched or treated as production.
    import sys
    paths={Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m,'__file__',None) and str(m.__file__).endswith('.py')
        and (str(Path(m.__file__).resolve()).startswith(str(r.REPO/'tools'))
             or str(Path(m.__file__).resolve()).startswith(str(r.REPO/'src')))}
    paths|={k.HERE/name for name in ('adapter.py','parent_diagnostics.py','runner.py','freeze.py','test_scientific.py','PROTOCOL.md')}
    paths|={ledger,k.ROOT/'COORDINATOR_PLAN.md',Path(r.__file__),
        Path('/srv/bulk/leo/research/ds24-nomination-information-r01/information/ranking.py')}
    for path in sorted(paths):bindings[str(path)]=r.sha(path)
    receipts=sorted(k.HERE.glob('test_receipt*.json'))
    tests=r.read(receipts[-1])
    protocol=dict(cases=cases,ordered_cases=k.CASES,arms=r.ARMS,methods=k.METHODS,
        source_input_hashes=bindings,preparation_numerical_seconds=sum(r.read(p)['seconds'] for p in receipts),
        tests_passed=tests['passed'],test_receipts={str(p):r.sha(p) for p in receipts},
        added_covariance='original unit-Gaussian three physical modes per active family missing original modes; one shared block across curved and predictive rows; append after unchanged old columns',
        inference_unchanged=['original candidates/aliases/points/masks/powers/native noise','original causal phase means/SD/nu','curved-only VI/Gamma calibration; predictive inverse-moment factor2 and300Hz constants','original radio/height priors and regional bounds'],
        conservative_gates='original calibration support and thresholds; omit new physical posterior means from profile, conditional residual, predictive raw residual and extensions; never mutate full likelihood cache',
        literal_gates='expanded support/full-mean retained and predictive gates only; expanded legacy postfit extension unavailable because its contiguous indexing does not match appended layout',
        fixed_steps_km=[.01,.02],objective_gradient_tolerance='norm(g.01-g.02)<=max(.001,.001*norm(g.01))',
        mean_design_relative_tolerance=1e-5,
        primary_information='OLD J/Gamma/weights/phase prior precisions/mean coefficients frozen; append Bnew with unit prior and mean0; retain joint old predictive covariance/constants',
        movement_proxy='-.5*solve(I_baseline,g_candidate-g_baseline); I is local mean-design information; Hessian proxy2I',
        triage='any case: BOTH arms proxy norm>=.05km OR BOTH arms original-weak variance fractional increase>=.05; no crossing criteria between arms',
        hypothetical_adoption='conservative paired RF gates AND unclipped absolute phase<=15.000001 AND final phase change<=.01 AND Gamma<=1e-5 AND complete original accepted IDs preserved both arms including postfit; original likelihood IDs/aliases/labels exact',
        operational_policy_source='original_reference',workers=2,BLAS_threads=1,scientific_cap_seconds=600,
        budget_semantics='cumulative summed scientific worker seconds plus producer numerical test seconds; global wall deadline remaining/2, per-case120s total across stages',
        case_cap_seconds=120,maximum_position_fits=16,phase_rounds=5,iterations_per_round=48,
        start_km=[0,0],regional_box_km=25,regional_center=[37.906,-122.545],
        no_retries_rescues_backfill_or_new_nominations=True,GPS_or_position_errors_used=False,
        fixed_stage_requires='audit/preflight.json bound to this protocol',
        fit_stage_requires='matching preflight plus coordinator_go.json bound to protocol and fixed_seal.json; no launch solely from materiality result',
        zero_equivalence_objective_tolerance=1e-6,zero_equivalence_coefficient_tolerance=1e-7,
        dense_oracle_tolerance=1e-6,freeze_non_numerical_seconds=time.monotonic()-began)
    r.write_new(k.PROTOCOL,protocol)
    r.write_new(k.HERE/'protocol_seal.json',dict(protocol_sha256=r.sha(k.PROTOCOL)))
    print(r.sha(k.PROTOCOL),flush=True)


if __name__=='__main__':freeze()
