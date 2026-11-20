import concurrent.futures
import pathlib
import struct
import urllib.request
import zlib


URL = "https://zenodo.org/api/records/8400658/files/230311.zip/content"
CENTRAL_OFFSET = 1050817010
CENTRAL_END = 1050841170
DIRECTORY = pathlib.Path(__file__).parent


def get_range(first, last):
    request = urllib.request.Request(URL, headers={"Range": f"bytes={first}-{last}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        expected = f"bytes {first}-{last}/1050841193"
        if response.status != 206 or response.headers.get("Content-Range") != expected:
            raise ValueError(f"Invalid byte range response: {response.status}")
        content = response.read(last - first + 1)
    if len(content) != last - first + 1:
        raise ValueError(f"Truncated byte range: {first}-{last}")
    return content


def entries():
    data = (DIRECTORY / "monitor-dir.bin").read_bytes()
    offset = 0
    while offset < len(data):
        if data[offset:offset + 4] != b"PK\x01\x02":
            raise ValueError(f"Unexpected directory record at {offset}")
        fields = struct.unpack_from("<4s6H3I5H2I", data, offset)
        name_length, extra_length, comment_length = fields[10:13]
        name = data[offset + 46:offset + 46 + name_length].decode("ascii")
        yield name, fields[4], fields[7], fields[8], fields[9], fields[-1]
        offset += 46 + name_length + extra_length + comment_length


def get_entry(entry):
    name, method, crc, compressed_size, size, offset = entry
    header = get_range(offset, offset + 29)
    fields = struct.unpack("<4s5H3I2H", header)
    if fields[0] != b"PK\x03\x04" or method != 8 or fields[3] != 8:
        raise ValueError(f"Unsupported ZIP member: {name}")
    start = offset + 30 + fields[-2] + fields[-1]
    payload = zlib.decompress(get_range(start, start + compressed_size - 1), -15)
    if len(payload) != size or zlib.crc32(payload) != crc:
        raise ValueError(f"Member integrity check failed: {name}")
    (DIRECTORY / pathlib.Path(name).name).write_bytes(payload)
    print(name, start, compressed_size, size, f"{crc:08x}")


if __name__ == "__main__":
    wanted = {"starlink.tle", "oneweb.tle"}
    wanted.update(f"Kerberos_230311_{hour:02d}00.csv" for hour in (0, 3, 4, 5))
    selected = [entry for entry in entries() if pathlib.Path(entry[0]).name in wanted]
    if {pathlib.Path(entry[0]).name for entry in selected} != wanted:
        raise ValueError("Requested members are missing")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(get_entry, selected))
