"""Read-only provenance preflight for sealed iteration164 numerical receipts.

Run only after all resource batches have terminated. This module never imports
recording models, geographic evaluation callbacks, or reference documents.
"""

import hashlib
import json
from pathlib import Path

import evaluation


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PHASES = ('search', 'native', 'zero')
BRANCH_PHASE = {'native': 'baseline', 'zero': 'candidate'}
IDENTITY_FIELDS = ('session_id', 'input_manifest_sha256',
                   'analysis_manifest_sha256', 'evidence_sha256')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    return json.loads(Path(path).read_text())


def _canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


def _binding(member, plan, root):
    binding = member.get('binding')
    if member.get('binding_status') != 'complete':
        _require(binding is None, member['label'] + ': failed binding has a document')
        return 'unavailable'
    _require(isinstance(binding, dict), member['label'] + ': missing complete binding')
    session = member['membership']['session_id']
    model = binding['model_identity']
    expected = binding['expected_input_binding']
    _require(binding.get('session_id') == session == model.get('session_id'),
             member['label'] + ': binding/model session differs')
    mint = member['membership'].get('recording_manifest_sha256')
    if mint is not None:
        _require(mint == model.get('input_manifest_sha256'),
                 member['label'] + ': mint input differs')
    for physical, model_field in (('input_digest', 'input_manifest_sha256'),
                                  ('evidence_digest', 'evidence_sha256'),
                                  ('bank_signature', 'bank_signature')):
        _require(expected.get(physical) == model.get(model_field),
                 member['label'] + ': physical ' + physical + ' differs')
    # The physical score signature binds the reconstructed prior plus HARD60
    # score, while model.score_signature binds configuration.scores metadata.
    _require(isinstance(expected.get('score_signature'), str)
             and bool(expected['score_signature']),
             member['label'] + ': missing physical score signature')
    relative = Path(binding['document_path'])
    base = Path(root).resolve()
    path = (base / relative).resolve()
    _require(not relative.is_absolute() and path.is_relative_to(base),
             member['label'] + ': document path escapes repository')
    document_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(document_sha == binding.get('document_sha256')
             == plan['input_sha256'].get(relative.as_posix()),
             member['label'] + ': document input closure differs')
    document = _read(path)
    _require(set(document) == {*IDENTITY_FIELDS, 'configuration'}
             and set(document['configuration']) == {'prior', 'scores', 'run'},
             member['label'] + ': sanitized document shape differs')
    for field in IDENTITY_FIELDS:
        _require(document.get(field) == model.get(field),
                 member['label'] + ': document ' + field + ' differs')
    for field, section in (('prior_signature', 'prior'),
                           ('score_signature', 'scores')):
        _require(model.get(field) == _canonical_digest(document['configuration'][section]),
                 member['label'] + ': document ' + field + ' differs')
    return 'complete'


def _phase_slices(folder, label, phase, terminal, digest):
    suffix = '.finished.json' if phase == 'search' else '.done.json'
    claims = sorted((folder / 'slices').glob('*.started.json'))
    cap = 6 if phase == 'search' else 2
    _require(len(claims) <= cap, label + '/' + phase + ': slice cap exceeded')
    if terminal['status'] == 'complete':
        _require(bool(claims), label + '/' + phase + ': complete without slices')
    admission = (isinstance(terminal.get('reason'), str)
                 and terminal['reason'].startswith(('Dependency admission failed:',
                                                    'Inference binding failed:'))
                 and 'binding_status' in terminal)
    if terminal['status'] == 'not-run-search-failed':
        _require(not claims or admission,
                 label + '/' + phase + ': not-run phase has slices')
    expected_phase = BRANCH_PHASE.get(phase)
    for slot, claim_path in enumerate(claims, 1):
        prefix = f'{slot:02}' if phase == 'search' else f'{expected_phase}-{slot:02}'
        _require(claim_path.name == prefix + '.started.json',
                 label + '/' + phase + ': noncontiguous or foreign claim filename')
        claim = _read(claim_path)
        _require(claim.get('protocol_sha256') == digest,
                 label + '/' + phase + ': claim protocol differs')
        if phase == 'search':
            _require(claim.get('slot') == slot and not isinstance(claim.get('slot'), bool),
                     label + '/search: claim slot differs')
        else:
            _require(claim.get('phase') == expected_phase and claim.get('slice') == slot
                     and not isinstance(claim.get('slice'), bool),
                     label + '/' + phase + ': claim phase/slice differs')
        finish = _read(claim_path.with_name(prefix + suffix))
        _require(finish.get('protocol_sha256') == digest,
                 label + '/' + phase + ': finish protocol differs')
        if phase != 'search':
            _require(finish.get('label') == label and finish.get('branch') == phase
                     and finish.get('slice') == slot,
                     label + '/' + phase + ': done identity differs')
        if slot < len(claims):
            _require(finish.get('status') == 'pending',
                     label + '/' + phase + ': nonfinal slice is terminal')
        else:
            admission_after_pending = (
                terminal['status'] in ('failed', 'not-run-search-failed')
                and finish.get('status') == 'pending'
                and admission
            )
            _require(finish.get('status') == terminal['status'] or admission_after_pending,
                     label + '/' + phase + ': last slice status differs')
            if phase != 'search' and not admission_after_pending:
                _require(finish == terminal,
                         label + '/' + phase + ': done and result differ')
    return len(claims)


def preflight(plan, directory, digest, *, root=ROOT):
    """Authenticate all193 first, then check extra source/receipt provenance.

    Returns counts and the frozen gate's raw JSON hash inventory. Nothing here
    computes or reads position error; callers must invoke the existing reporting
    entrypoint separately, after reviewing this result.
    """
    hashes = evaluation.authenticate(plan, directory, digest)
    directory = Path(directory)
    counts = dict(members=0, phases=0, slices=0, complete_bindings=0,
                  unavailable_bindings=0)
    for member in plan['members']:
        label = member['label']
        status = _binding(member, plan, root)
        counts[status + '_bindings'] += 1
        terminals = {phase: _read(directory / label / phase / 'result.json')
                     for phase in PHASES}
        search = terminals['search']['status']
        if search != 'complete':
            for phase in ('native', 'zero'):
                _require(terminals[phase]['status'] == 'not-run-search-failed',
                         label + ': continuation despite unsuccessful search')
        else:
            for phase in ('native', 'zero'):
                continuation = terminals[phase]
                if continuation['status'] == 'not-run-search-failed':
                    reason = continuation.get('reason')
                    _require(isinstance(reason, str)
                             and reason.startswith(('Dependency admission failed:',
                                                    'Inference binding failed:'))
                             and 'binding_status' in continuation,
                             label + ': successful search has unexplained not-run continuation')
        for phase, terminal in terminals.items():
            counts['slices'] += _phase_slices(directory / label / phase,
                                               label, phase, terminal, digest)
            counts['phases'] += 1
        counts['members'] += 1
    return dict(counts=counts, receipt_sha256=hashes,
                limitations='Search finish carries no label/slot; filename and claim slot are checked.')
