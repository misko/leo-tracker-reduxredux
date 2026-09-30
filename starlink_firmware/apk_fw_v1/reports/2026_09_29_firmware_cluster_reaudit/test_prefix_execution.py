from prefix_execution import CONTEXT, SOURCE, machine, prefix, write_bits


def test_prefix_stops_before_writer_even_after_writer_translation():
    uc = machine(SOURCE.read_bytes())
    assert write_bits(uc, 0xFFFFFFFF, 32, 31, 7) == (31, 1, 7 | (0xFFFFFFFF << 31))
    before = bytes(uc.mem_read(CONTEXT, 36))
    assert prefix(uc, 0, 1, 1, 3, 17, 5) == (16, 4 | 8 | 48 | (17 << 6) | (5 << 12))
    assert bytes(uc.mem_read(CONTEXT, 36)) == before
    assert prefix(uc, 1, 1, 1, 3, 63, 15) == (8, 6)
    assert bytes(uc.mem_read(CONTEXT, 36)) == before
