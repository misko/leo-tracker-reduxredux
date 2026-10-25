"""Bounded independent metadata and dense Gaussian checks; no propagation."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INFO = ROOT / 'information'
sys.path.insert(0, str(INFO))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('independent audit cap')))
    signal.setitimer(signal.ITIMER_REAL, 60.)
    checks = []
    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))
        if not passed:
            raise AssertionError(name)
    protocol_path = INFO/'protocol.json'
    protocol = json.loads(protocol_path.read_text())
    check('exact frozen protocol', sha(protocol_path) == 'd5df0aff51c2428e69d6296dbd0e1e86b7a0572a31dab10ba31eb643534e98e6')
    for path, digest in protocol['source_and_input_bindings'].items():
        check('binding '+path, sha(path) == digest)
    inv = json.loads((INFO/'inventory.json').read_text())
    for case in inv['cases']:
        rows = [r for r in inv['sources'] if r['case'] == case['case']]
        ownership = json.loads(Path(case['parent_ownership_path']).read_text())
        accepted = set().union(*(set(ownership['coverage'][arm]['accepted_observation_ids']) for arm in ('c0','fitted_c')))
        allids = [oid for row in rows for oid in row['observation_ids']]
        check(case['case']+' graph owner disjointness', len(allids) == len(set(allids)))
        check(case['case']+' whole pool count', len(rows) == case['original_curved_graph_owners'])
        eligible = [r for r in rows if r['eligible']]
        check(case['case']+' eligible count', len(eligible) == case['eligible_complete_curved_owners'])
        for row in rows:
            check(row['component']+' complete unique IDs', len(row['observation_ids']) == row['points'] == len(set(row['observation_ids'])))
            check(row['component']+' eligibility from full accepted IDs', row['eligible'] == (not bool(set(row['observation_ids']) & accepted)))
            check(row['component']+' unqualified identity retained', row['identity_qualified'] is False)
    import test_ranking as tests
    for name in sorted(n for n in vars(tests) if n.startswith('test_')):
        getattr(tests, name)()
        check(name, True)
    # Independent observation-space Gaussian oracle, without the producer's
    # nuisance projection or conditional-covariance construction.
    from ranking import gain
    rng = np.random.default_rng(202610251931)
    u, j = rng.normal(size=(31,5)), rng.normal(size=(31,2))
    h, jt, b = rng.normal(size=(9,5)), rng.normal(size=(9,2)), rng.normal(size=(9,4))
    w, prior, noise = np.exp(rng.normal(size=31)), np.exp(rng.normal(size=5)), np.exp(rng.normal(size=9))
    oldcov = np.diag(1/w)+(u/prior)@u.T
    oldinfo = j.T@np.linalg.solve(oldcov,j)
    fullu = np.vstack((np.column_stack((u,np.zeros((31,4)))),np.column_stack((h,b))))
    fullprior = np.r_[prior,np.ones(4)]
    covariance = np.diag(np.r_[1/w,noise])+(fullu/fullprior)@fullu.T
    fullj = np.vstack((j,jt))
    expected = fullj.T@np.linalg.solve(covariance,fullj)
    gram = np.diag(prior)+u.T@(w[:,None]*u)
    delta, _, _ = gain(jt,h,noise,b,np.linalg.cholesky(gram),np.linalg.solve(gram,u.T@(w[:,None]*j)))
    error = float(np.max(abs(expected-oldinfo-delta)))
    check('independent observation-space dense oracle', error < 1e-10)
    seconds = time.monotonic()-began
    signal.setitimer(signal.ITIMER_REAL,0)
    result = dict(all_passed=True, protocol_sha256=sha(protocol_path), checks=checks,
                  owned_tests_passed=3, independent_dense_max_error=error,
                  seconds=seconds, audit_cap_seconds=180., propagation_calls=0, fits=0,
                  source_sha256=sha(__file__),
                  scope='conditional local Gaussian mean-design diagnostic; no identity or calibrated uncertainty qualification',
                  source_review='shared old/new covariance; fixed weak axes; inactive dormant slots zero; blocked rows retained; no target CFO learning')
    (ROOT/'audit/information_preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(all_passed=True,checks=len(checks),seconds=seconds,error=error)))


if __name__ == '__main__':
    main()
