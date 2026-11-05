"""Native residual fragments with exact physical ownership and source boundaries.

Pure numerical extraction of the frozen recovery ranking; no legacy reader or
terminal adapter. Identical physical aliases collapse, partial overlaps fail.
"""

import hashlib
import math

PERIOD_HZ = 1 / 4.4e-6
GAP_S = 5.0


def canonical_tracks(tracks):
    """Collapse identical physical-ID aliases; never union partially overlapping curves."""
    groups = {}
    for index, track in enumerate(tracks):
        ids = track["observation_ids"]
        if (
            len(ids) != len(set(ids))
            or len(ids) != len(track["times"])
            or len(ids) != len(track["values"])
        ):
            raise ValueError("Duplicate IDs or unequal source arrays")
        key = (track["receiver"], track["channel"], track["rf_hz"], frozenset(ids))
        groups.setdefault(key, []).append((index, track))
    result, owner = [], {}
    for variants in sorted(groups.values(), key=lambda group: group[0][0]):
        index, track = variants[0]
        for oid in track["observation_ids"]:
            if oid in owner:
                raise ValueError(
                    f"Partial graph-source overlap: {oid}, tracks {owner[oid]}/{index}"
                )
            owner[oid] = index
        result.append((index, track, [dict(track_index=i, key=t["key"]) for i, t in variants]))
    return result


def piece_membership(track):
    indices = track.get("indices", list(range(len(track["times"]))))
    if len(indices) != len(track["times"]):
        raise ValueError("Native index array differs from observation array")
    memberships = []
    for index, time in zip(indices, track["times"], strict=True):
        matches = [
            i
            for i, piece in enumerate(track.get("pieces", []))
            if index in piece.get("indices", [])
        ]
        if not matches:
            matches = [
                i
                for i, piece in enumerate(track.get("pieces", []))
                if piece["start_s"] <= time <= piece["end_s"]
            ]
        memberships.append(matches)
    return memberships


def runs(track, associated, gap_s=GAP_S):
    """Source adjacency includes claimed points, so subtraction cannot bridge them."""
    membership = piece_membership(track)
    result, current = [], []
    for i in sorted(range(len(track["times"])), key=lambda k: (track["times"][k], k)):
        if track["observation_ids"][i] in associated:
            if current:
                result.append(current)
                current = []
            continue
        piece = membership[i][0] if membership[i] else None
        if current:
            previous = current[-1]
            old_piece = membership[previous][0] if membership[previous] else None
            if track["times"][i] - track["times"][previous] > gap_s or piece != old_piece:
                result.append(current)
                current = []
        current.append(i)
    if current:
        result.append(current)
    return result


def span(track, indices):
    return float(track["times"][indices[-1]] - track["times"][indices[0]])


def polynomial(piece, time):
    x = (time - piece["reference_time_s"]) / piece["time_scale_s"]
    coefficients = piece["coefficients_hz"]
    total, p0, p1 = coefficients[0], 1.0, x
    if len(coefficients) > 1:
        total += coefficients[1] * p1
    for degree in range(2, len(coefficients)):
        p0, p1 = p1, ((2 * degree - 1) * x * p1 - (degree - 1) * p0) / degree
        total += coefficients[degree] * p1
    return total


def fragment_rows(case, tracks, observations, associated, identities=None):
    lookup = {o["observation_id"]: o for o in observations}
    if len(lookup) != len(observations) or not set(associated) <= set(lookup):
        raise ValueError("Duplicate native GLRT IDs or unknown published support")
    canonical = canonical_tracks(tracks)
    graph = {oid for _, t, _ in canonical for oid in t["observation_ids"]}
    if not graph <= set(lookup):
        raise ValueError("Graph contains non-native observation IDs")
    rows = []
    for index, track, variants in canonical:
        for oid, time in zip(track["observation_ids"], track["times"], strict=True):
            obs = lookup[oid]
            if (obs["receiver"], obs["channel"]) != (track["receiver"], track["channel"]) or abs(
                obs["time_s"] - time
            ) > 1e-6:
                raise ValueError("Graph-to-native lane/time mismatch")
        remaining = [i for i, oid in enumerate(track["observation_ids"]) if oid not in associated]
        if not remaining:
            continue
        remaining.sort(key=lambda i: (track["times"][i], i))
        track_id = hashlib.sha256(
            (
                "\n".join(sorted(identities or [case]))
                + "\n"
                + "\n".join(sorted(track["observation_ids"]))
            ).encode()
        ).hexdigest()[:20]
        source_membership = piece_membership(track)
        sensitivity = {}
        for bound in (2.0, 5.0, 10.0):
            rr = runs(track, associated, bound)
            longest = max(rr, key=lambda z: (span(track, z), len(z)))
            sensitivity[f"parent_longest_{int(bound)}s_gap_fragment_span_s"] = span(track, longest)
            sensitivity[f"parent_{int(bound)}s_gap_fragments"] = len(rr)
        parent_gaps = [
            track["times"][b] - track["times"][a]
            for a, b in zip(remaining, remaining[1:], strict=False)
        ]
        for number, fragment in enumerate(runs(track, associated), 1):
            times = [track["times"][i] for i in fragment]
            ids = [track["observation_ids"][i] for i in fragment]
            native = [lookup[oid]["measured_cfo_hz"] for oid in ids]
            lifts = [track["values"][i] - y for i, y in zip(fragment, native, strict=True)]
            piece_index = (
                source_membership[fragment[0]][0] if source_membership[fragment[0]] else None
            )
            piece = track.get("pieces", [])[piece_index] if piece_index is not None else None
            errors = (
                [track["values"][i] - polynomial(piece, track["times"][i]) for i in fragment]
                if piece
                else []
            )
            rows.append(
                dict(
                    case=case,
                    track_index=index,
                    key=track["key"],
                    track_id=track_id,
                    native_graph_source_id=track.get("source_id"),
                    track_id_identity_basis=sorted(identities or [case]),
                    fragment_id=hashlib.sha256(
                        (track_id + "\n" + "\n".join(ids)).encode()
                    ).hexdigest()[:20],
                    fragment_number=number,
                    source_variants=variants,
                    source_piece_index=piece_index,
                    receiver=track["receiver"],
                    channel=track["channel"],
                    rf_hz=track["rf_hz"],
                    points=len(ids),
                    start_s=float(times[0]),
                    end_s=float(times[-1]),
                    duration_s=float(times[-1] - times[0]),
                    max_gap_s=float(
                        max((b - a for a, b in zip(times, times[1:], strict=False)), default=0)
                    ),
                    parent_points=len(track["observation_ids"]),
                    parent_residual_points=len(remaining),
                    parent_associated_points=len(track["observation_ids"]) - len(remaining),
                    parent_wholly_unassociated=len(remaining) == len(track["observation_ids"]),
                    parent_residual_span_s=span(track, remaining),
                    parent_residual_max_gap_s=float(max(parent_gaps, default=0)),
                    parent_graph_pieces=len(track.get("pieces", [])),
                    graph_quality_status=track.get("quality_status"),
                    graph_polynomial_rms_hz=track.get("residual_rms_hz"),
                    fragment_point_minus_polynomial_rms_hz=math.sqrt(
                        sum(e * e for e in errors) / len(errors)
                    )
                    if errors
                    else None,
                    alias_lift_changes=sum(
                        abs(b - a) > 1 for a, b in zip(lifts, lifts[1:], strict=False)
                    ),
                    maximum_noninteger_alias_lift_error_hz=max(
                        (abs(v - round(v / PERIOD_HZ) * PERIOD_HZ) for v in lifts), default=0
                    ),
                    ambiguous_piece_memberships=sum(
                        len(source_membership[i]) > 1 for i in fragment
                    ),
                    observation_ids=ids,
                    source_local_indices=fragment,
                    all_track_observation_ids=track["observation_ids"],
                    native_source_indices=[
                        track.get("indices", list(range(len(track["times"]))))[i] for i in fragment
                    ],
                    **sensitivity,
                )
            )
    summary = dict(
        case=case,
        total_GLRT=len(lookup),
        associated=len(associated),
        residual_GLRT=len(set(lookup) - set(associated)),
        graph_source_tracks=len(tracks),
        canonical_graph_tracks=len(canonical),
        duplicate_alias_tracks_collapsed=len(tracks) - len(canonical),
        residual_graph_unique_points=len(graph - set(associated)),
        unassociated_untracked_points=len(set(lookup) - graph - set(associated)),
        residual_fragments=len(rows),
        singleton_fragments=sum(r["points"] == 1 for r in rows),
    )
    assert sum(r["points"] for r in rows) == summary["residual_graph_unique_points"]
    return rows, summary
