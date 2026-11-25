"""Run passive-cache admission against three disposable 1 MiB files."""

from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from reports.ALGO08.v3.directed_stage_cache_reader import (
    BLOCK, CacheReader, CacheSourceUnavailable, Extent, resident_pages,
)


def exercise(directory, policy):
    member = directory / "member.bin"
    body = bytes(range(256)) * (BLOCK // 256)
    digest = sha256(body).hexdigest()
    with member.open("x+b") as stream:
        stream.write(body)
        stream.flush()
        fd = stream.fileno()
        os.fsync(fd)
        if policy in {"cold", "mixed"}:
            os.posix_fadvise(fd, 0, BLOCK, os.POSIX_FADV_DONTNEED)
        if policy == "mixed":
            # Rewriting part of the disposable file avoids a partial eviction
            # request that might leave its original large folio resident.
            half = BLOCK // 2
            if os.pwrite(fd, body[:half], 0) != half:
                raise OSError("The mixed fixture could not establish the warm half")
            os.fsync(fd)
        before = resident_pages(fd, BLOCK)
        reader = CacheReader(directory, {member.name: Extent(BLOCK, "sha256:" + digest, "encoded")})
        exact = False
        try:
            with reader:
                exact = sha256(reader.read(member, BLOCK)).hexdigest() == digest
                reader.verify_complete()
        except CacheSourceUnavailable:
            pass
        after = resident_pages(fd, BLOCK)
    receipt = reader.receipt()
    present, total = before
    expected_residency = {
        "cold": present == 0,
        "mixed": 0 < present < total,
        "warm": present == total,
    }
    if policy == "warm":
        expected_result = exact and receipt["nowait_requests"] == 1 and receipt["bytes"] == BLOCK
    else:
        expected_result = (not exact and not receipt["nowait_requests"] and
                           receipt["refused_read"]["condition"] == "initial_cache_census")
    passed = (expected_residency[policy] and expected_result and before == after and
              not receipt["read_input_blocks"] and not receipt["charged_read_bytes"])
    return dict(before=before, after=after, exact=exact, passed=passed, reader=receipt)


def main():
    path = Path(__file__).resolve().parents[3]
    cpu_affinity = sorted(os.sched_getaffinity(0))
    if cpu_affinity != [3]:
        raise SystemExit("Run this fixture on CPU3")
    cases = {}
    with TemporaryDirectory(prefix="directed-cache-fixture-", dir=path) as root:
        root = Path(root)
        device = root.stat().st_dev
        for name in ("cold", "mixed", "warm"):
            directory = root / name
            directory.mkdir()
            cases[name] = exercise(directory, name)
    print(json.dumps(dict(st_dev=device, cpu_affinity=cpu_affinity, kernel=os.uname().release,
                          file_bytes=BLOCK, cases=cases), indent=2, sort_keys=True))
    return 0 if all(case["passed"] for case in cases.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
