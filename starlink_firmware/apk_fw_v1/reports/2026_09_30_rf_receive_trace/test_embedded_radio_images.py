import pytest
from embedded_radio_images import decode_srec


def test_srec_addresses_payload_and_entry():
    records, entries = decode_srec(b'S1061234010203AD\nS9031234B6\n')
    assert records == [(0x1234, b'\x01\x02\x03')]
    assert entries == [0x1234]


def test_srec_rejects_corruption():
    with pytest.raises(AssertionError, match='checksum'):
        decode_srec(b'S1061234010203AE\n')
