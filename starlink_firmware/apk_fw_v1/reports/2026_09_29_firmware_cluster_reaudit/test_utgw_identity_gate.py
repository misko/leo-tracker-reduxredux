from utgw_identity_gate import run


def test_context_assignment_distinguishes_nonzero_mismatch_from_zero():
    result = run()
    assert len(result["cases"]) == 36
    assert sum(r["accepted"] for r in result["cases"]) == 16
    assert all(r["context_id"] == 0 and r["context_valid"] == 1
               for r in result["cases"] if r["received"] == 0)
