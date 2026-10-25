"""Source/input freeze only; no old-case numerical evaluation."""
from pathlib import Path
import sys
import support_replay as s


def freeze():
    r=s.r;old=r.read(s.OLD/'protocol.json');bindings=dict(old['source_input_hashes'])
    old_seal=r.read(s.OLD/'RF_seal.json')
    for path,h in old_seal['files'].items():
        if r.sha(path)!=h:raise ValueError('original sealed regression fixture changed: '+path)
    for p in sorted(s.OLD.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:bindings[str(p)]=r.sha(p)
    names=('support_geometry.py','support_math.py','support_bounds.py','support_replay.py','freeze_support.py','test_support.py','PROTOCOL.md')
    for name in names:
        p=s.HERE/name;bindings[str(p)]=r.sha(p)
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and str(path).endswith('.py') and (str(path).startswith(str(r.REPO/'src')) or str(path).startswith(str(r.REPO/'tools'))):
            bindings[str(Path(path).resolve())]=r.sha(path)
    receipts=sorted(s.HERE.glob('test_receipt*.json'));tests=r.read(receipts[-1])
    if tests['passed'] is not True:raise ValueError('owned tests must pass')
    protocol=dict(cases=s.CASES,arms=s.ARMS,layouts={row['case']:row for row in old['layouts']},
        source_input_hashes=bindings,old_protocol_sha256=r.sha(s.OLD/'protocol.json'),
        old_RF_seal_sha256=r.sha(s.OLD/'RF_seal.json'),original_RF_seal_bindings_verified=True,
        preparation_scientific_seconds=sum(r.read(p)['seconds']+r.read(p).get('earlier_test_seconds',0.) for p in receipts),
        test_receipts={str(p):r.sha(p) for p in receipts},
        maximum_trials=12,maximum_arm_rows=24,maximum_candidate_contexts=192,
        support='original truncated Student prior times whole-source LOS indicator; no visible-mass renormalization',
        root_xtol_s=1e-11,maximum_support_depth=22,maximum_envelope_panels=8192,envelope_refinement_batch=512,
        quadrature='log-tanh-sinh levels0..6 rtol1e-9,absolute0; independentGL32/64; all interpolation pieces',
        original_absolute_objective_tolerance=1e-3,score_precision_and_certified_order_reported_separately=True,
        order_rule='winning lower log evidence strictly exceeds every other upper including null; unknown bounds block',
        null_eigensolve_tolerance=1e-7,null_objective_floating_allowance=1e-6,
        reference_rule='old dense top2 plus new raw top2 plus evidence-interval overlaps with best physical/null; no backfill',
        positive_Woodbury_quadratic=True,mean_covariance_prior_derivative_enclosure=True,
        original_alias_support=list(range(-4,5)),original_uniform_alias_prior=True,
        workers=2,BLAS_threads=1,maximum_scientific_worker_seconds=600,
        cap_accounting='producer tests+sum scientific workerseconds; common wall deadline remaining/2',
        no_new_draws_parent_refits_positionfits_RF_GPS_or_operational_assignments=True,
        no_retries_rerolls_rescues_backfill=True)
    r.write_new(s.PROTOCOL,protocol);r.write_new(s.HERE/'protocol_seal.json',dict(protocol_sha256=r.sha(s.PROTOCOL)))
    print(r.sha(s.PROTOCOL),flush=True)


if __name__=='__main__':freeze()
