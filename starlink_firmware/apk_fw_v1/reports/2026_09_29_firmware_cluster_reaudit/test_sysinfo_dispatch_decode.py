from sysinfo_dispatch_decode import run


def test_outer_decoder_alignment_short_length_and_padding_values():
    rows = run()["cases"]
    assert len(rows) == 16
    assert sum(r["status"] == 0 for r in rows) == 8
    assert all(r["status"] == 27 for r in rows if r["length"] == 7)
