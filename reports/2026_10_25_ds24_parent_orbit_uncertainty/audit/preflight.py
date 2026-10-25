"""Independent source and Gaussian-kernel preflight. No scan propagation."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'scientific'
sys.path.insert(0,str(SCI))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gaussian(y,cov):
    return float(y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi))


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('60s independent preflight cap')))
    signal.setitimer(signal.ITIMER_REAL,60.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=json.loads((SCI/'protocol.json').read_text())
    check('exact frozen protocol',sha(SCI/'protocol.json')=='f9e4231d4552e1f19b0db627735424f7b7a1da2ed0dc6a69f1968ae6e7b6f3c6')
    for path,digest in protocol['source_input_hashes'].items():check('binding '+path,sha(path)==digest)
    for path,digest in protocol['test_receipts'].items():check('producer test receipt '+path,sha(path)==digest)
    check('four unchanged chronological cases',protocol['ordered_cases']==['DS24-0010','DS24-0011','DS24-0012','DS24-0013'])
    check('paired same-budget fits',protocol['arms']==['c0','fitted_c'] and protocol['maximum_position_fits']==16 and protocol['phase_rounds']==5 and protocol['iterations_per_round']==48)
    check('operational output is reference',protocol['operational_policy_source']=='original_reference')
    check('no real fixed stage yet',not (SCI/'fixed_summary.json').exists())
    import test_scientific
    import adapter as a
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_scientific)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    check('nine owned algebra/layout/gate controls',result.wasSuccessful() and result.testsRun==9)
    # Independent dense joint -> conditional Gaussian reference. One B block is
    # shared by curved and predictive data; predictive constants remain local.
    rng=np.random.default_rng(2026102529)
    uc,ue=rng.normal(size=(11,5))*20,rng.normal(size=(7,5))*20
    bc,be=rng.normal(size=(11,3))*30,rng.normal(size=(7,3))*30
    pc=np.r_[np.linspace(.5,2.,5),np.ones(3)]
    hc=np.column_stack((uc,bc));he=np.column_stack((ue,be))
    sc=np.linspace(15.,25.,11);se=np.linspace(30.,40.,7)
    yc,ye=rng.normal(size=11)*60,rng.normal(size=7)*60
    gram=np.diag(pc)+hc.T@((1/sc**2)[:,None]*hc)
    mean=np.linalg.solve(gram,hc.T@(yc/sc**2))
    actual=a.predictive_residual(ye-he@mean,he,gram,se,np.zeros(7,dtype=int))['objective']
    design=np.vstack((np.column_stack((hc,np.zeros(11))),np.column_stack((he,np.ones(7)*300))))
    prior=np.r_[pc,1.]
    covariance=np.diag(np.r_[sc**2,se**2])+(design/prior)@design.T
    expected=gaussian(np.r_[yc,ye],covariance)-gaussian(yc,covariance[:11,:11])
    error=abs(actual-expected)
    check('independent dense shared curved/predictive conditional density',error<1e-9)
    old=np.vstack((np.column_stack((uc,np.zeros((11,1)))),np.column_stack((ue,np.ones((7,1))*300))))
    oldcov=np.diag(np.r_[sc**2,se**2])+(old/np.r_[pc[:5],1.])@old.T
    added=np.vstack((bc,be))
    kernelerror=float(np.max(abs(covariance-oldcov-added@added.T)))
    check('one shared added prior covariance kernel',kernelerror<1e-9)
    info=np.array([[4.,.7],[.7,1.5]]);change=np.array([.6,-.8])
    movement=-.5*np.linalg.solve(info,change)
    check('negative-twice-objective movement factor',np.linalg.norm(2*info@movement+change)<1e-14)
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,protocol_sha256=sha(SCI/'protocol.json'),approved_stage='fixed_only',
        checks=checks,tests_passed=9,independent_conditional_density_error=error,kernel_identity_error=kernelerror,
        seconds=time.monotonic()-began,source_sha256=sha(__file__),propagation_calls=0,fits=0,GPS_or_position_errors_read=False,
        source_review=['old support/bank/columns/constants and priors preserved; extra Gaussian features appended only for active missing-mode families',
          'shared extra physical columns included jointly in curved and predictive covariance; predictive data do not calibrate coefficients or Gamma',
          'conservative gate view omits new physical means in curved/profile/predictive/extension predictions without mutating full results',
          'literal expanded/fullmean retained gates separately saved; unsafe literal expanded extension explicitly unavailable',
          'original noise/Student/Gaussian normalization and zero-feature predictive covariance retained',
          'fixed-state controls hardblock failed zero replay, column equality, original-ID ledger, derivative, PSD and density checks',
          'triage uses fixed old information and delta objective gradient with Hessian proxy2I; same criterion required in both arms',
          'matched cold16-fit design separately coordinator-gated after fixed seal; reference remains operational for all outcomes'],
        pending_before_fits='Actual-context zero-equivalence, no-feedback, cache/gate/extension invariance and fixed-state numerical results must pass; separate coordinator go remains required.')
    (ROOT/'audit/preflight.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(all_passed=True,checks=len(checks),seconds=output['seconds'],conditional_error=error,kernel_error=kernelerror)))


if __name__=='__main__':main()
