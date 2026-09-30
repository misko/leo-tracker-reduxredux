from descriptor_translation import run


def test_dequeue_translation_zero_wrap_and_invalid_type():
    rows = run()['cases']
    assert len(rows) == 140
    wrapped = [r for r in rows if r['memory_type'] in (1, 2, 3)
               and r['word'] == r['physical_base']-1]
    assert len(wrapped) == 12
    assert all(r['output'] == r['virtual_base']+0xFFFFFFFF for r in wrapped)
    assert all(r['output'] == 0 for r in rows if r['memory_type'] == 4)
