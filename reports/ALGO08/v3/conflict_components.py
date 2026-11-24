"""Connected track choices from the observed association port."""

from collections import Counter, defaultdict
from itertools import combinations


def joined_sizes(vertices, edges):
    parent = {i: i for i in vertices}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in edges:
        parent[find(i)] = find(j)
    return sorted(Counter(find(i) for i in parent).values(), reverse=True)


def exclusive_edges(supports):
    uses = defaultdict(list)
    for index, observation_ids in supports.items():
        for identity in set(observation_ids):
            uses[identity].append(index)
    return {tuple(sorted(edge)) for variants in uses.values() for edge in combinations(variants, 2)}


def spanning_edges(groups):
    return {(ids[0], other) for ids in map(sorted, groups) for other in ids[1:]}


def topology(tracks, alternatives):
    """Price discrete support and shared numerical variables as separate edge sets."""
    active = {int(i): tracks[int(i)] for i in alternatives}
    claimed = exclusive_edges({i: t["observation_ids"] for i, t in active.items()})
    satellite = defaultdict(lambda: defaultdict(set))
    beta, smooth = defaultdict(set), defaultdict(set)
    for i, track in active.items():
        beta[(track["receiver"], track["channel"] > 4)].add(i)
        smooth[track["receiver"]].add(i)
        for norad, alias in alternatives[str(i)]:
            satellite[norad][i].add(alias)
    overlap, alias_equal, alias_different = set(), set(), set()
    for participants in satellite.values():
        for i, j in combinations(sorted(participants), 2):
            a, b = active[i], active[j]
            if max(a["start_s"], b["start_s"]) <= min(a["end_s"], b["end_s"]):
                overlap.add((i, j))
                left, right = participants[i], participants[j]
                if left & right:
                    alias_equal.add((i, j))
                if len(left | right) > 1:
                    alias_different.add((i, j))
    local = claimed | overlap
    with_phase = local | spanning_edges(satellite.values())
    with_calibration = with_phase | spanning_edges(beta.values()) | spanning_edges(smooth.values())
    return dict(tracks=len(active), distinct_satellites=len(satellite),
                same_observation_edges=len(claimed), overlapping_satellite_edges=len(overlap),
                overlapping_same_alias_edges=len(alias_equal), overlapping_different_alias_edges=len(alias_different),
                rf_dependent_c_tracks=sum(t["rf_hz"] != 11.5e9 for t in active.values()),
                components=dict(observation=joined_sizes(active, claimed), local=joined_sizes(active, local),
                                shared_phase=joined_sizes(active, with_phase),
                                receiver_calibration=joined_sizes(active, with_calibration),
                                common_position=joined_sizes(active, with_calibration | spanning_edges([active]))))
