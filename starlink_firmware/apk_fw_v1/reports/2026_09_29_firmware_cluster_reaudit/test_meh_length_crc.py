from meh_length_crc import run


def test_crc_byte_accounting_and_short_extended_boundaries():
    rows = run()["cases"]
    assert len(rows) == 384
    assert all(r["status"] == 27 for r in rows
               if r["flags"] == 0 and r["encoded_length"] == 256)
    assert any(r["status"] == 0 for r in rows
               if r["flags"] == 8 and r["encoded_length"] == 256)
