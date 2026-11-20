"""Retain the partner on every primary hit and phase-staggered quarter of misses."""

import json
from collections import Counter
from hashlib import sha256

from .second_on_miss import needs_partner
from .selective_capture import visit_pairs

POLICY = "partner-on-hit-plus-quarter-of-rf-lane-misses/v1"


def phase(center, lane):
    return sha256(f"quarter-miss:v1:{center}:{lane}".encode()).digest()[0] & 3


def project(document, schedule):
    source = document["source"]
    provenance = document["provenance"]
    misses, counts, decisions, probes = Counter(), Counter(), [], []
    for entry, (visit, lanes) in zip(schedule, visit_pairs(source["probes"]), strict=True):
        center, primary = entry["rf_center_hz"], entry["selected_receiver"]
        if visit != entry["visit"] or primary not in (0, 1) or type(center) is not int:
            raise ValueError("quarter-miss requires the original ordered RF/lane schedule")
        key = center, primary
        hit = not needs_partner(lanes[primary])
        second_hit = not needs_partner(lanes[1 - primary])
        audit = False
        if not hit:
            audit = misses[key] % 4 == phase(*key)
            misses[key] += 1
        retain = hit or audit
        counts["valid_visits"] += 1
        counts["primary_hits"] += hit
        counts["covisible_partner_hits"] += hit and second_hit
        counts["partner_only_hits"] += not hit and second_hit
        counts["audited_misses"] += audit
        counts["audited_partner_hits"] += audit and second_hit
        decisions.append(dict(entry, primary_hit=hit, audited_miss=audit, keep_partner=retain))
        probes.extend(
            row if retain or rx == primary else dict(row, candidates=[])
            for rx, row in enumerate(lanes)
        )
    body = json.dumps(
        [POLICY, source["analysis_manifest_sha256"], probes],
        sort_keys=True,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    digest = sha256(body).hexdigest()
    projected = dict(
        document,
        source=dict(source, probes=probes, analysis_manifest_sha256="sha256:" + digest),
        provenance=dict(
            provenance, run_id="replay-" + digest[:32], scope=POLICY, detector_mode=POLICY
        ),
    )
    return projected, decisions, dict(counts, invalid_visits=len(provenance["excluded_windows"]))
