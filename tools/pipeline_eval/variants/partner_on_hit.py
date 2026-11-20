"""Project stored fixed-four packets with the partner retained on primary hits."""

import json
from collections import Counter
from hashlib import sha256

from .second_on_miss import needs_partner
from .selective_capture import visit_pairs

POLICY = "partner-on-strict-primary-hit/v1"


def project(document, schedule):
    source, prior = document["source"], document["provenance"]
    out, counts = [], Counter()
    for entry, (visit, lanes) in zip(schedule, visit_pairs(source["probes"]), strict=True):
        primary = entry["selected_receiver"]
        if visit != entry["visit"] or primary not in (0, 1):
            raise ValueError("projection requires the original physical primary schedule")
        partner = 1 - primary
        hit, partner_hit = (not needs_partner(lanes[i]) for i in (primary, partner))
        counts["valid_visits"] += 1
        counts["primary_hits"] += hit
        counts["covisible_partner_hits"] += hit and partner_hit
        counts["partner_only_hits"] += not hit and partner_hit
        counts["neither_hits"] += not hit and not partner_hit
        out.extend(
            probe if hit or lane == primary else dict(probe, candidates=[])
            for lane, probe in enumerate(lanes)
        )
    digest = sha256(
        json.dumps(
            [POLICY, source["analysis_manifest_sha256"], out],
            sort_keys=True,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return (
        dict(
            document,
            source=dict(source, probes=out, analysis_manifest_sha256="sha256:" + digest),
            provenance=dict(
                prior, run_id="replay-" + digest[:32], scope=POLICY, detector_mode=POLICY
            ),
        ),
        dict(counts, invalid_visits=len(prior["excluded_windows"])),
    )
