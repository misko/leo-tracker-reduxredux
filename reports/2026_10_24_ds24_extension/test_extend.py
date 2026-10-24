import pytest
from extend import adaptive_rates, merge_members


def member(identity, stamp, label=None):
    row = dict(raw_recording=dict(identity_sha256=identity), captured_utc_ns=stamp,
               recording_id=identity)
    if label:
        row['dataset_label'] = label
    return row


def test_stable_labels_even_when_new_format_has_earlier_capture():
    parent = [member('old', 10, 'DS24-0019')]
    rows = merge_members(parent, [member('new', 5), member('old', 10)])
    assert [(r['recording_id'], r['dataset_label']) for r in rows] == [
        ('old', 'DS24-0019'), ('new', 'DS24-0020')]
    assert parent[0]['dataset_label'] == 'DS24-0019'


def test_missing_or_changed_previous_identity_fails():
    parent = [member('old', 10, 'DS24-0001')]
    with pytest.raises(ValueError, match='missing'):
        merge_members(parent, [])
    with pytest.raises(ValueError, match='time changed'):
        merge_members(parent, [member('old', 11)])


def test_actual_rate_excludes_restoration_settings_and_detects_disagreement():
    d = dict(receipt=dict(plan=dict(geometry=dict(sample_rate_hz=10000000)),
                          restoration=dict(original_settings=dict(sample_rate_hz=30720000))),
             timing=dict(sample_rate_hz=10000000))
    assert adaptive_rates({'manifest': d}) == [10000000]
    d['timing']['sample_rate_hz'] = 2500000
    assert adaptive_rates(d) == [2500000, 10000000]
