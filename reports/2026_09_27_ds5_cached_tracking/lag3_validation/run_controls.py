"""One bounded independent proposal-only audit of frozen injected controls."""
import hashlib
import json
import signal
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTROL = ROOT / 'lag3_controls'
KERNEL = ROOT / 'lag3_proposal'
sys.path.insert(0, str(KERNEL))
from lag3_proposal import Lag3Proposal  # noqa: E402
from score import score_case  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    signal.alarm(120)
    output = HERE / 'results.json'
    if output.exists():
        raise FileExistsError(output)
    dataset_path = CONTROL / 'cases.json'
    design_path = CONTROL / 'design.json'
    library = KERNEL / 'liblag3_proposal.so'
    receipt_path = KERNEL / 'liblag3_proposal.so.build.json'
    dataset = json.loads(dataset_path.read_text())
    design = json.loads(design_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    cases = {c['case_id']: c for c in dataset['cases']}
    recipes = {c['case_id']: c for c in design['cases']}
    if set(cases) != set(recipes) or len(cases) != 20:
        raise ValueError('control membership differs')
    if sha(library) != receipt['binary_sha256']:
        raise ValueError('kernel binary differs from build receipt')
    protected = {Path(p): h for p, h in receipt['sources_sha256'].items()}
    protected.update({p: sha(p) for p in (
        library, receipt_path, dataset_path, design_path,
        CONTROL / 'source_lock.json', CONTROL / 'build_controls.py',
        HERE / 'score.py', HERE / 'DESIGN.md', Path(__file__))})
    if sha(design_path) != dataset['design_sha256'].removeprefix('sha256:'):
        raise ValueError('control design differs from materialization')
    if sha(CONTROL / 'build_controls.py') != dataset['generator_sha256'].removeprefix('sha256:'):
        raise ValueError('control generator differs from materialization')
    if any(sha(p) != h for p, h in protected.items()):
        raise ValueError('frozen kernel source differs')
    rows, kernels = [], {}
    with ExitStack() as stack:
        for case_id in sorted(cases):
            case, recipe = cases[case_id], recipes[case_id]
            path = (CONTROL / case['raw_npy']['path']).resolve()
            if not path.is_relative_to(CONTROL):
                raise ValueError('control IQ escapes dataset')
            expected = case['raw_npy']['sha256'].removeprefix('sha256:')
            if sha(path) != expected:
                raise ValueError('control IQ changed')
            raw = np.load(path, allow_pickle=False)
            memory_hash = hashlib.sha256(raw).hexdigest()
            geometry = (case['rate_hz'], case['edge'])
            if geometry not in kernels:
                kernels[geometry] = stack.enter_context(Lag3Proposal(*geometry, library=library))
            # The control generator uses templates.template_sha256's canonical
            # complex64 payload; the kernel also records its complex128 bytes.
            canonical_template_hash = hashlib.sha256(
                kernels[geometry].template.astype('<c8').tobytes()).hexdigest()
            for rx in range(2):
                injected = case['injected']['receivers'][rx]
                if injected['receiver'] != rx:
                    raise ValueError('receiver truth order differs')
                for component in injected['components']:
                    if component['type'] == 'pilot' and (
                        component['template_sha256'].removeprefix('sha256:')
                        != canonical_template_hash
                    ):
                        raise ValueError('proposal template differs from injected template')
                result = kernels[geometry].run(raw, rx)
                candidates = result['candidates']
                rows.append({'case_id': case_id, 'rx': rx, 'rate_hz': case['rate_hz'],
                             'kind': recipe['kind'], 'raw_sha256': expected,
                             'template_sha256': kernels[geometry].template_sha256,
                             'canonical_complex64_template_sha256': canonical_template_hash,
                             'candidates': candidates, **score_case(recipe, candidates)})
            if hashlib.sha256(raw).hexdigest() != memory_hash or sha(path) != expected:
                raise ValueError('control IQ mutated')
    if any(sha(p) != h for p, h in protected.items()):
        raise ValueError('protected input changed during audit')
    groups = {}
    for row in rows:
        key = f"{row['rate_hz']}:{row['kind']}"
        group = groups.setdefault(key, {'receiver_cases': 0, 'pilot_truth_cases': 0,
                                       'coordinate_matches': 0, 'supported_matches': 0,
                                       'supported_proposals': 0})
        group['receiver_cases'] += 1
        group['pilot_truth_cases'] += row['pilot_truth_count'] > 0
        group['coordinate_matches'] += row['any_coordinate_match'] is True
        group['supported_matches'] += row['any_supported_coordinate_match'] is True
        group['supported_proposals'] += row['supported_proposal_count']
    payload = {'schema': 'org.leo.research.lag3-injected-truth-audit/v1',
               'scope': 'proposal-coordinate diagnostic only; no GLRT decision or timing claim',
               'performance_timing_valid': False, 'detector_qualified': False,
               'association': {'timing_us': 2.0, 'cfo_hz': 8000.0},
               'source_sha256': {str(p): h for p, h in protected.items()},
               'summary': groups, 'rows': rows}
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    print(json.dumps(groups, indent=2))


if __name__ == '__main__':
    run()
