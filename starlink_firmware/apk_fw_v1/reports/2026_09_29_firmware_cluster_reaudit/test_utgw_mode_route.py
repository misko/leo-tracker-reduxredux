from utgw_mode_route import run


def test_composed_route_requires_mode4_and_clear_context_flags():
    rows = run()["cases"]
    assert len(rows) == 96
    stored = [r for r in rows if r["outcome"] == "identity_store"]
    assert len(stored) == 3
    assert all(r["mode"] == 4 and r["alternate"] == r["context_flag"] == 0 for r in stored)
