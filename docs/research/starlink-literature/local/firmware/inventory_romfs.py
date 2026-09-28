"""Inventory ROMFS without mounting or executing the supplied image."""
from pathlib import Path
import hashlib
import json
import struct

p = Path(__file__).parent
for source in p.glob('*.sxv'):
    raw = source.read_bytes()
    start = raw.index(b'-rom1fs-')
    b = raw[start:]
    total = int.from_bytes(b[8:12], 'big')
    assert total <= len(b)
    root = (b.index(b'\0', 16) + 16) & ~15
    rows = []
    seen = set()
    def walk(offset, parent):
        while offset:
            assert offset not in seen and offset+16 <= total
            seen.add(offset)
            nxt, spec, size, checksum = struct.unpack_from('>4I', b, offset)
            end = b.index(b'\0', offset+16)
            name = b[offset+16:end].decode()
            dataoff = (end+16) & ~15
            path = parent + '/' + name
            kind = nxt & 7
            assert dataoff+size <= total
            data = b[dataoff:dataoff+size]
            rows.append(dict(path=path, kind=kind, size=size, offset=dataoff,
                             magic=data[:16].hex(), sha256=hashlib.sha256(data).hexdigest()))
            if kind == 1 and name not in ('.','..'):
                walk(spec, path)
            if kind == 2 and ('version' in name or size > 1000000):
                print(source.name, path, size, repr(data[:100]))
            offset = nxt & ~15
    walk(root, '')
    (p/(source.stem+'-inventory.json')).write_text(json.dumps(rows,indent=2)+'\n')
    print(source.name, 'entries',len(rows), 'size', total)
    print('large',[(r['path'],r['size'],r['magic']) for r in rows if r['size']>1000000])
