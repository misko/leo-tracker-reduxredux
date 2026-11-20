"""Run a second physical antenna only when the primary supplies no gated pilot."""

import json
from hashlib import sha256

from .negative_rescue import positive
from .one_lane_schedule import dispatch
from .selective_capture import visit_pairs

POLICY = "second-physical-lane-on-primary-fractional-miss/v1"


def needs_partner(probe):
    return not positive(probe)


def mark(document, probes):
    """Bind acquired rows to the physical input, detector, exclusions and this policy."""
    source, provenance = document["source"], document["provenance"]
    payload = [
        POLICY,
        provenance.get("detector_sha256"),
        source["input_manifest_sha256"],
        probes,
        provenance["excluded_windows"],
    ]
    raw = json.dumps(
        payload, sort_keys=True, allow_nan=False, ensure_ascii=False, separators=(",", ":")
    ).encode()
    digest = sha256(raw).hexdigest()
    return dict(
        document,
        source=dict(source, probes=probes, analysis_manifest_sha256="sha256:" + digest),
        provenance=dict(
            provenance, scope=POLICY, detector_mode=POLICY, run_id="replay-" + digest[:32]
        ),
    )


def project(document, rf_centers):
    schedule = dispatch(document, rf_centers)
    rows, decisions = [], []
    for entry, (visit, lanes) in zip(
        schedule, visit_pairs(document["source"]["probes"]), strict=True
    ):
        lane = entry["selected_receiver"]
        process_partner = needs_partner(lanes[lane])
        decisions.append(
            dict(
                visit=visit,
                rf_center_hz=entry["rf_center_hz"],
                primary_receiver=lane,
                partner_required=process_partner,
            )
        )
        rows.extend(
            probe if process_partner or rx == lane else dict(probe, candidates=[])
            for rx, probe in enumerate(lanes)
        )
    return mark(document, rows), decisions
