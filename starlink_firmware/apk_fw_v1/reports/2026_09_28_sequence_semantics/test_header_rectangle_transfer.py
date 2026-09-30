from header_rectangle_transfer import mixed


def test_mixed_constraint_requires_positions_from_both_symbols():
    assert mixed(dict(inputs=[0, 56], output=57), 57)
    assert not mixed(dict(inputs=[57, 58], output=100), 57)
    assert not mixed(dict(inputs=[], output=60), 57)
