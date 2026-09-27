"""Independent all-window evidence for the entire new development cohort."""
import hashlib
import json
import signal
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from run_new_data_mismatch_diagnostic import (
    ROOT, NativeDwell, asdict, fitted, observation, sha256,
)


def select_cases(dataset):
    cases = dataset['cases']
    if not cases or len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('empty or duplicate cases')
    if any(c['split'] != 'dev' or c['is_holdout']
           or c['evaluation_role'] != 'newdevelopment' for c in cases):
        raise ValueError('development-only diagnostic')
    return sorted(cases, key=lambda c: (c['session_id'], c['visit_index']))


def run():
    signal.alarm(120)
    output = ROOT / 'new_data_all_window_evidence.json'
    if output.exists():
        raise FileExistsError(output)
    dataset_path = ROOT / 'new_data/cases.json'
    reference_path = ROOT / 'new_data_v6.json'
    library = ROOT / 'native/libblind_strided_v4.so'
    receipt_path = library.with_name(library.name + '.build.json')
    protected = {p: sha256(p) for p in (
        dataset_path, reference_path, library, receipt_path, Path(__file__),
        Path(__file__).with_name('run_new_data_mismatch_diagnostic.py'),
        Path(__file__).with_name('ALL_WINDOW_DESIGN.md'), ROOT / 'tracking.py')}
    reference = json.loads(reference_path.read_text())
    build = json.loads(receipt_path.read_text())
    if (reference['dataset_sha256'] != protected[dataset_path]
            or reference['baseline_sha256'] != protected[library]
            or build['binary_sha256'] != protected[library]):
        raise ValueError('reference or binary provenance differs')
    for name, digest in build['sources_sha256'].items():
        path = Path(name)
        if sha256(path) != digest:
            raise ValueError('frozen source differs')
        protected[path] = digest
    refs = {(r['case_id'], r['rx']): r['reference'] for r in reference['rows']}
    cases = select_cases(json.loads(dataset_path.read_text()))
    if set(refs) != {(c['case_id'], rx) for c in cases for rx in range(2)}:
        raise ValueError('reference membership differs')
    rows, workspaces = [], {}
    with ExitStack() as stack:
        for case in cases:
            path = (dataset_path.parent / case['raw_npy']['path']).resolve()
            if not path.is_relative_to(dataset_path.parent):
                raise ValueError('IQ path escapes dataset')
            digest = case['raw_npy']['sha256'].removeprefix('sha256:')
            if sha256(path) != digest:
                raise ValueError('IQ hash differs')
            raw = np.load(path, allow_pickle=False)
            rate = case['rate_hz']
            if raw.shape != (rate * 120 // 1000, 2, 2) or raw.dtype != np.dtype('<i2'):
                raise ValueError('invalid IQ geometry')
            memory_hash = hashlib.sha256(raw).hexdigest()
            geometry = (rate, case['edge'])
            if geometry not in workspaces:
                workspaces[geometry] = stack.enter_context(NativeDwell(library, *geometry, 512))
            for rx in range(2):
                result = workspaces[geometry].run(raw[:, rx, :], maximum=6, seeded=False)
                if result.confirmation_count != 6 or result.confirmation_window_mask != 63:
                    raise ValueError('incomplete window coverage')
                candidates = [fitted(result, i) for i in range(6)]
                ref = refs[(case['case_id'], rx)]
                if candidates[0] != (observation(ref) if ref else None):
                    raise ValueError('top result differs from frozen reference')
                rows.append({'case_id': case['case_id'], 'rx': rx, 'rate_hz': rate,
                             'raw_sha256': digest,
                             'rank_order': [int(result.rank.order[i]) for i in range(6)],
                             'candidates': [asdict(c) for c in candidates]})
            if hashlib.sha256(raw).hexdigest() != memory_hash or sha256(path) != digest:
                raise ValueError('IQ changed during diagnostic')
    if any(sha256(p) != digest for p, digest in protected.items()):
        raise ValueError('protected input changed during diagnostic')
    payload = {'schema': 'org.leo.research.all-window-evidence/v1',
               'qualification_result': False, 'physical_truth': False,
               'performance_timing_valid': False, 'post_outcome_development': True,
               'holdout_opened': False, 'seeded': False, 'maximum': 6,
               'source_sha256': {str(p): d for p, d in protected.items()},
               'receiver_visits': len(rows), 'rows': rows}
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'receiver_visits': len(rows), 'sha256': sha256(output)}))


if __name__ == '__main__':
    run()
