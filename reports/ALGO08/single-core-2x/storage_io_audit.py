"""Account for I/O from sealed metadata and saved Linux timing receipts."""

import argparse
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leo.contracts.multirate_window_recording import ShortWindowManifestV2
from leo.contracts.short_window_recording import ShortWindowManifestV1
from leo.storage.uri import confined_path
from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query, pages


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
    query = load_query(args.cache_library) if args.cache_library is not None else None
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
