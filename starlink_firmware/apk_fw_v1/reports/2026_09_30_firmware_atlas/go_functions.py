"""Recover named ranges from this corpus's Go 1.20-format pclntab, not types.

Format reference: https://go.dev/src/debug/gosym/pclntab.go
Only little-endian 64-bit, four-byte instruction quantum is supported here.
"""
import struct


def parse_table(data, text_start, text_end):
    if len(data) < 72 or data[:8] != bytes.fromhex('f1ffffff00000408'):
        raise ValueError('unsupported or truncated Go pclntab')
    count, _, base, names, cu, files, pcs, table = struct.unpack_from('<8Q', data, 8)
    if base != text_start or not 72 <= names <= cu <= files <= pcs <= table < len(data):
        raise ValueError('invalid table offsets or unrelocated text base')
    if count > (len(data) - table - 4) // 8:
        raise ValueError('truncated function table')
    rows = []
    for index in range(count):
        entry, record = struct.unpack_from('<II', data, table + 8 * index)
        end, = struct.unpack_from('<I', data, table + 8 * (index + 1))
        if not text_start <= base + entry < base + end <= text_end:
            raise ValueError('invalid function extent')
        location = table + record
        if location < table + count * 8 + 4 or location + 8 > len(data):
            raise ValueError('invalid function record offset')
        check_entry, name_offset = struct.unpack_from('<Ii', data, location)
        start = names + name_offset
        if check_entry != entry or not names <= start < cu:
            raise ValueError('invalid function name or entry')
        stop = data.find(b'\0', start, cu)
        if stop < 0:
            raise ValueError('unterminated function name')
        rows.append(dict(address=base + entry, end=base + end,
                         name=data[start:stop].decode('utf-8', errors='strict')))
    return rows


def recover_go_functions(elf):
    section = elf.get_section_by_name('.gopclntab')
    if section is None:
        return []
    text = elf.get_section_by_name('.text')
    if text is None:
        raise ValueError('Go text section missing')
    return parse_table(section.data(), int(text['sh_addr']),
                       int(text['sh_addr'] + text['sh_size']))
