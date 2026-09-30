"""Inventory XP70 S-record images from the existing runtime archive, read-only."""
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
FIRMWARE = BASE.parents[1] / 'local/firmware'


def decode_srec(data):
    records = []
    entries = []
    for line in data.decode('ascii').splitlines():
        if not line.strip():
            continue
        assert line[0] == 'S'
        kind = int(line[1])
        raw = bytes.fromhex(line[2:])
        assert len(raw) == raw[0] + 1, 'record length'
        assert sum(raw) & 255 == 255, 'record checksum'
        width = {0: 2, 1: 2, 2: 3, 3: 4, 5: 2, 6: 3, 7: 4, 8: 3, 9: 2}[kind]
        assert len(raw) >= width + 2
        address = int.from_bytes(raw[1:1 + width], 'big')
        payload = raw[1 + width:-1]
        if kind in (1, 2, 3):
            records.append((address, payload))
        elif kind in (7, 8, 9):
            entries.append(address)
    records.sort()
    for (address, payload), (next_address, _) in zip(records, records[1:], strict=False):
        assert address + len(payload) <= next_address, 'overlapping records'
    return records, entries


def run():
    archive = FIRMWARE / 'sw_update_catson-runtime.sxv'
    raw = archive.read_bytes()
    rom = raw[raw.index(b'-rom1fs-'):]
    inventory = json.loads((FIRMWARE / 'sw_update_catson-runtime-inventory.json').read_text())
    row = next(r for r in inventory if r['path'] == '/runtime.tar.zst')
    compressed = rom[row['offset']:row['offset'] + row['size']]
    assert hashlib.sha256(compressed).hexdigest() == row['sha256']
    tar_bytes = subprocess.run(['zstd', '-d', '-c'], input=compressed,
                               capture_output=True, check=True).stdout
    images = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        setup = tar.extractfile('./bin/setup_ut.sh').read()
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith('.srec'):
                continue
            data = tar.extractfile(member).read()
            records, entries = decode_srec(data)
            # Join only contiguous records when looking for text.
            spans = []
            for address, payload in records:
                if spans and spans[-1][0] + len(spans[-1][1]) == address:
                    spans[-1][1].extend(payload)
                else:
                    spans.append((address, bytearray(payload)))
            hints = []
            for address, payload in spans:
                for match in re.finditer(rb'[ -~]{8,}', payload):
                    if re.search(rb'beam|modem|demod|fft|fec|ldpc|pilot|shiraz|xp70|version',
                                 match.group(), re.I):
                        hints.append(dict(address=hex(address + match.start()),
                                          text=match.group().decode()))
            images.append(dict(path=member.name, sha256=hashlib.sha256(data).hexdigest(),
                               records=len(records), data_bytes=sum(len(p) for _, p in records),
                               entry_addresses=[hex(e) for e in entries], hints=hints,
                               spans=[dict(address=hex(a), bytes=len(p)) for a, p in spans]))
    return dict(archive_sha256=hashlib.sha256(raw).hexdigest(), images=images,
                setup_sha256=hashlib.sha256(setup).hexdigest(),
                setup_evidence=[dict(line=i + 1, text=line) for i, line in
                                enumerate(setup.decode().splitlines())
                                if re.search('xp70|Shiraz.*DBF|link_mac_phy|MODEM_TYPE', line)],
                limitation='S-record integrity and startup references, not instruction '
                'disassembly or proof of IQ-to-message decoding. No supplied code executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/embedded-radio-images.json').write_text(json.dumps(result, indent=2) + '\n')
    for item in result['images']:
        print(item['path'], item['data_bytes'], 'bytes;', len(item['hints']), 'text hints')
