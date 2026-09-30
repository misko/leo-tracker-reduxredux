from grant_configuration_origin import run


def test_grant_diagnostic_names_agree_with_actual_argument_mapping():
    result = run()
    cases = {c["packed_grant"]: c for c in result["cases"]}
    # One resource block, two first-OFDM units yields 47 data symbols.
    assert cases[(1 << 26) | (2 << 13)]["num_data_symbols_u32"] == 47
    for bit in range(31, 40):
        assert cases[1 << bit]["num_data_symbols_u32"] == cases[0]["num_data_symbols_u32"]
