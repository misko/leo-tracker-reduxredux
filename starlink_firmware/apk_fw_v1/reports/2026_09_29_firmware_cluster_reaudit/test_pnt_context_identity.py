from pnt_context_identity import run


def test_pnt_telemetry_id_comes_from_context_with_validity_gate():
    rows = run()["cases"]
    assert len(rows) == 272
    assert sum(r["context_valid"] for r in rows) == 136
