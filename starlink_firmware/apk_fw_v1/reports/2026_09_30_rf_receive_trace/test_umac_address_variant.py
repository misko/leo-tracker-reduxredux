from umac_address_variant import run


def test_tagged_address_conversion_and_unwritten_fields():
    result = run()
    assert len(result['cases']) == 280
    assert {case['tag'] for case in result['cases']} == set(range(8))
