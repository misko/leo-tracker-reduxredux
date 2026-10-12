"""Evaluate all sealed local fits against the same recording's public reference."""

import argparse
import json
import math
from pathlib import Path

from band_calibrated_merge_study import ARMS, LOCAL, PREVIOUS
from continuous_merge_study import sha, write

from leo.analysis.regional_position_score import coordinates
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store


def evaluate(case, reference_root):
    protocol_path = case / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    for path, digest in protocol["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("executed authority changed: " + path)
    paths = [case / (v + "-" + a + ".json") for v in protocol["variants"] for a in ARMS]
    results = [json.loads(path.read_bytes()) for path in paths]
    if any(
        r["protocol_sha256"] != sha(protocol_path) or r["reference_usage"] != "none"
        for r in results
    ):
        raise ValueError("numerical fits must match the reference-free frozen protocol")
    seal = {str(path): sha(path) for path in paths}
    seal_path = case / "evaluation-seal.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("sealed evaluation changed")
    write(seal_path, seal)
    census_path = PREVIOUS / "local" / protocol["dataset"] / protocol["session_id"] / "census.json"
    census = json.loads(census_path.read_bytes())
    manifest = B7Store(reference_root).status(protocol["session_id"]).manifest
    if manifest is None:
        manifest = Hard60Store(reference_root).status(protocol["session_id"]).manifest
    if manifest is None:
        raise ValueError("own reference product unavailable; retain the unevaluated case")
    document = manifest.document
    if document.input_manifest_sha256 != census["input_manifest_sha256"]:
        raise ValueError("reference product belongs to another recording")
    reference = (document.reference_latitude_deg, document.reference_longitude_deg)
    rows = []
    for result in results:
        latitude, longitude = coordinates(RegionalPrior(), result["fit"]["vector"][:2])
        lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
        h = (
            math.sin((lat - ref_lat) / 2) ** 2
            + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
        )
        rows.append(
            {
                "variant": result["variant"],
                "arm": result["arm"],
                "stationary": result["fit"]["converged"],
                "reference_error_m": 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h)))),
                **{
                    key: result[key]
                    for key in (
                        "objective",
                        "singleton_nll",
                        "singleton_signal_mass",
                        "singleton_rms_hz",
                        "band_offsets_hz",
                    )
                },
            }
        )
    destination = case / "evaluation-cohort-reference.json"
    write(
        destination,
        {
            "rows": rows,
            "reference": reference,
            "reference_evidence": document.reference_evidence,
            "reference_root": str(reference_root),
            "reference_document_sha256": canonical_digest(document.model_dump(mode="json")),
            "seal_sha256": sha(seal_path),
            "script_sha256": sha(Path(__file__)),
            "protocol_sha256": sha(protocol_path),
            "scope": (
                "All local conditions sealed before public reference access; nonstationary "
                "fits remain flagged, never silently excluded."
            ),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--reference-products", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    evaluate(LOCAL / args.dataset / args.session_id, args.reference_products)
