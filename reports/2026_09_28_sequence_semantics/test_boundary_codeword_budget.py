from boundary_codeword_budget import candidates


def test_budget_matches_do_not_identify_mcs_with_shared_symbol_size():
    records = [dict(identifier=i, symbols_per_codeword=512) for i in (1, 11)]
    found = candidates(4 * 114 + 20 * 512, records)
    assert {r["mcs"] for r in found} == {1, 11}
    assert {(r["header_units"], r["codewords"]) for r in found} == {(4, 20)}
    assert candidates(4 * 114 + 20 * 512 + 1, records) == []
