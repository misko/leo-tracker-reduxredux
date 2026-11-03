"""Apply the previously registered kernel bounds to an exact replay comparison.

All fields except phase marginal and orbital MAP diagnostics remain exact.
This produces an additional assessment and never changes the strict receipt.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

PROTOCOL_SHA256 = '0f6f81ae83918bd6a1dd3035aa12b0cd117ea82d33eaf8b9f53b3a3dd9ec3832'


def assess(strict, protocol):
    if hashlib.sha256(protocol).hexdigest() != PROTOCOL_SHA256:
        raise ValueError('Original predeclared kernel protocol required')
    if not (strict['both_calibration_arms_required'] and strict['tolerance'] == 0
            and strict['exact_leaves'] > 0 and strict['verified_runtime_files']):
        raise ValueError('Complete pinned exact replay comparison required')
    tolerances = json.loads(protocol)['kernel_tolerances']
    limits = {'phase_marginals': tolerances['phase_marginal_atol'],
              'orbital_map_mean': tolerances['orbital_map_mean_atol']}
    accepted, unresolved = [], []
    for difference in strict['differences']:
        parts = difference.get('path', '').split('/')
        field = (parts[-3] if len(parts) >= 3 and parts[-3] in limits
                 and parts[-2].isdigit() and parts[-1].isdigit() else None)
        a, b = difference.get('baseline'), difference.get('candidate')
        if (field and not difference.get('reason') and type(a) is float and type(b) is float
                and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= limits[field]):
            accepted.append(dict(difference, absolute_difference=abs(a-b),
                                 predeclared_absolute_limit=limits[field]))
        else:
            unresolved.append(difference)
    return dict(strict, passed=not unresolved, differences=unresolved,
                tolerance='predeclared_kernel_diagnostics_only',
                kernel_protocol_sha256=PROTOCOL_SHA256,
                roundoff_differences=accepted, strict_comparison_passed=strict['passed'],
                all_other_scientific_fields_exact=not unresolved)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--strict', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = a.strict.read_bytes()
    result = assess(json.loads(raw), a.protocol.read_bytes())
    result['strict_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'], tolerated=len(result['roundoff_differences']),
                          unresolved=len(result['differences']))))
    if not result['passed']:
        raise SystemExit(1)
