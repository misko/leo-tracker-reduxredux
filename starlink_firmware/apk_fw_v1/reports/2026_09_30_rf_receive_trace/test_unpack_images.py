import pytest
from unpack_images import safe_name, spans


def test_paths_reject_escape():
    for path in ('/etc/passwd', '../escape', 'a/../../escape'):
        with pytest.raises(ValueError):
            safe_name(path)
    assert str(safe_name('./bin/file')) == 'bin/file'


def test_sparse_memory_does_not_invent_padding():
    regions, entries = spans(b'S1061234010203AD\nS9031234B6\n')
    assert regions == [(0x1234, bytearray(b'\x01\x02\x03'))]
    assert entries == [0x1234]
