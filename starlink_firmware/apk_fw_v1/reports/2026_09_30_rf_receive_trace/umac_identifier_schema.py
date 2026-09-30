"""Extract the embedded LocalIdentifier descriptor and cross-check object RTTI."""
import hashlib
import io
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile
from umac_identity import SOURCE

BASE = Path(__file__).resolve().parent


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('oversized varint')


def fields(data):
    pos = 0
    result = {}
    while pos < len(data):
        key, pos = varint(data, pos)
        number, wire = key >> 3, key & 7
        assert number > 0
        if wire == 0:
            value, pos = varint(data, pos)
        elif wire == 2:
            size, pos = varint(data, pos)
            assert pos + size <= len(data)
            value, pos = data[pos:pos + size], pos + size
        else:
            raise ValueError(f'unexpected descriptor wire type {wire}')
        result.setdefault(number, []).append(value)
    return result


def descriptor(data):
    parsed = fields(data)
    members = []
    for raw in parsed.get(2, []):
        f = fields(raw)
        members.append(dict(name=f[1][0].decode(), number=f[3][0], type=f[5][0],
                            type_name=f.get(6, [b''])[0].decode(),
                            oneof=f.get(9, [None])[0]))
    return dict(name=parsed[1][0].decode(), fields=members,
                nested=[descriptor(raw) for raw in parsed.get(3, [])])


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == expected
    # FileDescriptorProto's length-delimited message_type entry.
    start = 0x750171
    assert data[start] == 0x22
    length, body = varint(data, start + 1)
    assert length == 615 and body == 0x750174
    result = descriptor(data[body:body + length])
    assert result['name'] == 'LocalIdentifier'
    assert {f['number']: f['name'] for f in result['fields']} == {
        1: 'satellite_id', 2: 'gateway_id', 3: 'ut_sid', 4: 'ut_ine_id',
        5: 'ut_network_id', 6: 'gw_id',
    }
    assert all(f['oneof'] == 0 for f in result['fields'])
    request_length, request_body = varint(data, 0x750450)
    assert data[0x75044F] == 0x22 and request_length == 1782
    request = descriptor(data[request_body:request_body + request_length])
    assert request['name'] == 'MacUpRequest'
    local_id = next(f for f in request['fields'] if f['number'] == 5)
    assert local_id['name'] == 'local_id'
    assert local_id['type_name'].endswith('.CMInterface2.LocalIdentifier')
    elf = ELFFile(io.BytesIO(data))

    def read(address, size):
        for segment in elf.iter_segments():
            offset = address - segment['p_vaddr']
            if segment['p_type'] == 'PT_LOAD' and 0 <= offset <= segment['p_filesz'] - size:
                return segment.data()[offset:offset + size]
        raise ValueError(hex(address))

    types = []
    for obj, vtable, suffix in ((0x8C1FE0, 0x89D028, '15LocalIdentifierE'),
                                (0x8C2000, 0x89CF80, '27LocalIdentifier_UtNetworkIdE'),
                                (0x8C2048, 0x89CE30, '25LocalIdentifier_GatewayIDE'),
                                (0x8C1EC8, 0x89D178, '12MacUpRequestE')):
        assert struct.unpack('<Q', read(obj, 8))[0] == vtable
        info = struct.unpack('<Q', read(vtable - 8, 8))[0]
        name_address = struct.unpack('<Q', read(info + 8, 8))[0]
        name = read(name_address, 180).split(b'\0')[0].decode()
        assert name == 'N6SpaceX3API10Satellites3MAC12CMInterface2' + suffix
        types.append(dict(object=hex(obj), vtable=hex(vtable), rtti=name))
    assert struct.unpack('<Q', read(0x89D178 + 0x50, 8))[0] == 0x195000
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    relocations = {r['r_offset']: r['r_addend'] for s in elf.iter_sections()
                   if s.name.startswith('.rela') for r in s.iter_relocations()}
    rpc_types = []
    for got in (0x8B9A90, 0x8BA090):
        info = relocations[got]
        name_address = struct.unpack('<Q', read(info + 8, 8))[0]
        name = read(name_address, 240).split(b'\0')[0].decode()
        rpc_types.append(dict(got=hex(got), typeinfo=hex(info), rtti=name))
    assert rpc_types[0]['rtti'] == '24GenericMacCtrlRpcContext'
    assert rpc_types[1]['rtti'] == (
        '17MacCtrlRpcContextIN6SpaceX3API10Satellites3MAC12CMInterface2'
        '12MacUpRequestENS4_13MacUpResponseEE')
    plt = list(cs.disasm(read(0xA5BE0, 12), 0xA5BE0))
    import_got = (int(plt[0].op_str.split('#')[1], 16)
                  + int(plt[1].op_str.split('#')[1].rstrip(']'), 16))
    rela = elf.get_section_by_name('.rela.plt')
    symbols = elf.get_section(rela['sh_link'])
    assert next(symbols.get_symbol(r['r_info_sym']).name for r in rela.iter_relocations()
                if r['r_offset'] == import_got) == '__dynamic_cast'
    windows = {}
    for start, size in ((0x195720, 0x2C), (0x108B20, 0x38), (0x102188, 0x10),
                        (0x10A1E0, 0x30), (0x10A510, 0x30), (0x19C520, 0x20)):
        windows[hex(start)] = [f'{i.address:x}: {i.mnemonic} {i.op_str}'
                               for i in cs.disasm(read(start, size), start)]
    assert windows['0x195720'][0] == '195720: cmp w1, #0x2a'
    assert '195728: ldr x1, [x21, #0x60]' in windows['0x195720']
    assert '195744: str x0, [x21, #0x60]' in windows['0x195720']
    assert '102188: ldr x0, [x24, #0x60]' in windows['0x102188']
    return dict(descriptor=result, enclosing_request=request, types=types, rpc_types=rpc_types,
                instruction_windows=windows, descriptor_file_offset=hex(body),
                binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Embedded API schema and RTTI, not an RF header layout. '
                'Actual converter execution is covered by umac_address_variant.py.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-identifier-schema.json').write_text(json.dumps(result, indent=2) + '\n')
    print('LocalIdentifier/MacUpRequest schemas, four RTTI objects and parser offset verified.')
