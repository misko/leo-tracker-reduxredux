"""Independent frozen nomination source/algebra review; no propagation."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
import unittest

import numpy as np
from scipy.special import logsumexp

ROOT=Path(__file__).resolve().parents[1]
NOM=ROOT/'nomination'
sys.path.insert(0,str(NOM))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('nomination preflight60s cap')))
    signal.setitimer(signal.ITIMER_REAL,60.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=json.loads((NOM/'protocol.json').read_text())
    check('exact frozen protocol',sha(NOM/'protocol.json')=='e9720f6efc12078c30e2c09edcb1606faa0b7ea575493cfb75f2b0c665fbf5e5')
    for path,digest in protocol['source_input_hashes'].items():check('binding '+path,sha(path)==digest)
    check('metadata binding',sha(NOM/'metadata.json')==protocol['metadata_sha256'])
    check('no science started before preflight',not (NOM/'scientific_start.json').exists())
    check('12 draw/24arm/192candidate caps',protocol['maximum_trials']==12 and protocol['maximum_arm_jobs']==24 and protocol['maximum_candidate_contexts']==192)
    check('same finite aliases',protocol['alias_support']==list(range(-4,5)))
    import experiment as e
    import test_experiment
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_experiment)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    check('eight owned controls',result.wasSuccessful() and result.testsRun==8)
    rng=np.random.default_rng(202610251945)
    n=7;root=rng.normal(size=(n,n));cov=root@root.T+np.eye(n)*5
    residual=rng.normal(size=(3,n));shape=rng.normal(size=(3,n,3));shifts=rng.normal(size=(9,n))
    actual=e.k.conditional_costs(residual,cov,shape,shifts)
    expected=np.empty_like(actual)
    for phase in range(3):
        full=cov+shape[phase]@shape[phase].T
        for alias in range(9):
            y=residual[phase]+shifts[alias]
            expected[phase,alias]=y@np.linalg.solve(full,y)+np.linalg.slogdet(full)[1]+n*np.log(2*np.pi)
    error=float(np.max(abs(expected-actual)))
    check('independent dense physical-node covariance oracle',error<1e-10)
    times=np.linspace(0,100,n);raw=rng.normal(size=n)*200
    base=cov*1000
    comp=dict(raw=raw,covariance=base,groups=np.zeros(n,dtype=int),d=dict(target_track=dict(times=times)))
    score=e.k.null_score(comp,np.arange(n))
    z=2*(times-times.min())/np.ptp(times)-1
    b=np.polynomial.legendre.legvander(z,4)*e.k.PERIOD/np.sqrt(6)
    full=base+b@b.T
    density=[]
    for alias in range(-4,5):
        y=raw+alias*e.k.PERIOD
        density.append(-.5*(y@np.linalg.solve(full,y)+np.linalg.slogdet(full)[1]+n*np.log(2*np.pi)))
    expectednull=float(-2*(logsumexp(density)-np.log(9)))
    nullerror=abs(expectednull-score['objective'])
    check('independent normalized shared-base polynomial-null oracle',nullerror<1e-5)
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,protocol_sha256=sha(NOM/'protocol.json'),checks=checks,tests_passed=8,
                independent_physical_node_error=error,independent_null_density_error=nullerror,
                seconds=time.monotonic()-began,source_sha256=sha(__file__),propagation_calls=0,fits=0,
                source_review=['injected whole-source CFO reaches original coarse_phase_scores through narrow truth-free port',
                  'ordinary top8 has no true-label backfill, nominee retention or reserved competitor',
                  'eligible generators exclude every original protected/curved/predictive family before response draw',
                  'same c0 generating observations and position in both arms; candidate-specific causal phase and full physical modes',
                  'uniform finite alias prior and normalized shared-base covariance agree for physical/null generation and scores',
                  'one symmetric union cavity; all original/final conditional vectors/covariances and removed IDs exported',
                  'expired global deadline hardblocks next scientific stage; failures/checkpoints retained',
                  'alias range sensitivity separate from quadrature qualification; all relevant competitors must qualify'],
                scope_limits=['historically response-selected native layouts',
                  'generating full-parent and exact union-cavity conditioning differ',
                  'conditional nomination/ranking falsification only; no parent/GLRT closure, SBC, identity probabilities or acceptance rule'])
    (ROOT/'audit/nomination_preflight.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(all_passed=True,checks=len(checks),seconds=output['seconds'],physical_error=error,null_error=nullerror)))


if __name__=='__main__':main()
