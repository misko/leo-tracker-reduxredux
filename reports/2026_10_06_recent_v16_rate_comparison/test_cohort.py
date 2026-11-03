"""Pure cohort policy tests: no radio, database or archive access."""
from inventory import select


def test_selection_time_only_and_order_invariant():
    rows=[dict(session_id=f's{i:02}',capture_start_ns=i) for i in range(80)]
    a=select(rows,0,80)
    b=select(list(reversed(rows)),0,80)
    assert a==b
    assert [r['capture_start_ns'] for r in a]==[5,15,25,35,45,55,65,75]
    assert len({r['session_id'] for r in a})==8


def test_insufficient_inventory_not_padded():
    rows=[dict(session_id='only',capture_start_ns=5)]
    assert select(rows,0,80)==rows
    assert select([],0,80)==[]


def test_input_metadata_not_mutated():
    rows=[dict(session_id='only',capture_start_ns=5)]
    result=select(rows,0,80)
    result[0]['label']='new'
    assert 'label' not in rows[0]
