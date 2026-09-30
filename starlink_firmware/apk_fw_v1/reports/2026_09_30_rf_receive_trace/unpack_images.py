"""Read-only recursive unpacking of existing firmware; output stays under local/."""
import gzip
import hashlib
import io
import json
import re
import struct
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from embedded_radio_images import FIRMWARE, decode_srec

OUT = FIRMWARE.parent / 'unpacked_images'


def safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f'unsafe member: {name}')
    return Path(*p.parts)


def spans(data):
    records, entries = decode_srec(data)
    result = []
    for address, payload in records:
        if result and result[-1][0] + len(result[-1][1]) == address:
            result[-1][1].extend(payload)
        else:
            result.append((address, bytearray(payload)))
    return result, entries


def rom_members(raw):
    start = raw.index(b'-rom1fs-')
    data = raw[start:]
    total = int.from_bytes(data[8:12], 'big')
    assert total <= len(data)
    seen = set()

    def walk(offset, parent):
        while offset:
            assert offset not in seen and offset + 16 <= total
            seen.add(offset)
            nxt, spec, size, _ = struct.unpack_from('>4I', data, offset)
            end = data.index(b'\0', offset + 16)
            name = data[offset + 16:end].decode()
            body = (end + 16) & ~15
            assert body + size <= total
            if name not in ('.', '..'):
                path = str(PurePosixPath(parent) / name)
                yield path, nxt & 7, data[body:body + size], spec
                if nxt & 7 == 1:
                    yield from walk(spec, path)
            offset = nxt & ~15

    yield from walk((data.index(b'\0', 16) + 16) & ~15, '')


def fit_members(data):
    _, total, off, strings, _, _, _, _, strings_size, structure_size = struct.unpack_from(
        '>10I', data)
    assert total <= len(data)
    names = data[strings:strings + strings_size]
    end = off + structure_size
    nodes = []
    while off < end:
        token = int.from_bytes(data[off:off + 4], 'big')
        off += 4
        if token == 1:
            stop = data.index(b'\0', off)
            nodes.append(data[off:stop].decode())
            off = (stop + 4) & ~3
        elif token == 2:
            nodes.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', data, off)
            off += 8
            name = names[nameoff:names.index(b'\0', nameoff)]
            assert off + size <= end
            if name == b'data':
                yield '/'.join(n for n in nodes if n) + '.bin', data[off:off + size]
            off = (off + size + 3) & ~3
        elif token == 9:
            break
        else:
            assert token == 4


def cpio_members(data):
    offset = 0
    while data[offset:offset + 6] in (b'070701', b'070702'):
        header = data[offset:offset + 110]
        values = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        mode, size, namesize = values[1], values[6], values[11]
        name = data[offset + 110:offset + 110 + namesize - 1].decode()
        body = (offset + 110 + namesize + 3) & ~3
        assert body + size <= len(data)
        if name == 'TRAILER!!!':
            return
        yield name, mode, data[body:body + size]
        offset = (body + size + 3) & ~3


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, decoded, seen = [], [], {}

    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == data, f'refusing to replace differing output {path}'
        else:
            path.write_bytes(data)

    def visit(data, path, depth=0):
        assert depth <= 12
        save(path, data)
        digest = hashlib.sha256(data).hexdigest()
        row = dict(path=str(path.relative_to(OUT)), bytes=len(data), sha256=digest)
        manifest.append(row)
        if digest in seen:
            row['same_content_as'] = seen[digest]
            return
        seen[digest] = row['path']
        target = path.with_name(path.name + '.unpacked')

        def child(name, body):
            visit(body, target / safe_name(name), depth + 1)

        if path.suffix == '.srec':
            target = OUT / 'xp70' / path.stem
            save(target / path.name, data)
            regions, entries = spans(data)
            details = dict(source=row['path'], sha256=digest,
                           entries=[hex(e) for e in entries], spans=[], strings=[])
            for address, body in regions:
                name = f'region_{address:08x}_{address + len(body):08x}.bin'
                save(target / name, bytes(body))
                candidates = []
                for magic, label in ((b'\x7fELF', 'ELF'), (b'-rom1fs-', 'ROMFS'),
                                     (b'hsqs', 'SquashFS'), (b'PK\x03\x04', 'ZIP'),
                                     (b'070701', 'CPIO'), (b'\x1f\x8b\x08', 'gzip'),
                                     (b'\x28\xb5\x2f\xfd', 'zstd')):
                    for m in re.finditer(re.escape(magic), body):
                        candidates.append(dict(address=hex(address + m.start()), type=label))
                details['spans'].append(dict(path=name, address=hex(address), bytes=len(body),
                                             sha256=hashlib.sha256(body).hexdigest(),
                                             signature_candidates=candidates))
                for match in re.finditer(rb'[ -~]{6,}', body):
                    details['strings'].append(dict(address=hex(address + match.start()),
                                                   text=match.group().decode()))
            save(target / 'memory_map.json', (json.dumps(details, indent=2) + '\n').encode())
            save(target / 'strings.tsv', ''.join(
                f"{r['address']}\t{r['text']}\n" for r in details['strings']).encode())
            decoded.append(details)
            row['format'] = 'S-record memory image'
        elif data.startswith(b'sxverity') or data.startswith(b'-rom1fs-'):
            row['format'] = 'SXV/ROMFS'
            for name, kind, body, spec in rom_members(data):
                if kind == 2:
                    child(name, body)
                else:
                    manifest.append(dict(parent=row['path'], member=name, romfs_kind=kind,
                                         spec=spec, link=body.decode(errors='replace') if kind == 3
                                         else None))
        elif data.startswith(b'\x28\xb5\x2f\xfd'):
            row['format'] = 'zstd'
            result = subprocess.run(['zstd', '-d', '-c'], input=data, capture_output=True)
            if result.returncode:
                row['decompression_warning'] = result.stderr.decode(errors='replace')
            if result.stdout:
                name = path.stem if path.suffix == '.zst' else 'decompressed.bin'
                if result.returncode:
                    name = 'unverified_prefix_' + name
                child(name, result.stdout)
        elif data.startswith(b'\x1f\x8b\x08'):
            row['format'] = 'gzip'
            child('decompressed.bin', gzip.decompress(data))
        elif data[:6] in (b'070701', b'070702'):
            row['format'] = 'CPIO'
            for name, mode, body in cpio_members(data):
                if mode & 0o170000 == 0o100000:
                    child(name, body)
                else:
                    manifest.append(dict(parent=row['path'], member=name, mode=oct(mode),
                                         link=body.decode(errors='replace') if
                                         mode & 0o170000 == 0o120000 else None))
        elif data.startswith(b'\xd0\x0d\xfe\xed'):
            row['format'] = 'FDT/FIT'
            for name, body in fit_members(data):
                child(name, body)
        elif len(data) > 262 and data[257:262] == b'ustar':
            row['format'] = 'tar'
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                for member in tar:
                    safe_name(member.name)
                    if member.isfile():
                        child(member.name, tar.extractfile(member).read())
                    else:
                        manifest.append(dict(parent=row['path'], member=member.name,
                                             tar_type=repr(member.type), link=member.linkname))
        elif data.startswith(b'\x01\x00\x64\xaa'):
            row['format'] = 'FIP'
            offset = 16
            while data[offset:offset + 16] != bytes(16):
                uuid = data[offset:offset + 16].hex()
                start, size, flags = struct.unpack_from('<QQQ', data, offset + 16)
                assert size > 0 and start + size <= len(data)
                child(uuid + '.bin', data[start:start + size])
                offset += 40
        else:
            row['format'] = 'leaf (not a recognized container)'

    for source in sorted(FIRMWARE.glob('*.sxv')):
        visit(source.read_bytes(), OUT / source.name)
    # Previously recovered FIT has had the outer ECC representation removed.
    source = FIRMWARE / 'linux.fit'
    if source.exists():
        visit(source.read_bytes(), OUT / 'existing_linux.fit')
    result = dict(files=manifest, xp70=decoded,
                  scope='All existing top-level SXV packages and existing recovered linux.fit. '
                  'Links and device nodes inventoried, not materialized. Exact-content containers '
                  'expanded once. Unknown leaf formats retained unchanged. No firmware executed.')
    (OUT / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(output=str(OUT), entries=len(manifest),
                          xp70_images=len(decoded), files=sum('sha256' in r for r in manifest))))
    return result


if __name__ == '__main__':
    run()
