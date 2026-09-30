from descriptor_integrity import run


def test_descriptor_integrity_gate_and_meh_state_exception():
    rows = run()["cases"]
    assert len(rows) == 1024
    selected = [r for r in rows if r["descriptor_gate"] and r["descriptor_flags"] == 16]
    assert all(r["meh_recorded"] == 1 for r in selected)
    assert all(r["status"] == (0 if r["state"] == 2 else 64) for r in selected)
