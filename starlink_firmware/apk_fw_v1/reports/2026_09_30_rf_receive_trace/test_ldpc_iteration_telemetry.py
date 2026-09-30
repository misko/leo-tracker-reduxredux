from ldpc_iteration_telemetry import run


def test_ldpc_iteration_field_has_exact_register_bit_dependency():
    cases = run()['cases']
    assert len(cases) == 70
    assert all(case['register_address'] - case['base'] == 0x8D04 for case in cases)
    assert [c['ldpc_max_iter'] for c in cases[:35]] == [c['ldpc_max_iter'] for c in cases[35:]]
