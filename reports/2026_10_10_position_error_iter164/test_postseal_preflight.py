"""Synthetic receipt and clean-document checks; no recording or reference reads."""

import hashlib
import json

import pytest

from test_evaluation import corpus
import postseal_preflight as preflight


def write(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row))


def update(path, **changes):
    row = json.loads(path.read_text())
    row.update(changes)
    write(path, row)


def prepared(tmp_path):
    result_dir = tmp_path / 'results'
    plan = corpus(result_dir)
    plan['input_sha256'] = {}
    for member in plan['members']:
        member.update(binding=None, binding_status='failed')
        for phase in ('native', 'zero'):
            update(result_dir / member['label'] / phase / 'result.json',
                   status='not-run-search-failed')
    for batch in plan['execution_batches']:
        index = plan['execution_batches'].index(batch)
        for shard in (0, 1):
            path = result_dir / f'batch-{index}-shard-{shard}.json'
            row = json.loads(path.read_text())
            for member in row['members']:
                member['phases'].update(native='not-run-search-failed',
                                        zero='not-run-search-failed')
            write(path, row)
    return plan, result_dir


def complete_one(plan, result_dir, tmp_path):
    member = plan['members'][0]
    label = member['label']
    document = dict(session_id='S0', input_manifest_sha256='input0',
                    analysis_manifest_sha256='analysis0', evidence_sha256='evidence0',
                    configuration=dict(prior=dict(radius_km=300.), scores=dict(weight=2.), run={}))
    document_path = tmp_path / 'clean' / 'L0.json'
    write(document_path, document)
    relative = document_path.relative_to(tmp_path).as_posix()
    digest = hashlib.sha256(document_path.read_bytes()).hexdigest()
    plan['input_sha256'][relative] = digest
    member.update(binding_status='complete', binding=dict(
        session_id='S0', document_path=relative, document_sha256=digest,
        model_identity=dict(session_id='S0', input_manifest_sha256='input0',
                            analysis_manifest_sha256='analysis0', evidence_sha256='evidence0',
                            prior_signature=preflight._canonical_digest(document['configuration']['prior']),
                            score_signature=preflight._canonical_digest(document['configuration']['scores']),
                            bank_signature='bank0'),
        expected_input_binding=dict(input_digest='input0', evidence_digest='evidence0',
                                    score_signature='physical-score0',
                                    bank_signature='bank0')))
    search = result_dir / label / 'search'
    update(search / 'result.json', status='complete')
    write(search / 'slices' / '01.started.json', dict(protocol_sha256='d', slot=1))
    write(search / 'slices' / '01.finished.json',
          dict(protocol_sha256='d', status='complete', elapsed_s=1.))
    for phase, claim_phase in (('native', 'baseline'), ('zero', 'candidate')):
        folder = result_dir / label / phase
        update(folder / 'result.json', status='complete', slice=1)
        write(folder / 'slices' / f'{claim_phase}-01.started.json',
              dict(protocol_sha256='d', phase=claim_phase, slice=1))
        write(folder / 'slices' / f'{claim_phase}-01.done.json',
              json.loads((folder / 'result.json').read_text()))
    path = result_dir / 'batch-0-shard-0.json'
    row = json.loads(path.read_text())
    row['members'][0]['phases'] = dict.fromkeys(('search', 'native', 'zero'), 'complete')
    write(path, row)
    return member, document_path


def test_valid_full193_source_only_preflight(tmp_path):
    plan, result_dir = prepared(tmp_path)
    complete_one(plan, result_dir, tmp_path)
    receipt = preflight.preflight(plan, result_dir, 'd', root=tmp_path)
    assert receipt['counts'] == dict(members=193, phases=579, slices=3,
                                     complete_bindings=1, unavailable_bindings=192)
    assert len(receipt['receipt_sha256']) == 579 + 4 * len(plan['execution_batches']) + 6


def test_frozen_gate_runs_before_extra_checks(tmp_path):
    plan, result_dir = prepared(tmp_path)
    (result_dir / 'L192' / 'zero' / 'result.json').unlink()
    with pytest.raises(FileNotFoundError):
        preflight.preflight(plan, result_dir, 'd', root=tmp_path)


def test_completed_search_requires_paired_slice(tmp_path):
    plan, result_dir = prepared(tmp_path)
    complete_one(plan, result_dir, tmp_path)
    (result_dir / 'L0' / 'search' / 'slices' / '01.started.json').unlink()
    (result_dir / 'L0' / 'search' / 'slices' / '01.finished.json').unlink()
    with pytest.raises(ValueError, match='complete without slices'):
        preflight.preflight(plan, result_dir, 'd', root=tmp_path)


def test_explicit_admission_failure_after_pending_slice_is_covered(tmp_path):
    plan, result_dir = prepared(tmp_path)
    member, _ = complete_one(plan, result_dir, tmp_path)
    search = result_dir / member['label'] / 'search'
    update(search / 'result.json', status='failed',
           reason='Dependency admission failed: unavailable', binding_status='complete')
    update(search / 'slices' / '01.finished.json', status='pending')
    for phase in ('native', 'zero'):
        folder = result_dir / member['label'] / phase
        update(folder / 'result.json', status='not-run-search-failed',
               reason='Dependency admission failed: unavailable', binding_status='complete')
        claim_phase = preflight.BRANCH_PHASE[phase]
        update(folder / 'slices' / f'{claim_phase}-01.done.json', status='pending')
    path = result_dir / 'batch-0-shard-0.json'
    row = json.loads(path.read_text())
    row['members'][0]['phases'] = dict(search='failed', native='not-run-search-failed',
                                      zero='not-run-search-failed')
    write(path, row)
    assert preflight.preflight(plan, result_dir, 'd', root=tmp_path)['counts']['slices'] == 3


@pytest.mark.parametrize('change, expected', [
    ('slot', 'claim slot differs'),
    ('done', 'done and result differ'),
    ('phase', 'claim phase/slice differs'),
    ('cross', 'continuation despite unsuccessful search'),
    ('notrun', 'successful search has unexplained not-run continuation'),
    ('binding', 'binding/model session differs'),
    ('document', 'document input closure differs'),
    ('mint', 'mint input differs'),
    ('prior', 'document prior_signature differs'),
])
def test_corrupted_provenance_rejected(tmp_path, change, expected):
    plan, result_dir = prepared(tmp_path)
    member, document = complete_one(plan, result_dir, tmp_path)
    if change == 'slot':
        update(result_dir / 'L0' / 'search' / 'slices' / '01.started.json', slot=2)
    elif change == 'done':
        update(result_dir / 'L0' / 'native' / 'slices' / 'baseline-01.done.json', reason='changed')
    elif change == 'phase':
        update(result_dir / 'L0' / 'zero' / 'slices' / 'candidate-01.started.json', phase='baseline')
    elif change == 'cross':
        update(result_dir / 'L0' / 'search' / 'result.json', status='failed')
        update(result_dir / 'L0' / 'search' / 'slices' / '01.finished.json', status='failed')
        path = result_dir / 'batch-0-shard-0.json'
        row = json.loads(path.read_text())
        row['members'][0]['phases']['search'] = 'failed'
        write(path, row)
    elif change == 'notrun':
        update(result_dir / 'L0' / 'native' / 'result.json', status='not-run-search-failed')
        update(result_dir / 'L0' / 'native' / 'slices' / 'baseline-01.done.json',
               status='not-run-search-failed')
        path = result_dir / 'batch-0-shard-0.json'
        row = json.loads(path.read_text())
        row['members'][0]['phases']['native'] = 'not-run-search-failed'
        write(path, row)
    elif change == 'binding':
        member['binding']['session_id'] = 'different'
    elif change == 'document':
        update(document, analysis_manifest_sha256='different')
    elif change == 'mint':
        member['membership']['recording_manifest_sha256'] = 'different'
    elif change == 'prior':
        member['binding']['model_identity']['prior_signature'] = 'different'
    with pytest.raises(ValueError, match=expected):
        preflight.preflight(plan, result_dir, 'd', root=tmp_path)
