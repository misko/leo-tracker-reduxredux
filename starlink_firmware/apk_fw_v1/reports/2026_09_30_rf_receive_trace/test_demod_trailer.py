from demod_trailer import run


def test_demod_trailer_selection_and_byte_preservation():
    result = run()
    assert len(result['cases']) == 232
    assert sum(c['copied_hex'] is not None for c in result['cases']) == 227
    assert all(c['marker'] == 1 for c in result['cases'] if c['copied_hex'] is not None)
