"""Qualify v5 endpoint projection from archived pre-render scientific axes."""

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

from tools.pipeline_eval import corpus
from tools.pipeline_eval.scoring import score
from tools.pipeline_eval.variants.v5_lean import (
    ARMS,
    ROOF_CENTER,
    SOURCE,
    SOURCE_SHA256,
    endpoint_latlon,
)

ARCHIVE = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001/results")
BOUNDARY = "Archived pre-render east/north axes to v5 latitude/longitude"
CHECKPOINT = b'["reassociation_complete",["map",[["status","reassociation_evaluated"],'
RECOVERY = b'["recovery",["map",'
FINAL = b'["final",["map",'
REGION_SHA256 = "sha256:4fc3b3ec6087fcb03e76fb431758375ffedda3fd823070dbe2b58a0e8a77938b"


def sha256(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _map(node):
    kind, pairs = node
    if kind != "map":
        raise ValueError("Expected an encoded scientific evidence mapping")
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate scientific evidence field")
    return result


def _pre_render_axes(archive):
    # Decode only the final scientific checkpoint. The archive also contains plot endpoints.
    raw = archive.read("values.json")
    if raw.count(CHECKPOINT) != 1:
        raise ValueError("Expected one completed reassociation checkpoint")
    start = raw.index(CHECKPOINT) + len(CHECKPOINT)
    if not raw.startswith(RECOVERY, start) or raw.count(FINAL, start) != 1:
        raise ValueError("Expected one completed reassociation recovery decision")
    final = raw.index(FINAL, start)
    pair, _ = json.JSONDecoder().raw_decode(raw[final : final + 4096].decode("utf-8", "ignore"))
    name, record = pair
    if name != "final" or set(_map(record)) != set(ARMS):
        raise ValueError("Expected both pre-render calibration arms")
    return {arm: _map(node)["x"] for arm, node in _map(record).items()}


def _project(archive_path, expected_sha, region):
    raw = archive_path.read_bytes()
    if sha256(raw) != expected_sha:
        raise ValueError(f"Evidence archive digest mismatch for {archive_path}")
    arms, digests = {}, {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for arm, (kind, digest) in _pre_render_axes(archive).items():
            if kind != "array" or not digest.startswith("sha256:"):
                raise ValueError("Expected content-bound numerical axes")
            blob = archive.read(digest.removeprefix("sha256:"))
            if sha256(blob) != digest:
                raise ValueError("Selected axes digest mismatch")
            axes = np.load(io.BytesIO(blob), allow_pickle=False)
            if axes.shape != (2,) or not np.isfinite(axes).all():
                raise ValueError("Expected one finite east/north pair")
            arms[arm] = {"latlon": endpoint_latlon(region, axes)}
            digests[arm] = digest
    return dict(status="ok", boundary=BOUNDARY, arms=arms, metrics={}), digests


def qualify(archive, *, only=None):
    sys.path.insert(0, str(SOURCE))
    from leo.analysis.localization_v3 import region

    region_path = Path(region.__file__).resolve()
    if not region_path.is_relative_to(SOURCE) or sha256(region_path.read_bytes()) != REGION_SHA256:
        raise ValueError("Qualification requires the frozen SearchRegion implementation")
    panel = "ds26-common127"
    ids, _ = corpus._selection(panel)
    if only:
        if not only <= set(ids):
            raise ValueError("Qualification cases must belong to DS26 common 127")
        ids = [case for case in ids if case in only]
    predictions, bindings = {}, {}
    search_region = region.SearchRegion(ROOF_CENTER)
    for case in ids:
        destination = archive / f"{case}-r0"
        evidence = destination / "baseline/experimental-evidence.zip"
        receipt = (destination / "baseline-execution.json").read_bytes()
        record = json.loads(receipt)
        worker = record["worker"]
        if (
            record["status"] != "complete"
            or record["role"] != "baseline"
            or worker["source_sha256"] != SOURCE_SHA256
        ):
            raise ValueError(f"Unqualified baseline archive for {case}")
        archive_sha = worker["artifact"]["sha256"]
        result, axes = _project(evidence, archive_sha, search_region)
        predictions[case] = {"result": result}
        bindings[case] = dict(
            archive=str(evidence),
            archive_sha256=archive_sha,
            archive_receipt_sha256=sha256(receipt),
            request_sha256=record["request_sha256"],
            pre_render_axes_sha256=axes,
        )
    refs = [item for item in corpus.references(panel) if item["id"] in predictions]
    summary, rows = score(refs, predictions)
    rows = [
        {k: row[k] for k in ("id", "arm", "error_km", "v5_error_km", "v5_coordinate_delta_km")}
        for row in rows
    ]
    return dict(
        boundary=BOUNDARY,
        model_source_sha256=SOURCE_SHA256,
        search_region_source_sha256=REGION_SHA256,
        panel=panel,
        bindings=bindings,
        scored_rows=rows,
        summary=summary,
        missing_or_different_coordinates=sum(row["v5_coordinate_delta_km"] != 0 for row in rows),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    path = args.out.resolve()
    if path.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    result = qualify(args.archive, only=set(args.case or []))
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        f"Projected {len(result['scored_rows'])} arm endpoints. "
        f"Different coordinates: {result['missing_or_different_coordinates']}."
    )


if __name__ == "__main__":
    main()
