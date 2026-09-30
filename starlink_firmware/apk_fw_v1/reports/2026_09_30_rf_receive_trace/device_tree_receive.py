"""Extract radio register declarations from the newly unpacked package DTBs."""
import hashlib
import json
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1] / 'local/unpacked_images'


def nodes(data):
    magic, total, offset, strings, _, _, _, _, stringsize, structuresize = struct.unpack_from(
        '>10I', data)
    assert magic == 0xD00DFEED and total <= len(data)
    names = data[strings:strings + stringsize]
    end = offset + structuresize
    stack, result = [], {}
    while offset < end:
        token = int.from_bytes(data[offset:offset + 4], 'big')
        offset += 4
        if token == 1:
            stop = data.index(b'\0', offset)
            stack.append(data[offset:stop].decode())
            offset = (stop + 4) & ~3
            result['/' + '/'.join(filter(None, stack))] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', data, offset)
            offset += 8
            assert offset + size <= end
            name = names[nameoff:names.index(b'\0', nameoff)].decode()
            result['/' + '/'.join(filter(None, stack))][name] = data[offset:offset + size]
            offset = (offset + size + 3) & ~3
        elif token == 9:
            break
        else:
            assert token == 4
    return result


def words(data):
    assert len(data) % 4 == 0
    return [int.from_bytes(data[i:i + 4], 'big') for i in range(0, len(data), 4)]


def run():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    results = []
    targets = {'l2_ut_rx_push', 'l2_ut_rx_pull', 'l2_ut_rx_common',
               'syscfg_adc', 'modem_adc', 'modem_rx', 'modem_rx_ipp'}
    for row in manifest['files']:
        if row.get('format') != 'FDT/FIT' or row['bytes'] > 100000:
            continue
        data = (ROOT / row['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        tree = nodes(data)
        selected = []
        for path, props in tree.items():
            if path.rsplit('/', 1)[-1] not in targets:
                continue
            parent = tree[path.rsplit('/', 1)[0]]
            selected.append(dict(path=path, reg=words(props['reg']),
                                 ranges=words(parent.get('ranges', b'')),
                                 parent_status=parent.get('status', b'').rstrip(b'\0').decode(),
                                 parent_compatible=parent.get('compatible', b'').split(b'\0')[0]
                                 .decode()))
        provenance = ('existing separate FIT' if row['path'].startswith('existing_')
                      else 'current unpacked SXV')
        results.append(dict(source=row['path'], sha256=row['sha256'], mappings=selected,
                            provenance=provenance))
    current = [r for r in results if r['provenance'] == 'current unpacked SXV']
    assert current
    for item in current:
        if not item['source'].endswith('/utdev3.bin'):
            continue
        regs = {r['path'].rsplit('/', 1)[-1]: r['reg'] for r in item['mappings']}
        assert regs['l2_ut_rx_push'] == [0xC204000, 0x2000]
        assert regs['syscfg_adc'] == [0xC400000, 0x100000]
        assert regs['modem_adc'] == [0xC500000, 0x1000]
    return dict(trees=results, current_count=len(current),
                limitation='Device-tree declarations, not observed hardware execution. '
                'Register values are raw big-endian cells; parent ranges retained. '
                'Separate existing FIT is not assumed to belong to the current package.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/device-tree-receive.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['current_count'], 'current-package device trees checked;',
          len(result['trees']), 'total trees inventoried.')
