"""Freeze a physical-manifest sample for the fixed two-rate replay."""

import argparse
from collections import Counter
from hashlib import sha256

from ..__main__ import encoded, save_json
from ..variants.selective_capture import visit_pairs
from . import one_lane_roster as roster
from .full_v5_check import _sha

REPORT = roster.fixed.SCREEN / "receiver-deadline/two-rate-holdout"
SALT = "2026-11-19/receiver-deadline/two-rate-holdout/v1"
ANCHORS = ("DS26-0237", "DS29-0082")
STRIDE = 12


def salted(*values):
    return sha256(encoded([SALT, *values])).hexdigest()


def select_recordings(manifests):
    digest = {ident: salted("membership", manifest) for ident, manifest in manifests.items()}
    groups = {group: [] for group in ("DS26", "DS29")}
    for ident in sorted(manifests.keys() - set(ANCHORS), key=lambda key: (digest[key], key)):
        groups[ident.split("-")[0]].append(ident)
    selected = [*ANCHORS, *groups["DS26"][:3], *groups["DS29"][:3]]
    return selected, groups, digest


def schedule(document):
    count = Counter()
    offset, selected = {}, []
    manifest = document["source"]["input_manifest_sha256"]
    for visit, pair in visit_pairs(document["source"]["probes"]):
        rf, other = [p["actual_rf_hz"] for p in pair]
        if rf != other or int(rf) != rf or rf <= 0:
            raise ValueError("physical stereo visit does not share one integer RF center")
        rf = int(rf)
        if rf not in offset:
            offset[rf] = int(salted("rf-stagger", manifest, rf), 16) % STRIDE
        ordinal = count[rf]
        if ordinal % STRIDE == offset[rf]:
            selected.append(dict(visit=visit, rf_hz=rf, ordinal=ordinal))
        count[rf] += 1
    if sum(count.values()) != document["provenance"]["processed_windows"]:
        raise ValueError("schedule does not contain every valid physical visit")
    return dict(selected=selected, visits_per_rf=count, stagger_per_rf=offset)


def freeze():
    path = REPORT / "membership-lock.json"
    if path.exists():
        raise FileExistsError("two-rate holdout membership is already frozen")
    groups, media, *_ = roster.inventory()
    manifests, schedules = {}, {}
    for ident in groups["all"]:
        document = roster.stock_document(media[ident])
        manifests[ident] = document["source"]["input_manifest_sha256"]
        schedules[ident] = schedule(document)
    if len(set(manifests.values())) != 22:
        raise ValueError("expected 22 distinct physical manifests")
    selected, ranks, digest = select_recordings(manifests)
    for ident in selected:
        save_json(REPORT / "schedules" / f"{ident}.json", schedules[ident])
    save_json(
        path,
        dict(
            salt=SALT,
            stride=STRIDE,
            selected=selected,
            timing_anchors=ANCHORS,
            ranked_pool=ranks,
            membership_sha256=digest,
            physical_manifest_sha256=manifests,
            stock_archives=media,
            prior_roster_membership=groups,
            schedule_sha256={
                ident: _sha(REPORT / "schedules" / f"{ident}.json") for ident in selected
            },
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            sources={
                "roster": roster.ROSTER_SHA,
                "frozen_twenty": roster.RECONSTRUCTION_SHA,
                "fresh_two": roster.FRESH_RAW_SHA,
            },
        ),
    )
    print(" ".join(selected))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze",))
    parser.parse_args()
    freeze()
