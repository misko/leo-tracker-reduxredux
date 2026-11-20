"""Fetch only the preselected ZIP members for the Watson spectrum trial."""

import argparse
import json
import re
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

DAYS = ("230302", "230314", "230316", "230323")
HOURS = (6, 18)
URL = "https://zenodo.org/records/8400658/files/{day}.zip?download=1"


def request_range(url, requested):
    request = Request(url, headers={"Range": f"bytes={requested}"})
    with urlopen(request, timeout=35) as response:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if response.status != 206 or not match:
            raise ValueError("archive server did not honor the requested byte range")
        start, stop, total = map(int, match.groups())
        expected = (
            (total - int(requested[1:]), total - 1)
            if requested.startswith("-")
            else tuple(map(int, requested.split("-")))
        )
        if (start, stop) != expected:
            raise ValueError("archive server returned a different byte range")
        data = response.read(stop - start + 2)
    if len(data) != stop - start + 1:
        raise ValueError("archive range is truncated")
    return data, start, total


def archive_entries(data, start, total):
    marker = data.rindex(b"PK\x05\x06")
    sig, disk, central_disk, own, count, size, offset, comment = struct.unpack_from(
        "<4s4H2IH", data, marker
    )
    if disk or central_disk or own != count or offset < start or marker + 22 + comment != len(data):
        raise ValueError("unsupported ZIP directory")
    if start + marker != offset + size or start + len(data) != total:
        raise ValueError("invalid ZIP directory range")
    position = offset - start
    for _ in range(count):
        fields = struct.unpack_from("<4s6H3I5H2I", data, position)
        if fields[0] != b"PK\x01\x02":
            raise ValueError("invalid ZIP directory entry")
        name_size, extra, comment = fields[10:13]
        name = data[position + 46 : position + 46 + name_size].decode("ascii")
        yield name, fields[4], *fields[7:10], fields[-1]
        position += 46 + name_size + extra + comment
    if position != marker:
        raise ValueError("ZIP directory member count is inconsistent")


def fetch_day(day, out):
    url = URL.format(day=day)
    entries = list(archive_entries(*request_range(url, "-80000")))
    wanted = {f"Kerberos_{day}_{hour:02d}00.csv" for hour in HOURS} | {"starlink.tle", "oneweb.tle"}
    selected = {Path(entry[0]).name: entry for entry in entries if Path(entry[0]).name in wanted}
    if selected.keys() != wanted:
        raise ValueError(
            f"missing preselected ZIP members for {day}: {sorted(wanted - selected.keys())}"
        )
    report = []
    for short in sorted(selected):
        name, method, crc, packed, size, offset = selected[short]
        header, _, _ = request_range(url, f"{offset}-{offset + 29}")
        fields = struct.unpack("<4s5H3I2H", header)
        if fields[0] != b"PK\x03\x04" or method != 8 or fields[3] != 8 or size > 35_000_000:
            raise ValueError(f"unsupported ZIP member: {name}")
        first = offset + 30 + fields[-2] + fields[-1]
        last = first + packed - 1
        raw, _, archive_bytes = request_range(url, f"{first}-{last}")
        content = zlib.decompress(raw, -15)
        if len(content) != size or zlib.crc32(content) != crc:
            raise ValueError(f"ZIP member failed integrity validation: {name}")
        (out / f"{day}-{short}").write_bytes(content)
        report.append(
            dict(
                member=name,
                local=f"{day}-{short}",
                url=url,
                range=[first, last],
                archive_bytes=archive_bytes,
                bytes=size,
                crc32=f"{crc:08x}",
                sha256=sha256(content).hexdigest(),
                compressed_sha256=sha256(raw).hexdigest(),
            )
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--day", choices=DAYS, action="append")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    index_path = args.directory / "source.json"
    old = json.loads(index_path.read_bytes())["members"] if index_path.exists() else []
    with ThreadPoolExecutor(max_workers=3) as executor:
        receipts = list(executor.map(lambda day: fetch_day(day, args.directory), args.day or DAYS))
    by_name = {entry["member"]: entry for entry in old}
    by_name.update({entry["member"]: entry for day in receipts for entry in day})
    manifest = dict(
        source="10.5281/zenodo.8400658",
        author="Robert A. Watson",
        license="CC BY 4.0",
        members=[by_name[name] for name in sorted(by_name)],
    )
    index_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
