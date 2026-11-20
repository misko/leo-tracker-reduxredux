"""Select one physical receiver at each valid visit, alternating at each RF center."""

import json
from hashlib import sha256

from .selective_capture import visit_pairs
from .staggered_native import RfStagger

POLICY = "one-physical-lane-per-valid-rf-visit/v1"


def dispatch(document, rf_centers):
    source, provenance = document["source"], document["provenance"]
    valid = list(visit_pairs(source["probes"]))
    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    total = provenance["window_count"]
    admitted = {visit for visit, _ in valid}
    if (
        len(document["delivery_clocks"]) != total
        or len(valid) != provenance["processed_windows"]
        or len(excluded) != len(set(excluded))
        or len(excluded) != provenance["invalid_capture"]
        or admitted.intersection(excluded)
        or admitted.union(excluded) != set(range(total))
    ):
        raise ValueError("one-lane scheduling requires every valid visit and exact exclusions")
    state = RfStagger()
    selected = []
    for visit, (left, right) in valid:
        key = (left["channel"], left["edge"])
        if key != (right["channel"], right["edge"]) or key not in rf_centers:
            raise ValueError("physical receivers must share an authenticated RF tuning center")
        center = rf_centers[key]
        selected.append(
            dict(visit=visit, rf_center_hz=center, selected_receiver=state.reserve(center))
        )
    return selected


def mark(document, probes):
    source, provenance = document["source"], document["provenance"]
    payload = json.dumps(
        [
            POLICY,
            provenance.get("detector_sha256"),
            source["input_manifest_sha256"],
            probes,
            provenance["excluded_windows"],
        ],
        sort_keys=True,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    analysis_sha = "sha256:" + sha256(payload).hexdigest()
    return dict(
        document,
        source=dict(source, analysis_manifest_sha256=analysis_sha, probes=probes),
        provenance=dict(
            provenance, run_id="replay-" + analysis_sha[7:39], scope=POLICY, detector_mode=POLICY
        ),
    )


def project(document, rf_centers):
    """Keep one exact native probe payload and both physical slots on every visit."""
    visits = dispatch(document, rf_centers)
    chosen = {row["visit"]: row["selected_receiver"] for row in visits}
    probes = [
        probe
        if probe["receiver_id"] == chosen[probe["visit_index"]]
        else dict(probe, candidates=[])
        for probe in document["source"]["probes"]
    ]
    return mark(document, probes), visits
