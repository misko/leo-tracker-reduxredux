from firmware_seed_search import SEED, packed_matches


def test_every_bit_alignment_and_boundary_truncation():
    for offset in range(8):
        stream = "1" * offset + SEED
        stream += "0" * ((-len(stream)) % 8)
        encoded = int(stream, 2).to_bytes(len(stream) // 8, "big")
        assert (0, offset) in list(packed_matches(encoded, SEED))
        assert (0, offset) not in list(packed_matches(encoded[:-1], SEED))


def test_repeated_occurrences_and_mutation():
    data = int(SEED + "0000", 2).to_bytes(8, "big")
    assert list(packed_matches(data + data, SEED)) == [(0, 0), (8, 0)]
    damaged = bytes([data[0] ^ 0x80]) + data[1:]
    assert not list(packed_matches(damaged, SEED))
