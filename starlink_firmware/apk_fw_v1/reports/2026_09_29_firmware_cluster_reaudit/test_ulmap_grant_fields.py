from ulmap_grant_fields import run


def test_ulmap_names_distinguish_index_mcs_offset_and_count():
    result = run()
    assert len(result["cases"]) == 174
    cases = {r["grant"]: r["fields"] for r in result["cases"] if r["element"] == 0}
    assert cases[1 << 16]["index"] == 1
    assert cases[1 << 48]["mcs"] == 1
    assert cases[1 << 47] == cases[0]  # Unreported packed bit31.
