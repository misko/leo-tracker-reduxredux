import pytest
from raw_audit import file_offset


def test_elf_translation_rejects_bss_and_ambiguous_mapping():
    segments = [dict(address=0x1000, offset=0x200, filesz=32, memsz=64)]
    assert file_offset(segments, 0x1004, 4) == 0x204
    with pytest.raises(ValueError):
        file_offset(segments, 0x1020, 4)
    with pytest.raises(ValueError):
        file_offset(segments * 2, 0x1004, 4)
