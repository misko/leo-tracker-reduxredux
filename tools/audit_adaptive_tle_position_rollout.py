#!/usr/bin/env python3
"""Verify immutable adaptive-TLE publications for a frozen rollout inventory.

This is a read-only post-rollout audit.  It never reconstructs tracks, selects
locations, opens recordings, or consults a position reference.  It reads only
the inventory supplied by the rollout operator and the public position
publication store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

from leo.contracts.digests import canonical_json_bytes
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore, AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

_ROOT = Path(__file__).parents[1]
_SOURCES = (
    Path(__file__),
    _ROOT / "src/leo/contracts/adaptive_tle_position.py",
    _ROOT / "src/leo/storage/adaptive_tle_position.py",
    _ROOT / "src/leo/cli/adaptive_tle_position.py",
    _ROOT / "src/leo/analysis/adaptive_tle_position.py",
    _ROOT / "src/leo/analysis/adaptive_tle_prediction.py",
    _ROOT / "src/leo/operations/adaptive_tle_position_inputs.py",
)


class _Version(NamedTuple):
    number: int
    analysis_id: str
    api_suffix: str
    store_type: type[AdaptiveTlePositionStore]


def _version(number: int) -> _Version:
    if number == 1:
        return _Version(
            1,
            "scanner-adaptive-tle-position-v1",
            "adaptive-tle-position",
            AdaptiveTlePositionStore,
        )
    if number == 2:
        return _Version(
            2,
            "scanner-adaptive-tle-position-v2",
            "adaptive-tle-position-v2",
            AdaptiveTlePositionStoreV2,
        )
    raise ValueError("adaptive TLE position audit version must be 1 or 2")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _source_digests() -> dict[str, str]:
    return {str(path.relative_to(_ROOT)): _sha256(path.read_bytes()) for path in _SOURCES}


def _inventory_session_ids(inventory: dict[str, Any]) -> list[str]:
    session_ids = inventory.get("session_ids_newest_first")
    if not isinstance(session_ids, list) or not session_ids:
        raise ValueError("inventory lacks a non-empty session_ids_newest_first list")
    if any(not isinstance(value, str) for value in session_ids):
        raise ValueError("inventory session IDs must be strings")
    if len(set(session_ids)) != len(session_ids):
        raise ValueError("inventory session IDs are not unique")
    return session_ids


def _validate_mask_evidence(document: Any) -> tuple[dict[str, int], list[str]]:
    """Return fixed-split counts without re-scoring any scientific evidence."""
    evidence = document.diagnostics.get("track_evidence")
    if not isinstance(evidence, list) or not evidence:
        return {}, ["diagnostic document lacks track_evidence"]
    counts = {
        "tracks": 0,
        "observations": 0,
        "training_observations": 0,
        "heldout_observations": 0,
        "partition_seeds": 0,
    }
    errors: list[str] = []
    seeds: set[str] = set()
    for index, row in enumerate(evidence):
        if not isinstance(row, dict):
            errors.append(f"track_evidence[{index}] is not an object")
            continue
        observation_ids, times, mask, seed = (
            row.get("observation_ids"),
            row.get("times_s"),
            row.get("training_mask"),
            row.get("partition_seed"),
        )
        if not (
            isinstance(observation_ids, list)
            and isinstance(times, list)
            and isinstance(mask, list)
            and isinstance(seed, str)
            and len(observation_ids) == len(times) == len(mask)
            and observation_ids
        ):
            errors.append(f"track_evidence[{index}] has inconsistent fixed-split arrays")
            continue
        if not all(isinstance(value, bool) for value in mask):
            errors.append(f"track_evidence[{index}] training_mask is not boolean")
            continue
        if not any(mask) or all(mask):
            errors.append(f"track_evidence[{index}] lacks train or held-out observations")
            continue
        counts["tracks"] += 1
        counts["observations"] += len(mask)
        counts["training_observations"] += sum(mask)
        counts["heldout_observations"] += len(mask) - sum(mask)
        seeds.add(seed)
    counts["partition_seeds"] = len(seeds)
    return counts, errors


def _http_get(url: str, timeout_seconds: float) -> bytes:
    request = Request(url, headers={"Accept": "application/json, image/png"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read()


def _verify_api(
    *, api_base: str, session_id: str, manifest: Any, version: _Version, timeout_seconds: float
) -> None:
    """Verify the deployed read-only routes against the immutable store manifest."""
    base = (
        f"{api_base.rstrip('/')}/api/v1/scanner/tracking/"
        f"{quote(session_id, safe='')}/{version.api_suffix}"
    )
    payload = json.loads(_http_get(base, timeout_seconds))
    served = payload.get("manifest")
    if (
        not isinstance(served, dict)
        or payload.get("session_id") != session_id
        or payload.get("state") != "complete"
    ):
        raise ValueError("API status response does not bind the requested session")
    if served.get("document_sha256") != manifest.document_sha256:
        raise ValueError("API document SHA differs from immutable store manifest")
    artifacts = served.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise ValueError("API artifact inventory differs from immutable store manifest")
    artifact = artifacts[0]
    if not isinstance(artifact, dict):
        raise ValueError("API map artifact is not an object")
    if artifact.get("sha256") != manifest.artifacts[0].sha256:
        raise ValueError("API map SHA differs from immutable store manifest")
    image = _http_get(
        base + "/map.png?" + urlencode({"sha256": manifest.artifacts[0].sha256}),
        timeout_seconds,
    )
    if _sha256(image) != manifest.artifacts[0].sha256:
        raise ValueError("API map PNG SHA differs from immutable store manifest")
    with Image.open(BytesIO(image)) as decoded:
        decoded.verify()


def audit_rollout(
    store: AdaptiveTlePositionStore,
    inventory: dict[str, Any],
    *,
    tracking_inputs: ScannerTrackingInputStore | None = None,
    api_base: str | None = None,
    api_timeout_seconds: float = 10,
    version: int = 2,
) -> dict[str, Any]:
    """Verify each frozen session through the immutable public publication port."""
    session_ids = _inventory_session_ids(inventory)
    target = _version(version)
    states = {state: 0 for state in ("pending", "diagnostic", "insufficient", "failed")}
    aggregate_masks = {
        "tracks": 0,
        "observations": 0,
        "training_observations": 0,
        "heldout_observations": 0,
        "partition_seeds": 0,
    }
    rows: list[dict[str, Any]] = []
    invalid_count = png_count = api_count = source_manifest_count = reference_metric_count = 0
    for session_id in session_ids:
        row: dict[str, Any] = {"session_id": session_id}
        try:
            status = store.status(session_id)
            row["publication_state"] = status.state
            if status.manifest is None:
                states["pending"] += 1
                rows.append(row)
                continue
            manifest, document = status.manifest, status.manifest.document
            if (
                document.schema_version != target.number
                or document.analysis_id != target.analysis_id
            ):
                raise ValueError("publication document differs from requested version")
            if target.number == 2 and tuple(
                prior.region.radius_km for prior in document.priors
            ) not in ((), (250.0, 500.0)):
                raise ValueError("V2 publication prior radii differ from Sacramento 250/Reno 500")
            states[document.state] += 1
            row.update(
                document_sha256=manifest.document_sha256,
                evidence_sha256=document.evidence_sha256,
                input_manifest_sha256=document.input_manifest_sha256,
                scientific_state=document.state,
                known_position_used_for_inference=document.known_position_used_for_inference,
                position_fix_claimed=document.position_fix_claimed,
            )
            raw = canonical_json_bytes(document.model_dump(mode="json"))
            if _sha256(raw) != manifest.document_sha256:
                raise ValueError("document SHA differs from manifest")
            image = store.artifact(session_id)
            if image is None:
                raise ValueError("complete publication lacks map PNG")
            if _sha256(image) != manifest.artifacts[0].sha256:
                raise ValueError("map PNG SHA differs from manifest")
            if len(image) != manifest.artifacts[0].byte_count:
                raise ValueError("map PNG byte count differs from manifest")
            with Image.open(BytesIO(image)) as decoded:
                decoded.verify()
                row["map_size_px"] = list(decoded.size)
            png_count += 1
            if tracking_inputs is not None:
                source = tracking_inputs.load(session_id)
                if (
                    source.input_manifest_sha256 != document.input_manifest_sha256
                    or source.analysis_manifest_sha256 != document.analysis_manifest_sha256
                ):
                    raise ValueError("current tracking source manifest differs from publication")
                source_manifest_count += 1
                row["current_source_manifest_match"] = True
            if api_base is not None:
                _verify_api(
                    api_base=api_base,
                    session_id=session_id,
                    manifest=manifest,
                    version=target,
                    timeout_seconds=api_timeout_seconds,
                )
                api_count += 1
                row["api_verified"] = True
            if document.state == "diagnostic":
                mask_counts, errors = _validate_mask_evidence(document)
                if errors:
                    raise ValueError("; ".join(errors))
                for key, value in mask_counts.items():
                    aggregate_masks[key] += value
                reference = document.diagnostics.get("reference_evaluation_only")
                if (
                    not isinstance(reference, dict)
                    or reference.get("used_for_inference") is not False
                ):
                    raise ValueError("diagnostic reference is not labeled evaluation-only")
                reference_metric_count += sum(
                    candidate.horizontal_error_m is not None
                    for prior in document.priors
                    for candidate in (prior.selected, prior.finest)
                    if candidate is not None
                )
                row["fixed_split"] = mask_counts
            row["valid"] = True
        except (OSError, ValueError, KeyError, UnidentifiedImageError) as error:
            invalid_count += 1
            row.update(valid=False, error=f"{type(error).__name__}: {error}")
        rows.append(row)
    return {
        "schema": "adaptive-tle-position-rollout-audit/v1",
        "purpose": "read-only publication integrity and scientific-state audit; no truth used",
        "target_version": target.number,
        "target_analysis_id": target.analysis_id,
        "inventory_sha256": _sha256(canonical_json_bytes(inventory)),
        "frozen_window": inventory.get("frozen_window"),
        "source_sha256": _source_digests(),
        "summary": {
            "frozen_session_count": len(session_ids),
            "publication_states": states,
            "verified_map_png_count": png_count,
            "verified_api_route_count": api_count,
            "current_source_manifest_match_count": source_manifest_count,
            "invalid_publication_count": invalid_count,
            "diagnostic_fixed_split_totals": aggregate_masks,
            "postselection_reference_metric_count": reference_metric_count,
            "selection_declarations": {
                "known_position_used_for_inference": False,
                "position_fix_claimed": False,
                "reference_metrics_labeled_evaluation_only": True,
            },
        },
        "sessions": rows,
    }


def _write_once(path: Path, document: dict[str, Any]) -> None:
    payload = json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with open(descriptor, "wb", closefd=True) as stream:
        stream.write(payload)
    Path(temporary).replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--api-base",
        help="optional deployed API base, for example http://127.0.0.1:8000",
    )
    parser.add_argument("--api-timeout-seconds", type=float, default=10)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="exit nonzero when any frozen session has not published a valid sidecar",
    )
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    if args.api_timeout_seconds <= 0:
        parser.error("api timeout must be positive")
    inputs = ScannerTrackingInputStore(args.bulk_root)
    try:
        target = _version(args.version)
        receipt = audit_rollout(
            target.store_type(args.bulk_root),
            inventory,
            tracking_inputs=inputs,
            api_base=args.api_base,
            api_timeout_seconds=args.api_timeout_seconds,
            version=target.number,
        )
    finally:
        inputs.close()
    receipt["audited_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_once(args.output, receipt)
    print(json.dumps(receipt["summary"], sort_keys=True))
    incomplete = receipt["summary"]["publication_states"]["pending"]
    invalid = receipt["summary"]["invalid_publication_count"]
    if invalid or (args.require_complete and incomplete):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
