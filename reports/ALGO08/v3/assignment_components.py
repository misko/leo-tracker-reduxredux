"""Price assignment separability on sealed, full-observation cold branches."""

from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / "single-core-2x/measurements/DS30-0008-moments-control.json.gz"
SHORT = HERE / "measurements/cold-track-row-reuse.json.gz"
TRACK = re.compile(r"SCAN-RX([12])-CH([1-8])-T\d+-RF(\d+(?:\.\d+)?)")


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Changed receipt: {path.name}")
    return json.loads(gzip.decompress(data))


def assignments(signature):
    rows = {track: (int(norad), int(alias)) for track, _, norad, alias in signature}
    if not rows or len(rows) != len(signature):
        raise ValueError("Empty or duplicate track assignment")
    return rows


def components(branches, *, receiver_offsets, fitted_c):
    if not branches or not branches[0] or any(b.keys() != branches[0].keys() for b in branches):
        raise ValueError("Compare branches on identical, nonempty track membership")
    factors = defaultdict(set)
    for track in branches[0]:
        match = TRACK.fullmatch(track)
        if match is None:
            raise ValueError(f"Unrecognized signed track identity: {track}")
        receiver, channel, rf = match.groups()
        for branch in branches:
            factors["phase", branch[track][0]].add(track)
        if receiver_offsets:
            factors["hardware", receiver, int(channel) > 4].add(track)
        if fitted_c and float(rf) != 11.5e9:
            factors["rf-calibration"].add(track)

    neighbours = defaultdict(set)
    for tracks in factors.values():
        root = min(tracks)
        neighbours[root].update(tracks)
        for track in tracks:
            neighbours[track].add(root)

    remaining = set(branches[0])
    groups = []
    while remaining:
        pending = [min(remaining)]
        group = set()
        while pending:
            track = pending.pop()
            if track in group:
                continue
            group.add(track)
            pending.extend(neighbours[track] - group)
        remaining.difference_update(group)
        groups.append(sorted(group))
    return sorted(groups, key=lambda group: (-len(group), group))


def census(signatures):
    branches = [assignments(sig) for sig in signatures]
    results = {}
    conditional = components(branches, receiver_offsets=False, fitted_c=False)
    changed = {t for t in branches[0] if len({b[t] for b in branches}) > 1}
    for name, hardware, fitted in [("receiver_parameters_fixed", False, False),
                                   ("receiver_band_offsets_free", True, False),
                                   ("receiver_band_offsets_and_calibration_free", True, True)]:
        groups = components(branches, receiver_offsets=True, fitted_c=fitted) if hardware else conditional
        sizes = [len(g) for g in groups]
        unique = [len({tuple(b[t] for t in group) for b in branches}) for group in groups]
        results[name] = dict(sizes=sizes, unique_patterns=unique,
                             tracks_in_groups_containing_changes=sum(len(g) for g in groups if changed.intersection(g)),
                             distinct_pattern_evaluations=sum(unique), naive_evaluations=len(groups)*len(branches),
                             distinct_track_evaluations=sum(n*k for n, k in zip(sizes, unique, strict=True)),
                             naive_track_evaluations=len(branches[0])*len(branches))
    return dict(tracks=len(branches[0]), branches=len(branches), changed_tracks=len(changed), groups=results)


def report():
    original = checked(ORIGINAL, "ee960eb5b9e4428d9f5330160df41504d06428fd06a7b4975fffd26ee35002fc")["control"]
    short = checked(SHORT, "27baf73f3eb1ccf8293b847fdc482b41dd8ad6cf249a3f503b8c8e81d5325692")
    original_rows = original["initial"]["ranked_signatures"]
    if original["initial"]["selected_signature"] not in original_rows:
        raise ValueError("Published cold winner missing from original ranked branches")
    short_winner = short["pair"]["released"]["branch"]["selected_signature"]
    if short_winner != short["pair"]["reused"]["branch"]["selected_signature"]:
        raise ValueError("Saved full-short winner mismatch")
    return dict(original_seven=census(original_rows), original_winner=census([original["initial"]["selected_signature"]]),
                full_short_winner=census([short_winner]))


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, allow_nan=False))
