"""Cross reported score fields and measured CFO/timing on the same winning factors."""

import argparse
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from .selected_changes import bound_native


SCORES = {"fractional_control_score", "fractional_exact_score", "fractional_margin"}
MEASURED = {"fractional_tracking_cfo_hz", "fractional_epoch_offset_samples"}


def mix(left, right, fields):
    rows = []
    for a, b in zip(left, right, strict=True):
        if {k: v for k, v in a.items() if k != "candidates"} != {k: v for k, v in b.items() if k != "candidates"}:
            raise ValueError("Different RF opportunity")
        factors = []
        for x, y in zip(a["candidates"], b["candidates"], strict=True):
            if x.keys() != y.keys() or not fields <= x.keys():
                raise ValueError("Different or missing factor fields")
            if any(x[k] != y[k] for k in x.keys() - SCORES - MEASURED):
                raise ValueError("Different winning rank, gate or integer epoch")
            factors.append(x | {k: y[k] for k in fields})
        rows.append(a | {"candidates": factors})
    return rows


def crossed_document(baseline, candidate, fields):
    """Copy selected fields from the candidate into matching baseline factors."""
    source = candidate["source"]
    raw = source["raw_recording_authority_digest"]
    if baseline["source"]["raw_recording_authority_digest"] != raw:
        raise ValueError("Different raw recording for crossed factors")
    rows = mix(baseline["source"]["probes"], source["probes"], fields)
    detector = candidate["provenance"]["detector_sha256"].removeprefix("sha256:")
    digest = canonical_digest(["cancellation", raw, detector, rows])
    return candidate | {"source": source | {"probes": rows, "analysis_manifest_sha256": digest},
                        "provenance": candidate["provenance"] | {"run_id": "blind-compact-" + digest[7:39]}}


def prepare(pair, output):
    if output.exists():
        raise FileExistsError(output)
    runs = json.loads(pair.read_bytes())["runs"]
    left, right = (bound_native(pair.parent / label, runs[label]) for label in ("baseline", "candidate"))
    source = right["source"]
    if (left["source"]["raw_recording_authority_digest"] != source["raw_recording_authority_digest"]
            or runs["baseline"]["receipt"]["region"] != runs["candidate"]["receipt"]["region"]):
        raise ValueError("Different raw or region")
    output.mkdir()
    for name, changed in (("candidate-scores", SCORES), ("candidate-cfo-time", MEASURED)):
        native = crossed_document(left, right, changed)
        (output / (name + ".json")).write_text(json.dumps(native, allow_nan=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    cli.add_argument("new_directory", type=Path)
    args = cli.parse_args()
    prepare(args.pair, args.new_directory)
