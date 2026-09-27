"""Add assessment summary flags without changing scores or association."""
import json
from pathlib import Path
import run_real as original


def annotate(assessment):
    result = dict(assessment)
    matched = assessment['reference_outcome'] == 'retained_associated'
    result.update(matched_reference=matched,
        lost_reference=assessment['reference_active'] and not matched,
        additional_or_mismatched=assessment['candidate_active'] and not matched)
    return result


def run():
    here = original.HERE
    lock = json.loads((here / 'real_source_lock.json').read_text())
    assert all(original.study.digest(p) == h for p, h in lock['files'].items())
    hashes = dict(lock['files'])
    for path in (Path(__file__).resolve(), here / 'test_reporting_fix.py', here / 'reporting_failure.json'):
        hashes[str(path)] = original.study.digest(path)
    original.write(here / 'reporting_fix_lock.json', {'files': hashes,
        'correction': 'Derived reporting flags only; detector, timing and membership unchanged.'})
    original_assess = original.study.dataset.assess_receiver
    original_write = original.write

    def assess(*args, **kwargs):
        value = annotate(original_assess(*args, **kwargs))
        # Preserve assessment progress even if later summary construction fails.
        with (here / 'reporting_fix_assessments.jsonl').open('a') as stream:
            stream.write(json.dumps({'case_id': args[2].id, 'assessment': value}) + '\n')
        return value

    def write(path, value):
        if path.name == 'real_source_lock.json':
            assert value == lock
            return
        assert path.name == 'results.real.json'
        assert all(original.study.digest(p) == h for p, h in hashes.items())
        value['reporting_adapter_lock_sha256'] = original.study.digest(here / 'reporting_fix_lock.json')
        original_write(here / 'results.reporting_fix.real.json', value)

    original.study.dataset.assess_receiver = assess
    original.write = write
    try:
        original.run()
    finally:
        original.study.dataset.assess_receiver = original_assess
        original.write = original_write


if __name__ == '__main__':
    run()
