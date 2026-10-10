"""Full193 postseal reporting gate. No recording or reference access on import."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = HERE.parent/'2026_10_09_position_error_iter129'
PHASES = ('search', 'native', 'zero')
ARMS = ('zero-c', 'fitted-c')
TERMINAL = {'complete', 'failed', 'incomplete', 'budget-exhausted', 'not-run-search-failed'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_files(plan, group):
    for name, expected in plan[group].items():
        if sha(ROOT/name) != expected:
            raise ValueError('bound artifact changed: '+name)


def authenticate(plan, directory, digest):
    """Require all phases and resource checkpoints before admitting evaluation."""
    directory = Path(directory)
    labels = [m['label'] for m in plan['members']]
    if len(labels) != 193 or len(set(labels)) != 193:
        raise ValueError('exact193 membership required')
    if Counter(m['dataset'] for m in plan['members']) != Counter(
            {'DS16':63, 'DS17':51, 'DS18':34, 'POST18-development':45}):
        raise ValueError('dataset membership differs')
    sessions = [m['membership']['session_id'] for m in plan['members']]
    if len(set(sessions)) != 193 or any(not isinstance(s, str) or not s for s in sessions):
        raise ValueError('unique recording sessions required')
    batches = plan['execution_batches']
    flattened = [label for batch in batches for label in batch]
    if len(flattened) != 193 or set(flattened) != set(labels):
        raise ValueError('resource membership differs')
    hashes, terminals = {}, {}
    def read(path, identity):
        raw = path.read_bytes()
        row = json.loads(raw)
        if any(row.get(k) != v for k, v in identity.items()):
            raise ValueError('foreign receipt: '+str(path))
        hashes[str(path.relative_to(directory))] = hashlib.sha256(raw).hexdigest()
        return row
    for label in labels:
        for phase in PHASES:
            identity = dict(label=label, protocol_sha256=digest)
            if phase != 'search':
                identity['branch'] = phase
            row = read(directory/label/phase/'result.json', identity)
            if row.get('status') not in TERMINAL:
                raise ValueError('unsealed member phase')
            if phase != 'search' and row.get('fallback_available') is not False:
                raise ValueError('undeclared fallback')
            terminals[label, phase] = row
            slices = directory/label/phase/'slices'
            claims = sorted(slices.glob('*.started.json'))
            suffix = '.finished.json' if phase == 'search' else '.done.json'
            finishes = sorted(slices.glob('*'+suffix))
            expected = {p.name.replace('.started.json', suffix) for p in claims}
            if {p.name for p in finishes} != expected:
                raise ValueError('orphan or unmatched invocation slice')
            for claim in claims:
                started = read(claim, dict(protocol_sha256=digest))
                finish = claim.with_name(claim.name.replace('.started.json', suffix))
                bound = dict(protocol_sha256=digest)
                if phase != 'search':
                    bound.update(label=label, branch=phase)
                completed = read(finish, bound)
                if 'slice' in started and completed.get('slice') != started['slice']:
                    raise ValueError('invocation slice number differs')
                for key, value in (('label', label), ('branch', phase)):
                    if key in started and started[key] != value:
                        raise ValueError('invocation claim identity differs')
                if completed.get('status') not in TERMINAL | {'pending'}:
                    raise ValueError('invalid invocation status')
    for index, labels_in_batch in enumerate(batches):
        for shard in (0, 1):
            identity = dict(protocol_sha256=digest, batch=index, shard=shard)
            stem = f'batch-{index}-shard-{shard}'
            read(directory/(stem+'.claim.json'), identity)
            row = read(directory/(stem+'.json'), identity)
            if row.get('status') != 'terminal':
                raise ValueError('controller checkpoint not terminal')
            members = row.get('members', [])
            if [m.get('label') for m in members] != labels_in_batch[shard::2]:
                raise ValueError('checkpoint membership differs')
            for member in members:
                if 'controller_failure' in member or member.get('phases') != {
                    phase: terminals[member['label'], phase]['status'] for phase in PHASES
                }:
                    raise ValueError('checkpoint phase status differs')
    # Authenticate raw claims, point caches, selected stages and timing receipts.
    # An unresolved claim under an explicit failed phase remains reportable;
    # it never becomes permission to repeat the operation.
    for label in labels:
        for path in sorted((directory/label).rglob('*.json')):
            read(path, dict(protocol_sha256=digest))
    return hashes


def reporter():
    source = (PARENT/'report_cohort.py').read_text()
    if source.count('BRANCHES = ("native", "fixed")') != 1 or source.count('return len(rows) == 12 and all(') != 1:
        raise ValueError('inherited reporter shape changed')
    source = source.replace('"fixed"', '"zero"').replace(
        'return len(rows) == 12 and all(', 'return len(rows) == 193 and all(')
    namespace = {'__name__': 'report129_for164', '__file__': str(PARENT/'report_cohort.py')}
    exec(compile(source, str(PARENT/'report_cohort.py'), 'exec'), namespace)
    return namespace


def build(plan, directory, digest, *, evaluation_factory=None):
    """No reference factory can run until all193 frozen selections are sealed."""
    evaluation_plan = json.loads((HERE/'evaluation_protocol.json').read_text())
    if evaluation_plan.get('numerical_protocol_digest') != digest:
        raise ValueError('evaluation protocol differs')
    if evaluation_plan.get('numerical_protocol_sha256') != sha(HERE/'protocol.json'):
        raise ValueError('numerical protocol bytes changed')
    verify_files(evaluation_plan, 'source_sha256')
    verify_files(plan, 'source_sha256')
    verify_files(plan, 'input_sha256')
    for name, expected in plan.get('runtime', {}).get('sha256', {}).items():
        if sha(name) != expected:
            raise ValueError('runtime changed: '+name)
    hashes = authenticate(plan, directory, digest)
    api = reporter()
    rows, _ = api['load_rows'](plan, directory, digest)
    if not api['sealed'](rows):
        raise ValueError('full193 phase seal required')
    summary = api['summarize'](rows, evaluate=None)
    verify_files(plan, 'evaluation_source_sha256')
    evaluate = (evaluation_factory or api['evaluation_callback'])(plan, rows)
    members = {m['label']: m for m in plan['members']}
    for raw, row in zip(rows, summary['rows'], strict=True):
        member = members[row['label']]
        row['membership'] = member['membership']
        row['exposure'] = member.get('exposure')
        row['binding_status'] = member.get('binding_status')
        row['binding_error'] = member.get('binding_error')
        for arm in ARMS:
            for branch in ('native', 'zero'):
                item = row['arms'][arm][branch]
                if item.get('status') != 'selected':
                    continue
                operation = raw['phases'][branch]['operational'][arm]
                try:
                    error = evaluate(row['label'], branch, arm, operation)
                    if isinstance(error, bool) or not isinstance(error, (float, int)) or not math.isfinite(error) or error < 0:
                        raise ValueError('invalid geographic error')
                    item.update(error_km=float(error), evaluation_status='complete')
                except Exception as exc:
                    item.update(evaluation_status='failed', evaluation_error=repr(exc))
            pair = row['arms'][arm]
            if all('error_km' in pair[b] for b in ('native', 'zero')):
                pair['delta_km'] = pair['zero']['error_km'] - pair['native']['error_km']
    summary['numerical_comparison_complete'] = summary['full_comparison_complete']
    summary['geographic_comparison_complete'] = all(
        row['arms'][arm][branch].get('evaluation_status') == 'complete'
        for row in summary['rows'] for arm in ARMS for branch in ('native', 'zero'))
    summary['full_comparison_complete'] = (
        summary['numerical_comparison_complete'] and summary['geographic_comparison_complete'])
    summary.update(protocol_sha256=digest, receipt_sha256=hashes,
                   scope='Consumed193 single-pass discovery; not deployed multiseparation parity')
    return summary
