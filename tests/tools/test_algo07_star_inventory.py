import json

import pytest
from inventory_algo07_star import inventory


class Source:
    def __init__(self, path):
        self.path = path

    def automatic_status(self, recording):
        return dict(run_id=recording) if recording != 'missing' else None

    def tracking_input_path(self, run):
        return self.path

    def source(self, session, digest):
        return dict(recording_name='available')

    def detail(self, run, *, include_points):
        assert not include_points
        return dict(session_id='session')


def member(recording, mode='fast'):
    return dict(dataset_label=recording, recording_id=recording, session_id='session',
                sample_rate_hz=10_000_000, mode=mode)


def test_missing_members_stay_in_the_denominator(tmp_path):
    path = tmp_path/'tracking.json'
    path.write_text(json.dumps(dict(source=dict(session_id='session',
                                               input_manifest_sha256='digest'))))
    result = inventory(dict(members=[member('available'), member('missing'),
                                     member('adaptive', 'adaptive')]), Source(path))
    assert result['fast_members'] == 2
    assert result['counts'] == dict(available=1, no_native_run=1)
    assert result['excluded_nonfast_members'] == 1
    assert not result['equivalence_verified']


def test_wrong_recording_is_an_explicit_failure(tmp_path):
    path = tmp_path/'tracking.json'
    path.write_text(json.dumps(dict(source=dict(session_id='session',
                                               input_manifest_sha256='digest'))))
    result = inventory(dict(members=[member('wrong')]), Source(path))
    assert result['counts'] == dict(invalid_or_unavailable=1)
    assert 'different recording' in result['members'][0]['reason']


def test_duplicate_recordings_cannot_bias_accounting(tmp_path):
    with pytest.raises(ValueError, match='Duplicate'):
        inventory(dict(members=[member('same'), member('same')]), Source(tmp_path))
