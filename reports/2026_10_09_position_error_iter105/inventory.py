"""Pure metadata selection/deduplication for a failure-triggered pilot; no fits."""

import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def pilot_members(authority):
    """Every newer development member with a recorded ordinary calibration failure.

    This deliberately does not require retained_baseline: sep25/sep50 retention
    is equally operational. Failure severity and reference errors are not read.
    """
    rows = []
    for member in authority["members"]:
        if member["dataset"] != "POST18-development" or not member["failure_bindings"]:
            continue
        unique, unavailable = {}, []
        for failure in member["failure_bindings"]:
            basin = failure["basin"]
            if not basin.startswith("point:"):
                unavailable.append(dict(basin=basin, reason="not-an-ordinary-retained-region"))
                continue
            coarse = [
                row
                for row in failure["checkpoint_attempts"]
                if row.get("available") and row.get("contains_coarse_fit")
            ]
            if not coarse:
                unavailable.append(
                    dict(basin=basin, reason="missing-bound-bootstrap/coarse-receipt")
                )
                continue
            identities = {(row["value_sha256"], row["bootstrap_sha256"]) for row in coarse}
            if len(identities) != 1:
                unavailable.append(dict(basin=basin, reason="conflicting-coarse-receipts"))
                continue
            selected = min(coarse, key=lambda row: row["key"])
            identity = dict(
                input_manifest_sha256=failure["input_manifest_sha256"],
                score_signature=failure["score_prior_signature"],
                coarse_sha256=selected["value_sha256"],
                bootstrap_sha256=selected["bootstrap_sha256"],
                basin=basin,
            )
            key = digest(identity)
            if key not in unique:
                unique[key] = dict(
                    identity=identity,
                    deduplication_key=key,
                    source_passes=[],
                    checkpoint_binding=failure["checkpoint_binding"],
                    coarse_key=selected["key"],
                    coarse_sha256=selected["value_sha256"],
                    observed_spacing_km=failure.get("baseline_spacing_km"),
                )
            unique[key]["source_passes"].append(
                dict(
                    source=failure["source"],
                    region=failure["region"],
                    configuration_signature=failure["configuration_signature"],
                    retained_baseline=failure["retained_baseline"],
                )
            )
        rows.append(
            dict(
                dataset=member["dataset"],
                label=member["label"],
                session_id=member["session_id"],
                triggers=sorted(unique.values(), key=lambda row: row["deduplication_key"]),
                unavailable=unavailable,
                baseline_requirement="Fresh standard B7; old hard60 errors are not B7 baseline",
            )
        )
    return sorted(rows, key=lambda row: row["label"])


def regional_triggers(
    regions, *, input_digest, score_signature, bank_signature, minimum_local_radius_km=25.0
):
    """Apply the same rule to all ordinary failures in a matched B7 baseline.

    Unlike the metadata inventory this is a numerical-model-bound inventory:
    observations, prior/score and bank signatures must be verified by the caller.
    Existing recovery failures are accounted separately, not retried recursively.
    """
    candidates, failures = {}, []
    for name, region in regions.items():
        points = region["points"]
        spacing = {
            f"point:{row['east_km']:g}:{row['north_km']:g}": row["spacing_km"]
            for row in region["searches"]["V16"]["evaluations"]
        }
        for failure in region["failures"]:
            if failure.get("stage") != "calibration":
                continue
            key = failure["basin"]
            if not key.startswith("point:"):
                failures.append(
                    dict(source=name, basin=key, reason="existing-recovery-failure-no-recursion")
                )
                continue
            receipt = points.get(key)
            original = receipt.get("result") if receipt else None
            if not original or key not in spacing:
                failures.append(
                    dict(source=name, basin=key, reason="missing-ordinary-coarse-or-spacing")
                )
                continue
            identity = dict(
                input_digest=input_digest,
                score_signature=score_signature,
                bank_signature=bank_signature,
                basin=key,
                original_sha256=digest(original),
                local_radius_km=max(minimum_local_radius_km, spacing[key] / math.sqrt(2)),
            )
            identity_key = digest(identity)
            if identity_key not in candidates:
                candidates[identity_key] = dict(
                    identity=identity,
                    key=key,
                    source_passes=[],
                    spacing_km=spacing[key],
                    contributing_spacings_km=[],
                    original=original,
                )
            candidates[identity_key]["source_passes"].append(name)
            candidates[identity_key]["contributing_spacings_km"].append(spacing[key])
    return dict(
        candidates=[candidates[key] for key in sorted(candidates)], explicit_failures=failures
    )
