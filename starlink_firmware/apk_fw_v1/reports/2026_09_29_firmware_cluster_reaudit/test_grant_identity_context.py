from grant_identity_context import run


def test_grant_satellite_gate_uses_context_and_zero_bypass():
    result = run()
    assert len(result["cases"]) == 288
    assert sum(c["accepted"] for c in result["cases"]) == 128
