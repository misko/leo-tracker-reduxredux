"""Compare authenticated detector factors and distinguish equivalent peak ties."""

from collections import Counter

from ..__main__ import encoded
from ..scoring import distribution
from . import accelerated_command_parity as original
from .accelerated_command_results import partial_parity


def circular_hz(left, right):
    return (left - right + original.ALIAS / 2) % original.ALIAS - original.ALIAS / 2


def peak_axes(candidate):
    return (
        candidate["integer_epoch_sample"],
        candidate["fractional_epoch_offset_samples"] or 0.0,
        candidate["fractional_tracking_cfo_hz"],
    )


def peak_delta(left, right):
    epoch, offset, cfo = left
    other_epoch, other_offset, other_cfo = right
    return (
        (epoch - other_epoch) + (offset - other_offset),
        None if cfo is None or other_cfo is None else circular_hz(cfo, other_cfo),
    )


def peak_neighbours(left, right):
    edges = []
    for i, x in enumerate(left):
        for j, y in enumerate(right):
            dt, df = peak_delta(x, y)
            if abs(dt) <= original.EPOCH_TOLERANCE_SAMPLES and (
                (df is None and x[2] == y[2])
                or (df is not None and abs(df) <= original.CFO_TOLERANCE_HZ)
            ):
                edges.append((i, j))
    return edges


def compare(native, visits, archived):
    """Return complete native parity or parity on authenticated closed visits."""
    clocks = archived["delivery_clocks"]
    indices = [r["visit"] for r in visits]
    if indices != sorted(set(indices)) or any(not 0 <= index < len(clocks) for index in indices):
        raise ValueError("closed visits must have unique, ascending signed indices")
    probes = [p for r in visits for p in r["probes"]]
    exclusions = [
        {k: r[k] for k in ("visit", "reason", "iq_sha256", "sample_start", "sample_end")}
        for r in visits
        if r["status"] == "invalid_capture"
    ]
    if native is None:
        proof, changes = partial_parity(visits, archived)
    else:
        if (
            indices != list(range(len(clocks)))
            or encoded(probes) != encoded(native["source"]["probes"])
            or encoded(exclusions) != encoded(native["provenance"]["excluded_windows"])
            or [r["delivery_clock"] for r in visits] != native["delivery_clocks"]
            or [r["clock_anchor"] for r in visits if r["clock_anchor"] is not None]
            != [native["clock_anchor"]]
            or visits[-1]["sample_end"] != native["last_sample_counter"]
        ):
            raise ValueError("native compact handoff differs from its authenticated visit ledger")
        proof, changes = original.compare(native, archived)
        proof.update(
            coverage="complete_native",
            compared_visits=len(indices),
            archived_total_visits=len(clocks),
            proof_scope=dict(
                archived_analysis_manifest_sha256=archived["source"]["analysis_manifest_sha256"],
                fresh_analysis_manifest_sha256=native["source"]["analysis_manifest_sha256"],
                all_provenance_fields_changed=original.differs(
                    native["provenance"], archived["provenance"]
                ),
                all_document_fields_changed=original.differs(native, archived),
            ),
        )
    selected = set(indices)
    archived_exclusions = [
        r for r in archived["provenance"]["excluded_windows"] if r["visit"] in selected
    ]
    proof.update(
        fresh_exclusions=exclusions,
        archived_exclusions_in_coverage=archived_exclusions,
        exclusion_rows_match=encoded(exclusions) == encoded(archived_exclusions),
        delivery_clock_mismatches=[
            r["visit"] for r in visits if r["delivery_clock"] != clocks[r["visit"]]
        ],
        unexpected_anchor_visits=[
            r["visit"] for r in visits if r["visit"] and r["clock_anchor"] is not None
        ],
        first_clock_anchor_matches=(
            visits[0]["clock_anchor"] == archived["clock_anchor"] if indices[:1] == [0] else None
        ),
    )
    return add_peak_details(probes, archived["source"]["probes"], proof, changes)


def add_peak_details(probes, archived, proof, changes):
    """Keep alternate admissible matches and aliased deltas beside exact differences."""
    old = {original.key(p): p for p in archived}
    changed = {c["probe"]: c for c in changes}
    ambiguous, deltas, found = [], {"epoch_samples": [], "circular_cfo_hz": []}, Counter()
    for probe in probes:
        key = original.key(probe)
        if key not in old:
            continue
        other = old[key]
        x, y = (list(map(peak_axes, p["candidates"])) for p in (probe, other))
        edges = peak_neighbours(x, y)
        n_left, n_right = (Counter(edge[i] for edge in edges) for i in (0, 1))
        alternatives = [edge for edge in edges if n_left[edge[0]] > 1 or n_right[edge[1]] > 1]
        if alternatives:
            ambiguous.append(
                dict(probe=key, equivalent_indices=alternatives, exact_probe=key not in changed)
            )
        detail = changed.get(key)
        pairs = detail["matched_physical_indices"] if detail else list(enumerate(range(len(x))))
        if detail:
            detail["matched_peak_axes"] = []
            detail["equivalent_peak_indices"] = alternatives
            matched_left, matched_right = ({pair[i] for pair in pairs} for i in (0, 1))
            detail["unmatched_portable_candidates"] = [
                c for i, c in enumerate(probe["candidates"]) if i not in matched_left
            ]
            detail["unmatched_archived_candidates"] = [
                c for j, c in enumerate(other["candidates"]) if j not in matched_right
            ]
        for i, j in pairs:
            dt, df = peak_delta(x[i], y[j])
            if detail:
                left, right = probe["candidates"][i], other["candidates"][j]
                detail["matched_peak_axes"].append(
                    dict(
                        pair=(i, j),
                        epoch_samples=dt,
                        circular_cfo_hz=df,
                        exact_fields_changed=original.differs(left, right),
                    )
                )
            deltas["epoch_samples"].append(abs(dt))
            if df is not None:
                deltas["circular_cfo_hz"].append(abs(df))
            if i != j:
                found["rank_moves_with_ambiguous_counterpart"] += (i, j) in alternatives
            found["matches_on_tolerance_rounding_boundary"] += (i, j) not in edges
    proof["physical_neighbourhood"] = dict(
        ambiguous_probes=len(ambiguous),
        ambiguous_changed_probes=sum(not row["exact_probe"] for row in ambiguous),
        rank_moves_with_ambiguous_counterpart=found["rank_moves_with_ambiguous_counterpart"],
        matches_on_tolerance_rounding_boundary=found["matches_on_tolerance_rounding_boundary"],
        matched_absolute_error={key: distribution(values) for key, values in deltas.items()},
    )
    return proof, changes, ambiguous
