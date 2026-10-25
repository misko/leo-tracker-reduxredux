"""Bounded prediction preflight: immutable inputs and independent pure algebra."""
import hashlib
import json
from pathlib import Path
import signal
import sys
import time
from unittest.mock import patch

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'prediction'
sys.path.insert(0, str(SCI))
import prediction as p
import test_prediction as fixtures


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / 'preflight.json'
    if output.exists():
        raise FileExistsError('preserve frozen receipt')
    began = time.monotonic()
    protocol_hash = sha(SCI / 'protocol.json')
    protocol = read(SCI / 'protocol.json')
    checks = []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    bad = [path for path, expected in protocol['source_input_hashes'].items() if sha(path) != expected]
    check('frozen source, exact prior RF seal and all inputs unchanged',
          not bad and protocol_hash == read(SCI / 'protocol_seal.json')['protocol_sha256'],
          bindings=len(protocol['source_input_hashes']), mismatches=bad)
    check('no corpus score before preflight; original budgets/denominators',
          not (SCI / 'execution_started.json').exists() and protocol['candidate'] == 57450 and
          protocol['order'] == ['owner1', 'owner0', 'owner2'] and protocol['budget']['total_worker_seconds'] == 600 and
          protocol['budget']['workers'] == 2 and protocol['budget']['BLAS_threads'] == 1 and
          protocol['position_fits'] == protocol['GPS_used'] == protocol['retries'] == 0)
    check('independent mixture/Schur and denominator algebra fixture passed', read(HERE / 'math_checks.json')['all_passed'])
    test_status = pytest.main(['-q', '-p', 'no:cacheprovider', str(SCI / 'test_prediction.py')])
    signal.setitimer(signal.ITIMER_REAL, 0)
    check('seven component-owned covariance/81alias/support/response-redaction tests independently rerun', test_status == 0)

    # Valid constant covariance and a phase-independent kernel permit an exact
    # latent Gaussian posterior oracle for the exported D constant uncertainty.
    cd, base, _, support = fixtures.diagnostic_fixture()
    covariance = base['covariance'].copy()
    covariance[:57, :57] += 300. ** 2
    covariance[57:, 57:] += 300. ** 2
    base = dict(base, covariance=covariance)
    shape = np.column_stack((np.ones(61) * .3, np.linspace(-.2, .4, 61), np.sin(cd['target_track']['times']) * .1))

    def geometry(d, x, phases):
        return dict(frequency_hz=np.zeros((len(phases), 61)),
            shape_columns_hz=np.broadcast_to(shape, (len(phases), 61, 3)).copy(), elevation_deg=np.ones((len(phases), 61)))

    with patch.object(p.k.m.q, 'phase_geometry', side_effect=geometry), patch.object(p, 'supports', side_effect=support):
        actual = p.diagnostic_rule(cd, base, 64, time.monotonic() + 20)
    signal.setitimer(signal.ITIMER_REAL, 0)
    b = shape * base['q'][:, None]
    full = covariance + b @ b.T
    dd = full[:57, :57]
    latent_cross = np.column_stack((b[:57], np.ones(57) * 300.)).T
    latent_mean = latent_cross @ np.linalg.solve(dd, base['raw'][:57])
    latent_covariance = np.eye(4) - latent_cross @ np.linalg.solve(dd, latent_cross.T)
    constant_mean_error = abs(actual['Dconstant_mean_Hz'] - 300 * latent_mean[-1])
    constant_sd_error = abs(actual['Dconstant_SD_Hz'] - 300 * np.sqrt(latent_covariance[-1, -1]))
    shape_error = float(np.max(abs(actual['shape_covariance'] - latent_covariance[:3, :3])))
    check('D-only latent shape/constant variance matches independent dense Gaussian posterior',
          constant_mean_error < 1e-6 and constant_sd_error < 1e-6 and shape_error < 1e-8,
          constant_mean_error_hz=constant_mean_error, constant_sd_error_hz=constant_sd_error,
          maximum_shape_covariance_error=shape_error)
    text = (SCI / 'prediction.py').read_text()
    check('completed evidence checkpoint saved before independent reference',
          text.index("write(name+'_primary_checkpoint.json',row)") < text.index('reference,root_reference=sr.sm.reference'))
    check('scientific freeze unchanged throughout independent tests',
          sha(SCI / 'protocol.json') == protocol_hash and all(sha(path) == h for path, h in protocol['source_input_hashes'].items()))
    elapsed = time.monotonic() - began
    prior = (read(HERE / 'math_checks.json')['seconds'] + read(HERE / 'archival_check.json')['seconds'] +
             read(HERE / 'math_serialization_failure01.json')['first_attempt_tool_wall_seconds'])
    receipt = dict(all_passed=all(q['passed'] for q in checks), protocol_sha256=protocol_hash,
        checks=checks, source_sha256=sha(__file__), seconds=elapsed,
        cumulative_audit_seconds=elapsed + prior, audit_cap_seconds=180,
        corpus_propagation_calls=0, new_corpus_scores=0, position_fits=0, geographic_truth_read=False,
        authorization='standing coordinator plan authorizes this frozen bounded run on independent pass',
        scope='same57450 versus unresolved W, D physical in both; identical D marginal and shared covariance; no validated identity or position adoption')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], protocol_sha256=protocol_hash,
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], failed=[q for q in checks if not q['passed']])))


if __name__ == '__main__':
    main()
