"""Account for I/O from sealed metadata and saved Linux timing receipts."""

import argparse
import errno
import json
import os
import stat
from collections import Counter
from ctypes import CDLL, POINTER, byref, c_int, c_uint64
from hashlib import sha256
from pathlib import Path
from time import time_ns

from leo.contracts.multirate_window_recording import ShortWindowManifestV2
from leo.contracts.short_window_recording import ShortWindowManifestV1
from leo.storage.uri import confined_path


def pages(length, page_size):
    return (length + page_size - 1) // page_size


def _cache_query(path):
    library = CDLL(str(path))
    function = library.leo_cached_pages
    function.argtypes = [c_int, c_uint64, POINTER(c_uint64)]
    function.restype = c_int

    def query(fd, length):
        value = c_uint64()
        error = function(fd, length, byref(value))
        if error:
            raise OSError(error, os.strerror(error))
        return value.value

    return query


def cache_snapshot(members, page_size, query):
    """Observe current page-cache entries from read-only descriptors."""
    counts = Counter()
    errors = Counter()
    started = time_ns()
    for root, filename, length in members:
        counts["members"] += 1
        try:
            path = confined_path(root, root / filename, must_exist=True)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                metadata = os.fstat(fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_size != length
                ):
                    errors["unexpected_member_metadata"] += 1
                    continue
                counts["cached_pages"] += query(fd, length)
                counts["observed_members"] += 1
                counts["observed_file_pages"] += pages(length, page_size)
            finally:
                os.close(fd)
        except OSError as error:
            errors[errno.errorcode.get(error.errno, "unspecified")] += 1
    return dict(
        started_unix_ns=started,
        ended_unix_ns=time_ns(),
        members=counts["members"],
        observed_members=counts["observed_members"],
        cached_pages=counts["cached_pages"] if counts["observed_members"] else None,
        observed_file_pages=counts["observed_file_pages"],
        unavailable=dict(errors),
    )


def inventory(case, bulk, page_size, query=None):
    group = {kind: Counter() for kind in ("manifest", "index", "compressed_iq")}
    manifests, compressed = [], []
    windows = 0
    for entry in case["recording"]["segments"]:
        path = confined_path(bulk, bulk / entry["path"], must_exist=True)
        if path.name != "manifest.json":
            raise ValueError("Expected a bound segment manifest")
        content = path.read_bytes()
        if sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Changed sealed manifest: {path}")
        manifest_type = (
            ShortWindowManifestV2
            if json.loads(content).get("schema_version") == 2
            else ShortWindowManifestV1
        )
        manifest = manifest_type.model_validate_json(content)
        manifests.append(entry)
        windows += manifest.window_count
        sizes = {
            "manifest": [len(content)],
            "index": [c.index_bytes for c in manifest.chunks],
            "compressed_iq": [c.compressed_bytes for c in manifest.chunks],
        }
        for kind, values in sizes.items():
            group[kind].update(
                files=len(values),
                logical_bytes=sum(values),
                pages=sum(pages(length, page_size) for length in values),
            )
        if query is not None:
            compressed.extend(
                (path.parent, c.payload_relative_path, c.compressed_bytes) for c in manifest.chunks
            )
    if windows != case["recording"]["window_count"]:
        raise ValueError("Bound manifests differ from the expected visit count")
    result = dict(
        case=case["id"],
        window_count=windows,
        page_size_bytes=page_size,
        manifests=manifests,
        file_groups=group,
        recording_pages=sum(row["pages"] for row in group.values()),
    )
    if query is not None:
        result["present_cache_snapshot"] = cache_snapshot(compressed, page_size, query)
    return result


def receipt(case, pair, page_size):
    arms = {}
    for name in ("baseline", "candidate"):
        run = pair["runs"][name]
        if (
            run["raw_authority"] != case["raw_authority"]
            or run["receipt"]["window_count"] != case["recording"]["window_count"]
        ):
            raise ValueError("Pair does not match the bound recording")
        read_bytes = 512 * run["input_blocks"]  # Linux task accounting units.
        arms[name] = dict(
            cpu_s=run["cpu_s"],
            elapsed_s=run["elapsed_s"],
            non_cpu_s=run["elapsed_s"] - run["cpu_s"],
            input_blocks=run["input_blocks"],
            charged_read_bytes=read_bytes,
            charged_page_equivalents=read_bytes / page_size,
            voluntary_switches=run["voluntary_switches"],
            involuntary_switches=run["involuntary_switches"],
        )
    return dict(order=pair["order"], recording=pair["recording"], arms=arms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binding", type=Path)
    parser.add_argument("receipts", type=Path, nargs="*")
    parser.add_argument("--bulk", type=Path, required=True)
    parser.add_argument(
        "--cache-library", type=Path, help="Optional present-day cachestat snapshot"
    )
    args = parser.parse_args()
    binding = args.binding.read_bytes()
    case = json.loads(binding)["case"]
    size = os.sysconf("SC_PAGE_SIZE")
    query = _cache_query(args.cache_library) if args.cache_library is not None else None
    result = inventory(case, args.bulk, size, query)
    result["binding_sha256"] = sha256(binding).hexdigest()
    result["receipts"] = []
    for path in args.receipts:
        data = path.read_bytes()
        row = receipt(case, json.loads(data), size)
        result["receipts"].append(dict(file=str(path), sha256=sha256(data).hexdigest(), **row))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
