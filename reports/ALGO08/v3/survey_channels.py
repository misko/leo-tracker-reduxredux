"""Select continuous stereo RF groups from a causal prefix of verified signals."""

import argparse
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from rf_block_trial import CASES, run


def group(probe):
    return probe["actual_rf_hz"], probe["channel"]


def survey(pairs):
    counts = defaultdict(lambda: [[0, 0] for _ in range(4)])
    for index, pair in enumerate(pairs):
        quarter = 4 * index // len(pairs)
        for probe in pair:
            selected = probe["candidates"]
            if len(selected) > 1:
                raise ValueError("Expected a single continuation selection per antenna")
            cell = counts[group(probe)][quarter]
            cell[0] += len(selected)
            cell[1] += 1

    def rank(key):
        quarters = counts[key]
        worst = min(Fraction(hits, max(1, total)) for hits, total in quarters)
        pooled = Fraction(sum(x for x, _ in quarters), sum(n for _, n in quarters))
        return -worst, -pooled, key

    groups = sorted(counts)
    middle = (len(groups) + 1) // 2
    selected = {min(half, key=rank) for half in (groups[:middle], groups[middle:]) if half}
    return selected, counts


def choose(probes):
    pairs = list(zip(probes[::2], probes[1::2], strict=True))
    if not pairs:
        raise ValueError("No admitted stereo visits")
    last_visit = last_counter = -1
    for left, right in pairs:
        visit, counter = left["visit_index"], left["valid_start_counter"]
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1)
                or visit <= last_visit or counter <= last_counter or group(left) != group(right)
                or right["visit_index"] != visit or right["valid_start_counter"] != counter):
            raise ValueError("Inconsistent stereo timeline")
        last_visit, last_counter = visit, counter
    prefix = (len(pairs) + 5) // 6
    selected, counts = survey(pairs[:prefix])
    keep = {left["visit_index"] for i, (left, _) in enumerate(pairs) if i < prefix or group(left) in selected}
    stats = dict(survey_visits=prefix, selected_groups=sorted(selected), quarters=[
        dict(rf_hz=key[0], channel=key[1], selected_and_available=counts[key]) for key in sorted(counts)
    ])
    return keep, stats


def project(native):
    from leo.contracts.digests import canonical_digest

    source = native["source"]
    probes = source["probes"]
    keep, stats = choose(probes)
    rows = [p if p["visit_index"] in keep else dict(p, candidates=[]) for p in probes]
    detector = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    digest = canonical_digest(["cancellation", source["raw_recording_authority_digest"], detector, rows])
    packet = dict(native, source=dict(source, probes=rows, analysis_manifest_sha256=digest),
                  provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39]))
    stats.update(admitted_visits=len(rows) // 2, paid_visits=len(keep),
                 original_factors=sum(len(p["candidates"]) for p in probes),
                 retained_factors=sum(len(p["candidates"]) for p in rows),
                 paid_visits_digest=canonical_digest(sorted(keep)), packet_digest=canonical_digest(packet),
                 projection_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    return packet, stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.case, args.output, project=project)
