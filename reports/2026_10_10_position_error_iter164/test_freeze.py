from freeze import execution_batches
import pytest


def members():
    return [dict(label=f'{d}-{i:03d}', dataset=d, binding_status='error')
            for d, n in [('DS16', 63), ('DS17', 51), ('DS18', 34), ('POST18', 45)]
            for i in range(1, n+1)]


def test_balanced_order_preserves_every_member_including_input_failures():
    rows = members()
    batches = execution_batches(rows)
    assert batches[0] == ['DS16-001', 'DS17-001', 'DS18-001', 'POST18-001']
    assert len(batches[0]) == 4
    assert all(len(b) == 16 for b in batches[1:-1])
    assert len(batches[-1]) == 13
    assert sorted(x for b in batches for x in b) == sorted(m['label'] for m in rows)
    assert execution_batches(list(reversed(rows))) == batches


def test_missing_or_duplicate_members_rejected():
    with pytest.raises(ValueError):
        execution_batches(members()[:-1])
    rows = members()
    rows[-1]['label'] = rows[0]['label']
    with pytest.raises(ValueError):
        execution_batches(rows)
