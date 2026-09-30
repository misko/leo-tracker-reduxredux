import struct

import pytest
from go_functions import parse_table


def fixture():
    data = bytearray(160)
    data[:8] = bytes.fromhex('f1ffffff00000408')
    struct.pack_into('<8Q', data, 8, 1, 1, 0x1000, 72, 80, 80, 80, 96)
    data[72:77] = b'main\0'
    struct.pack_into('<III', data, 96, 0, 16, 16)
    struct.pack_into('<Ii', data, 112, 0, 0)
    return data


def test_named_range():
    assert parse_table(fixture(), 0x1000, 0x1010) == [
        dict(address=0x1000, end=0x1010, name='main')]


@pytest.mark.parametrize('offset,value', [(96, 20), (100, 9999), (104, 0), (116, 99)])
def test_reject_corrupt_records(offset, value):
    data = fixture()
    struct.pack_into('<I', data, offset, value)
    with pytest.raises(ValueError):
        parse_table(data, 0x1000, 0x1010)


def test_reject_wrong_format():
    with pytest.raises(ValueError):
        parse_table(b'', 0, 1)
