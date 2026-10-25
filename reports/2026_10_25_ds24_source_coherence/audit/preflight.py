"""Independent frozen source-coherence preflight; pure fixtures, no corpus score."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
import pytest
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'scientific'
sys.path.insert(0, str(SCI))
import coherence as c
import test_coherence as fixtures

read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    output = HERE / 'preflight.json'
    if output.exists():
        raise FileExistsError('preserve preflight')
    p = read(SCI / 'protocol.json'); digest = sha(SCI / 'protocol.json')
    checks = []

    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))

    check('exact frozen source, original observations and prior research bindings',
          digest == read(SCI / 'protocol_seal.json')['protocol_sha256'] and
          all(sha(path) == h for path, h in p['source_input_hashes'].items()), bindings=len(p['source_input_hashes']))
    check('same100 observations, normalized fixed cuts/classes and unchanged budgets',
          p['cuts_after_W_indices'] == [14, 21, 29] and p['class_prior'] == .25 and
          p['scientific_seconds'] == 600 and p['workers'] == 2 and p['BLAS_threads'] == 1 and
          p['position_fits'] == p['scientific_retries'] == 0 and not p['GPS_used'] and
          not (SCI / 'execution_started.json').exists())
    check('independent native/gauge/duration and remote-noise/mixture math checks pass',
          read(HERE / 'math_checks.json')['all_passed'] and read(HERE / 'ownership_check.json')['all_passed'])
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(SCI / 'test_coherence.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('ten final owned tests independently rerun, including cache and Path ports', status == 0)

    base = fixtures.base_model()
    rng = np.random.default_rng(202610252252)
    phases = np.array([-.31, .17, .61])
    frequency = rng.normal(size=(3, 100))
    shape = rng.normal(size=(3, 100, 3)) * .25
    geometry = lambda values: dict(frequency_hz=frequency, shape_columns_hz=shape, elevation_deg=np.ones((3, 100)))
    prior = c.sr.law(dict(target=dict(phase_nu=3., phase_mean_s=.2, phase_sd_s=2.)))
    errors = []
    for row in c.allocations(np.linspace(236, 265, 43), period=17.):
        comp, columns = c.model_component(base, row)
        actual = c.kernel(comp, geometry, prior, phases)
        expected = []
        for i, phi in enumerate(phases):
            b = shape[i] * comp['q'][:, None]
            covariance = comp['covariance'] + b @ b.T
            root = np.linalg.cholesky(covariance)
            raw = comp['raw'][None] - frequency[i] * comp['q'][None] + comp['shifts']
            white = solve_triangular(root, raw.T, lower=True)
            costs = np.sum(white ** 2, axis=0) + 2 * np.log(np.diag(root)).sum() + 100 * np.log(2 * np.pi)
            expected.append(logsumexp(-costs / 2) - np.log(81) + prior['distribution'].logpdf(phi) - np.log(prior['mass']))
        errors.append(float(np.max(abs(actual - expected))))
    check('all11 allocation kernels match independent full100row Gaussian density on81aliases',
          max(errors) <= 1e-8, maximum_objective_density_error=max(errors))
    source = (SCI / 'coherence.py').read_text()
    check('D and whole-W null replays are enforced before class bounds/order',
          "'original D evidence replay prerequisite failed'" in source and
          "'whole-null/D marginal replay prerequisite failed'" in source and
          source.index("'D_replay.json'") < source.index('bounded=[];best=') and
          source.index("'replay.json'") < source.index('bounded=[];best='))
    check('remote support is bounded without prior truncation or calibrated-mixture claim',
          'global_joint_remote_upper_log_evidence' in source and 'Gamma_mixture_ceiling_claimed=False' in source and
          'remote_not_renormalized=True' in source and 'if not all(row[\'independent_quadrature_passed\']' in source)
    check('source/protocol bytes unchanged through independent pure checks',
          digest == sha(SCI / 'protocol.json') and all(sha(path) == h for path, h in p['source_input_hashes'].items()))
    seconds = time.monotonic() - began
    cumulative = seconds + read(HERE / 'math_checks.json')['seconds'] + read(HERE / 'ownership_check.json')['seconds']
    receipt = dict(all_passed=all(q['passed'] for q in checks), checks=checks, protocol_sha256=digest,
        source_sha256=sha(__file__), seconds=seconds, cumulative_audit_seconds=cumulative, audit_cap_seconds=180,
        corpus_propagation_calls=0, new_corpus_scores=0, position_fits=0, geographic_truth_read=False,
        scope='All-points conditional coherence; normalized finite cut/allocation prior. Valid whole-domain interval ordering is distinct from absolute precision, source identity, join proof and acceptance.',
        authorization='standing coordinator plan authorizes this exact bounded experiment on independent pass')
    receipt['all_passed'] &= cumulative <= 180
    with output.open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], protocol_sha256=digest,
        cumulative_audit_seconds=cumulative, failed=[q for q in checks if not q['passed']])))


if __name__ == '__main__':
    main()
