"""Reduce the already authenticated DS30-0003 records to branch and support evidence."""

from collections import Counter, defaultdict

from ds30_0003_native_agreement import RATE, canonical, tag
from first30_native_agreement import LANE, match, positives


def observation_id(session, radio, counter):
    return tag(f"{session}:{radio}:{counter}".encode())


def plotted_opportunities(report, clock_sample):
    if report["policy"]["sample_rate_hz"] != RATE or report["time_basis"] != "relative sample counter":
        raise ValueError("Unexpected native plot time basis")
    rows = {}
    for row in report["points"]:
        relative = round(row["time_s"]*RATE)
        oid = observation_id(report["session_id"], row["receiver_id"], relative+clock_sample)
        if row["time_s"] != relative/RATE or oid in rows:
            raise ValueError("The plot does not uniquely recover an exact signed opportunity")
        rows[oid] = row
    return rows


def valid_owners(witness, expected):
    output = {}
    for arm, rows in witness["evidence"]["owner_rows"].items():
        owners = {oid: (norad, role) for oid, norad, role in rows}
        if (len(owners) != len(rows) or canonical({key: val[0] for key, val in owners.items()}) != expected[arm]):
            raise ValueError("The retained owner rows do not reproduce the final publication digest")
        output[arm] = owners
    if output.keys() != expected.keys():
        raise ValueError("Expected both original calibrated owner rosters")
    return output


def case_fit_audit(witness, boot, original):
    ports = witness["ports"]
    risk = ports["history_risk"]
    attempt, = risk["lean_attempts"]
    repair = attempt["repair"]
    original_points, removed = repair["rejection_counts"]["curved"]
    remaining = {arm: fit["curved_points"]-fit["compatible_curved_points"] for arm, fit in repair["finish"].items()}
    failed = {arm: fit["failed_curved"] for arm, fit in repair["finish"].items()}
    if (attempt["reason"] != "repair_original_joint_pair_gate" or risk["inference_calls"] != 1
            or repair["attempted_refits"] != 1 or len(remaining) != 2
            or len(set(remaining.values())) != 1 or len({frozenset(v) for v in failed.values()}) != 1
            or any(not set(v).isdisjoint(repair["removed_curved"]) for v in failed.values())
            or any(fit["curved_points"] != original_points-removed for fit in repair["finish"].values())):
        raise ValueError("The paid repair does not match the frozen disjoint-support accounting")
    total_removed = removed+next(iter(remaining.values()))
    ordinary_wall = original["successor"]["elapsed_s"]
    lean_wall = attempt["candidate_pre_evidence_clocks"]["elapsed_s"]
    return dict(
        selection=risk["choice"]["reason"], original_joint_failed=not attempt["pair_passes"],
        rejection=attempt["reason"], rejection_counts=repair["rejection_counts"],
        remaining_incompatible_curved=remaining, retained_incompatible_tracks=len(next(iter(failed.values()))),
        disjoint_hypothetical_loss=dict(curved_points=total_removed, original_points=original_points,
                                       max_original_points_at_5pct=original_points//20,
                                       percent=100*total_removed/original_points),
        lean=attempt["candidate_pre_evidence_clocks"], paid_ordinary=attempt["fallback_clocks"],
        lean_nested={k: v for k, v in attempt.items() if k.endswith("_clocks")
                     and k not in ("candidate_pre_evidence_clocks", "fallback_clocks")},
        published_solve=witness["timing"]["solve"][0], published_render=witness["timing"]["render"][0],
        solver_prepare=ports["history"]["prepare"][0], route_infer=ports["history"]["infer"][0],
        nomination_handoff=risk["nomination_handoff"],
        raw_acquisition=boot["phases"]["authenticated_raw_acquisition"],
        wall_ceiling=dict(upper_avoidance_s=lean_wall, hypothetical_candidate_wall_s=ordinary_wall-lean_wall,
                          speedup=original["installed"]["elapsed_s"]/(ordinary_wall-lean_wall)),
    )


def owner_support(left, right, plotted, owners):
    """Join final mixed owners to one exact same-window native peak comparison."""
    cadence = Counter()
    seen, assigned = set(), {arm: defaultdict(Counter) for arm in owners}
    visit_class = {}
    session = right["source"]["session_id"]
    for a, b in zip(left["source"]["probes"], right["source"]["probes"], strict=True):
        key = tuple(b[k] for k in LANE)
        radio = b["receiver_id"]
        if radio == 0:
            visit_class[b["visit_index"]] = "anchor" if cadence[key] % 8 == 0 else "short"
            cadence[key] += 1
        aperture = visit_class[b["visit_index"]]
        oid = observation_id(session, radio, b["valid_start_counter"])
        installed, mixed = positives(a), positives(b)
        for role, found in (("installed", installed), ("successor", mixed)):
            observed = plotted[role].get(oid)
            if len(found) != int(observed is not None) or (found and (
                observed["visit"] != b["visit_index"] or observed["channel"] != b["channel"]
                or observed["receiver_id"] != radio or observed["cfo_hz"] != found[0]["fractional_tracking_cfo_hz"]
            )):
                raise ValueError("The fast-scan report did not reproduce the exact signed raw opportunity")
        if not mixed:
            continue
        seen.add(oid)
        result, counts = match(installed, mixed)
        state = ("matched" if result else "added" if not installed else
                 "ambiguous" if counts["ambiguous_mixed_peaks"] else "changed")
        for arm, rows in owners.items():
            if oid in rows:
                assigned[arm][aperture][f"{state}_{rows[oid][1]}"] += 1
    return {
        arm: dict(unjoinable=len(set(owners[arm])-seen), strata={a: dict(x) for a, x in rows.items()})
        for arm, rows in assigned.items()
    }
