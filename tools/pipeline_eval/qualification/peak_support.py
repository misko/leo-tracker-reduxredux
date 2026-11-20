"""Gate-independent physical peak families and retrospective shared support."""

from collections import Counter, defaultdict
from hashlib import sha256
from math import isfinite

from .factor_cross import CFO, GATE, MARGIN, winner, wrapped
from .full_v5_check import ALIAS_HZ, FRAME_HZ

SOURCES = ("capture-era", "ordinary", "wide")
COMPARISONS = ((0, 1), (0, 2), (1, 2))
BASINS = {"strict": (0.2e-6, 1000.0), "broad": (0.6e-6, 3000.0)}


def family_probe(candidates, frame, strict_samples):
    """Group duplicate physical aliases without score or rank in the membership rule."""
    points = [
        (
            (row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"]) % frame,
            row[CFO],
        )
        for row in candidates
    ]
    if any(not isfinite(x) for point in points for x in point):
        raise ValueError("invalid native candidate measurement")
    groups = []
    for i, (epoch, cfo) in sorted(enumerate(points), key=lambda row: row[1]):
        for group in groups:
            if all(
                abs(wrapped(epoch - points[j][0], frame)) <= strict_samples
                and abs(wrapped(cfo - points[j][1], ALIAS_HZ)) <= BASINS["strict"][1]
                for j in group
            ):
                group.append(i)
                break
        else:
            groups.append([i])
    families = [
        (tuple(points[i] for i in group), any(candidates[i][GATE] for i in group))
        for group in groups
    ]
    best_peak = winner(candidates)
    best_group = next((i for i, g in enumerate(groups) if best_peak in g), None)
    margin = None if best_peak is None else candidates[best_peak][MARGIN]
    return families, best_group, margin


def _affinities(left, right, frame, samples, frequency):
    rows, columns = ([[] for _ in side] for side in (left, right))
    epoch_left, epoch_right = set(), set()
    for i, (a, _) in enumerate(left):
        for j, (b, _) in enumerate(right):
            nearest = None
            for time_a, cfo_a in a:
                for time_b, cfo_b in b:
                    dt = abs(wrapped(time_a - time_b, frame))
                    if dt > samples:
                        continue
                    epoch_left.add(i)
                    epoch_right.add(j)
                    raw_df = cfo_a - cfo_b
                    df = abs(wrapped(raw_df, ALIAS_HZ))
                    if df <= frequency:
                        option = (
                            (dt / samples) ** 2 + (df / frequency) ** 2,
                            abs(raw_df) > frequency,
                        )
                        if nearest is None or option < nearest:
                            nearest = option
            if nearest is not None:
                distance, folded = nearest
                rows[i].append((distance, j, folded))
                columns[j].append((distance, i, folded))
    return (rows, columns), (epoch_left, epoch_right)


def _best(edges):
    if not edges:
        return None
    if len(edges) == 1:
        return edges[0]
    a, b = sorted(edges)[:2]
    return a if b[0] - a[0] > 1e-12 else None


def compare(left, right, frame, samples, frequency):
    """Return reciprocal unique family links and mutually exclusive winner drop-off."""
    (rows, columns), epochs = _affinities(left[0], right[0], frame, samples, frequency)
    choices_a = [_best(edges) for edges in rows]
    choices_b = [_best(edges) for edges in columns]
    links = {
        i: choice[1]
        for i, choice in enumerate(choices_a)
        if choice is not None and choices_b[choice[1]] is not None and choices_b[choice[1]][1] == i
    }
    backwards = {j: i for i, j in links.items()}
    outcome = []
    for source, target, edges, epoch, mapping, choices in (
        (left, right, rows, epochs[0], links, choices_a),
        (right, left, columns, epochs[1], backwards, choices_b),
    ):
        best, margin = source[1:]
        if best is None:
            outcome.append(None)
            continue
        other = mapping.get(best)
        if best not in epoch:
            category = "no_target_epoch"
        elif not edges[best]:
            category = "epoch_without_folded_cfo"
        elif other is None:
            category = "joint_without_reciprocal"
        elif not target[0][other][1]:
            category = "reciprocal_gate_failed"
        elif other != target[1]:
            category = "reciprocal_gated_nonwinner"
        else:
            category = "same_winner_family"
        strength = "low" if margin < 0.05 else "middle" if margin < 0.10 else "high"
        outcome.append(
            (category, strength, min(2, len(edges[best])), other is not None and choices[best][2])
        )
    return links, outcome


def lane(probe):
    return tuple(probe[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))


def circular_indices(probes):
    groups = defaultdict(list)
    for i, probe in enumerate(probes):
        groups[lane(probe)].append(i)
    shifted = [None] * len(probes)
    for items in groups.values():
        if len(items) < 2:
            raise ValueError("a channel and RX lane cannot support a nontrivial circular control")
        step = len(items) // 2
        for j, i in enumerate(items):
            shifted[i] = items[(j + step) % len(items)]
    return shifted


def corroborated(probes, links):
    ab, ac, bc = links
    return any(
        c is not None
        and bc.get(b) == c
        and all(probes[i][0][j][1] for i, j in enumerate((a, b, c)))
        for a, b in ab.items()
        if (c := ac.get(a)) is not None
    )


def _check_support(documents):
    base, *rest = documents
    for document in rest:
        if any(
            base[k] != document[k]
            for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")
        ):
            raise ValueError("candidate files change the acquisition clock support")
        if base["provenance"]["excluded_windows"] != document["provenance"]["excluded_windows"]:
            raise ValueError("candidate files change acquisition exclusions")
        if any(
            base["source"][k] != document["source"][k]
            for k in (
                "session_id",
                "sample_rate_hz",
                "input_manifest_sha256",
                "raw_recording_authority_digest",
            )
        ):
            raise ValueError("different recording or sample authority")
    all_probes = [d["source"]["probes"] for d in documents]
    for row in zip(*all_probes, strict=True):
        a, b, c = ({k: v for k, v in r.items() if k != "candidates"} for r in row)
        if not a == b == c:
            raise ValueError("factor sources do not share complete probe metadata")
    return all_probes


def examine(documents):
    probe_lists = _check_support(documents)
    rate = documents[0]["source"]["sample_rate_hz"]
    frame = round(rate / FRAME_HZ)
    prepared = [
        [family_probe(row["candidates"], frame, BASINS["strict"][0] * rate) for row in rows]
        for rows in probe_lists
    ]
    counters = defaultdict(Counter)
    blocks = circular_indices(probe_lists[0])
    selected = []
    for i, shifted in enumerate(blocks):
        triangles = []
        probe_set = [rows[i] for rows in prepared]
        for a, b in COMPARISONS:
            for name, (seconds, hz) in BASINS.items():
                for condition, right_index in (("observed", i), ("circular", shifted)):
                    left, right = prepared[a][i], prepared[b][right_index]
                    links, categories = compare(left, right, frame, seconds * rate, hz)
                    if name == "strict" and condition == "observed":
                        triangles.append(links)
                    for source, target, u, v, entry in (
                        (a, b, left, right, categories[0]),
                        (b, a, right, left, categories[1]),
                    ):
                        audit = counters[f"{name}/{condition}/{SOURCES[source]}→{SOURCES[target]}"]
                        audit["probes"] += 1
                        audit["ref_families"] += len(u[0])
                        audit["reciprocal_families"] += len(links)
                        audit["both_positive"] += u[1] is not None and v[1] is not None
                        audit["reference_positive"] += u[1] is not None
                        audit["target_positive"] += v[1] is not None
                        if entry is not None:
                            label, margin, degree, folded = entry
                            audit[label] += 1
                            audit[f"strength/{margin}/{label}"] += 1
                            audit[f"eligible_targets/{degree}/{label}"] += 1
                            audit["reference_winner_reciprocal_branch_lift"] += folded
        if corroborated(probe_set, triangles):
            selected.append(i)
    return dict(counters), selected


def thinned(ident, native, selected):
    """Hash-sample complete probes in exact matched physical lane and time block."""
    probes = native["source"]["probes"]
    anchor = native["clock_anchor"]["sample_counter"]
    rate = native["source"]["sample_rate_hz"]
    groups = defaultdict(list)
    block_of = []
    for i, row in enumerate(probes):
        block = (*lane(row), (row["valid_start_counter"] - anchor) // (30 * rate))
        block_of.append(block)
        groups[block].append(i)
    required = Counter(block_of[i] for i in selected)

    def rank(i):
        row = probes[i]
        raw = f"peak-support-thin-v1/{ident}/{row['visit_index']}/{row['receiver_id']}"
        return sha256(raw.encode()).digest()

    return sorted(i for block, n in required.items() for i in sorted(groups[block], key=rank)[:n])


def subset(native, indices, diagnostic):
    rows = native["source"]["probes"]
    if indices != sorted(set(indices)) or any(i < 0 or i >= len(rows) for i in indices):
        raise ValueError("physical support indices must preserve native probe order and identity")
    return dict(
        native,
        source=dict(native["source"], probes=[rows[i] for i in indices]),
        provenance=dict(native["provenance"], peak_support_diagnostic=diagnostic),
    )
