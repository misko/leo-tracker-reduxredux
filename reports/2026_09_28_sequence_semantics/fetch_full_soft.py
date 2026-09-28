"""Extend the existing 64-carrier soft cache to full frames in bounded batches."""

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from fetch_full_reference import URL, Remote, decode_chunk

BASE = Path(__file__).parent


def main():
    out = BASE / "local/full-soft-reference-0-12.npz"
    if out.exists():
        raise FileExistsError("Existing cache retained")
    cache_path = BASE / "local/soft-transition-0-12.npz"
    cache = np.load(cache_path)
    cached_metadata = json.loads(cache_path.with_suffix(".json").read_text())
    etag = cached_metadata["etag"]
    remote = Remote()
    if remote.etag != etag:
        raise ValueError("Published source differs from existing soft cache")
    with h5py.File(remote, "r") as source:
        data = source["yDataSoft"]
        assert data.shape == (1009, 301, 1024) and data.chunks == (13, 301, 1)
        filters = data.id.get_create_plist()
        assert filters.get_nfilters() == 1 and filters.get_filter(0)[0] == 1
        dtype = data.dtype
        chunks = [data.id.get_chunk_info_by_coord((0, 0, b)) for b in range(1024)]
    symbols = np.empty((13, 301, 1024), complex)
    symbols[:, :, cache["bins"]] = cache["symbols"]
    total = remote.total
    batches = []
    missing = np.setdiff1d(np.arange(1024), cache["bins"])
    groups = []
    for b in sorted(missing, key=lambda b: chunks[b].byte_offset):
        if (
            not groups
            or len(groups[-1]) == 64
            or chunks[b].byte_offset - chunks[groups[-1][-1]].byte_offset > 1024**2
        ):
            groups.append([])
        groups[-1].append(b)
    batch_dir = BASE / "local/soft-download-batches"
    batch_dir.mkdir(exist_ok=True)
    for batch_index, group in enumerate(groups):
        bins = np.array(group)
        saved = batch_dir / f"batch-{batch_index}.npz"
        if saved.exists():
            prior = np.load(saved)
            if str(prior["etag"]) != etag or not np.array_equal(prior["bins"], bins):
                raise ValueError("Batch cache differs from requested source")
            symbols[:, :, bins] = prior["symbols"]
            continue
        selected = [chunks[b] for b in bins]
        assert all(c.filter_mask == 0 and c.size > 0 for c in selected)
        start = min(c.byte_offset for c in selected)
        stop = max(c.byte_offset + c.size for c in selected)
        if stop - start > 12 * 1024**2 or total + stop - start > 80 * 1024**2:
            raise ValueError("Download exceeds byte bound")
        remote = Remote()
        if remote.etag != etag:
            raise ValueError("Source changed between batches")
        remote.seek(start)
        blob = remote.read(stop - start)
        for b, chunk in zip(bins, selected, strict=True):
            at = chunk.byte_offset - start
            raw = decode_chunk(blob[at : at + chunk.size], dtype, (13, 301))
            symbols[:, :, b] = raw["real"] + 1j * raw["imag"]
        total += remote.total
        np.savez_compressed(saved, symbols=symbols[:, :, bins], bins=bins, etag=etag)
        batches.append(dict(first_bin=int(bins[0]), last_bin=int(bins[-1]), bytes=remote.total))
        print(f"Completed batch {batch_index + 1}/{len(groups)}; {total} bytes", flush=True)
    np.savez_compressed(out, symbols=symbols, bins=np.arange(1024), frame_indices=np.arange(13))
    metadata = dict(
        url=URL,
        etag=etag,
        dataset="yDataSoft",
        fetched_bytes=total,
        batches=batches,
        reused_cache_sha256=hashlib.sha256(cache_path.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
        limitation="Published normalized soft decisions; same acquisition, not raw IQ.",
    )
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
