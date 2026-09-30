"""Read only the archive directory and compare small local files by ZIP CRC/size."""

import hashlib
import json
import struct
import urllib.request
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
URL = "https://zenodo.org/api/records/21404931"


def main():
    with urllib.request.urlopen(URL, timeout=20) as response:
        record = json.load(response)
    parts = sorted(
        (f for f in record["files"] if ".zip.part" in f["key"]), key=lambda f: f["key"]
    )
    last = parts[-1]
    length = 131072
    start = last["size"] - length
    request = urllib.request.Request(
        last["links"]["self"], headers={"Range": f"bytes={start}-{last['size'] - 1}"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 206, "Range rejected; do not download full archive"
        expected_range = f"bytes {start}-{last['size'] - 1}/{last['size']}"
        assert response.headers["Content-Range"] == expected_range
        tail = response.read(length + 1)
    assert len(tail) == length
    base_offset = sum(p["size"] for p in parts[:-1]) + start
    end = tail.rfind(b"PK\x05\x06")
    assert end >= 0
    _, disk, cd_disk, n_disk, count, cd_size, cd_offset, comment = struct.unpack_from(
        "<4s4H2IH", tail, end
    )
    assert disk == cd_disk == 0 and n_disk == count
    assert end + 22 + comment == len(tail)
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or count == 0xFFFF:
        locator = end - 20
        sig, _, absolute, _ = struct.unpack_from("<4sIQI", tail, locator)
        assert sig == b"PK\x06\x07"
        position = absolute - base_offset
        assert position >= 0
        fields = struct.unpack_from("<4sQ2H2I4Q", tail, position)
        assert fields[0] == b"PK\x06\x06"
        count, cd_size, cd_offset = fields[7:10]
    position = cd_offset - base_offset
    assert 0 <= position < end
    stop = position + cd_size
    assert stop <= end
    root = BASE.parents[3] / "docs/research/starlink-literature/local/data/ut-pilots/supplement"
    rows = []
    for _ in range(count):
        assert tail[position : position + 4] == b"PK\x01\x02"
        crc, compressed, size = struct.unpack_from("<III", tail, position + 16)
        n, extra, note = struct.unpack_from("<HHH", tail, position + 28)
        name = tail[position + 46 : position + 46 + n].decode()
        position += 46 + n + extra + note
        row = dict(name=name, crc32=f"{crc:08x}", size32=size, compressed_size32=compressed)
        if name.startswith("starlink-template-supp/") and not name.endswith("/"):
            relative = Path(name).relative_to("starlink-template-supp")
            assert ".." not in relative.parts
            local = root / relative
            if local.is_file() and local.stat().st_size < 10000000:
                data = local.read_bytes()
                row["local_crc_and_size_match"] = len(data) == size and zlib.crc32(data) == crc
        rows.append(row)
    assert position == stop
    result = dict(
        source=URL, archive_bytes=sum(p["size"] for p in parts),
        bytes_read=length, tail_sha256=hashlib.sha256(tail).hexdigest(), rows=rows,
        limitation="Directory only; ZIP CRC and length comparison is not cryptographic "
        "authentication. Large data member not downloaded or compared.",
    )
    (BASE / "local/zenodo_inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(
        entries=count, compared=sum("local_crc_and_size_match" in r for r in rows),
        mismatches=[r["name"] for r in rows if r.get("local_crc_and_size_match") is False],
    )))


if __name__ == "__main__":
    main()
