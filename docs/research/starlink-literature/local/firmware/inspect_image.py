"""Read-only inspection of an untrusted public partition image."""
import hashlib
import json
import lzma
from pathlib import Path
import struct

p = Path(__file__).parent
b = (p / 'linux_with_ecc').read_bytes()
assert b[:7] == b'SXECCv1'
out = bytearray(b[7:222])
i = 0
while b[i + 222] == ord('*'):
    i += 255
    assert b[i + 222] in (ord('*'), ord('$'))
    out.extend(b[i:i + 222])
assert b[i + 222] == ord('$')
footer = b[i + 255:i + 255 + 53]
assert footer[0] == ord('!')
size = int.from_bytes(footer[1:5], 'big')
out = bytes(out[:size])
assert hashlib.md5(out).digest() == footer[5:21], 'Storage checksum mismatch'
(p / 'linux.fit').write_bytes(out)
print('FIT', size, hashlib.sha256(out).hexdigest(), 'MD5 verified')
magic, total, off_struct, off_strings = struct.unpack_from('>4I', out)
assert magic == 0xd00dfeed and total <= len(out)
pos = off_struct
stack = []
entries = []
while True:
    token = struct.unpack_from('>I', out, pos)[0]
    pos += 4
    if token == 1:
        end = out.index(b'\0', pos)
        stack.append(out[pos:end].decode())
        pos = (end + 4) & ~3
    elif token == 2:
        stack.pop()
    elif token == 3:
        length, nameoff = struct.unpack_from('>2I', out, pos)
        pos += 8
        start = off_strings + nameoff
        name = out[start:out.index(b'\0', start)].decode()
        value = out[pos:pos + length]
        if name == 'data':
            label = '_'.join(stack).strip('_')
            (p / (label + '.bin')).write_bytes(value)
            entry = {'node': '/'.join(stack), 'bytes': length, 'sha256': hashlib.sha256(value).hexdigest()}
            try:
                dec = lzma.decompress(value)
                (p / (label + '.uncompressed')).write_bytes(dec)
                entry['uncompressed_bytes'] = len(dec)
                entry['magic'] = dec[:16].hex()
            except lzma.LZMAError:
                pass
            entries.append(entry)
        pos = (pos + length + 3) & ~3
    elif token == 9:
        break
    else:
        assert token == 4
(p / 'fit_inventory.json').write_text(json.dumps(entries, indent=2) + '\n')
print(json.dumps(entries, indent=2))
