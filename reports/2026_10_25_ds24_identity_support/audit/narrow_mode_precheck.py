"""Independent analytic missed-mode probe; no corpus reads or propagation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np
from scipy.special import ndtr

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'scientific/support_math.py'
PRIOR_PROBE_SECONDS = 0.006001601926982403


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / 'narrow_mode_precheck.json'
    if output.exists():
        raise FileExistsError('preserve original failed numerical receipt')
    source_hash = sha(SOURCE)
    spec = importlib.util.spec_from_file_location('candidate_support_math', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.monotonic()
    rows = []
    for sigma in (1e-2, 1e-3, 1e-4, 1e-5):
        center, offset = .123456789, -1e6
        def density(x):
            peak = -.5*((x-center)/sigma)**2 - np.log(sigma*np.sqrt(2*np.pi))
            return offset + np.logaddexp(np.log(.99)+peak, np.log(.01/2))
        mass = .99*(ndtr((1-center)/sigma)-ndtr((-1-center)/sigma))+.01
        exact = -2*(offset+np.log(mass))
        primary = module.log_integrate(density, [[-1., 1.]])
        reference = module.reference(density, [[-1., 1.]])
        primary_error = abs(primary['objective']-exact)
        reference_error = abs(reference['objective']-exact)
        shared_agreement = abs(primary['objective']-reference['objective'])
        falsely_qualified = bool(primary['success'] and reference['success'] and
                                 shared_agreement <= 1e-3 and
                                 max(primary_error, reference_error) > 1e-3)
        rows.append(dict(sigma_s=sigma, center_s=center, log_density_offset=offset,
                         exact_objective=float(exact), primary=primary, reference=reference,
                         primary_exact_error=float(primary_error),
                         reference_exact_error=float(reference_error),
                         primary_reference_difference=float(shared_agreement),
                         falsely_qualified=falsely_qualified))
    elapsed = time.monotonic()-started
    receipt = dict(all_passed=not any(row['falsely_qualified'] for row in rows),
                   purpose='analytic narrow-mode coverage, not a real-candidate score',
                   candidate_source=str(SOURCE), candidate_source_sha256=source_hash,
                   source_unchanged=source_hash == sha(SOURCE),
                   audit_source_sha256=sha(__file__), rows=rows,
                   numeric_seconds=elapsed, prior_exploratory_seconds=PRIOR_PROBE_SECONDS,
                   cumulative_numeric_seconds=elapsed+PRIOR_PROBE_SECONDS,
                   propagation_calls=0, position_fits=0, corpus_observations_read=False)
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'],
                         source_unchanged=receipt['source_unchanged'],
                         falsely_qualified_sigmas=[r['sigma_s'] for r in rows if r['falsely_qualified']],
                         cumulative_numeric_seconds=receipt['cumulative_numeric_seconds'])))


if __name__ == '__main__':
    main()
