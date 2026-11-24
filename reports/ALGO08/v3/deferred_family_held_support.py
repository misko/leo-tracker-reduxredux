"""Count physically separated opportunities without substituting full-packet fitted state."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from os import fsdecode
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
CASE = "DS30-0220"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
NOMINATION = (Path("/srv/postgres-nvme/leo-ds30-research-worktrees/deferred-family-nomination")
              / "reports/ALGO08/v3/measurements/deferred-family-nomination-prediction.json")
PINS = {
    "nomination": "641b140d42c552c9cfa1e54104b303085735d8709388d8645b291843d90a33de",
    "custodian": "6eb9e46220096e695eaddfb5b4b0a673d8a28d13035e7caf8a26b9fc5f7df995",
    "prior_graph": "1c9f656916353ff01037e495312ee410cb71e079147350b9934b51c7ac7e67e2",
    "charted": "b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
}
ARMS = ("c0", "fitted_c")
MIN_CONTIGUOUS = 12
LEAKAGE_SOURCE_PINS = {
    "event_position.py": "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f",
    "scan.py": "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89",
    "family_weighting.py": "ff20661e8685e49089ba716eb60f05f3596f94c7303e8cc2b90e40dc630a8f31",
    "position.py": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
    "predictive_linear.py": "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
}


def signature(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def checked(path, pin):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed publication evidence changed at {path}")
    return raw


def document(path, pin):
    raw = checked(path, pin)
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def deny_raw_and_orbital(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = fsdecode(args[0])
        if path.startswith(("/srv/bulk/", "/mnt/qnap01/")) or path.endswith((".tle", ".ci16", ".ci16.zst")):
            raise ValueError("Held-opportunity audit only reads signed detector and source metadata")


def time_separated(start, aperture, train_intervals, guard):
    """Compare closed hardware counter intervals, including both apertures."""
    return all(start + aperture < first - guard or start > last + aperture + guard
               for first, last in train_intervals)


def split_runs(ids, opportunities, allowed, max_gap):
    runs, current = [], []
    for oid in ids:
        if current and (oid not in allowed or opportunities[oid]["start"] - opportunities[current[-1]]["start"] > max_gap):
            runs.append(current)
            current = []
        if oid in allowed:
            current.append(oid)
    if current:
        runs.append(current)
    return runs


def native_opportunities(native):
    source = native["source"]
    radios = {value: i + 1 for i, value in enumerate(sorted({row["receiver_id"] for row in source["probes"]}))}
    rows = {}
    for probe in source["probes"]:
        receiver, start = probe["receiver_id"], probe["valid_start_counter"]
        oid = "sha256:" + sha256(f'{source["session_id"]}:{receiver}:{start}'.encode()).hexdigest()
        if oid in rows:
            raise ValueError("Signed detector opportunity duplicates its hardware identity")
        rows[oid] = dict(start=start, lane=(radios[receiver], probe["channel"]), rf=probe["actual_rf_hz"],
                         positive=any(c["passed_fractional_margin_gate"] is True for c in probe["candidates"]))
    return rows


def original_candidate_roster(risk, target):
    """Return recorded full-packet selections and shortlists, never extrapolated eligibility."""
    attempt, = risk["lean_attempts"]
    norad = target[1]
    finalists = risk["two_centre_rank"]["finalist_signatures"]
    elected = finalists[attempt["cold"]["branch"] - 1]
    chosen = {key: [index, n, alias] for key, index, n, alias in elected}
    suggested = {}
    for branch, items in enumerate(finalists, 1):
        for name, index, n, alias in items:
            if (index, n) == target:
                suggested.setdefault(name, []).append([branch, alias])
    shortlist = {row["component"]: row["candidate_indices"] for row in attempt["salvage_shortlists"]}
    support = attempt["support"]
    fine = {row["component"]: [proposal for proposal in row["alternatives"]
                               if (proposal["candidate_index"], proposal["norad"]) == target]
            for row in support["salvage"]}
    linear = {label[0]: label[2] for label in support["predictive_labels"] if label[1] == norad}
    selected = {row["component"]: row["selected"] for row in support["salvage"] if row["selected"] is not None}
    return chosen, suggested, shortlist, fine, linear, selected


def preserved_owners(evidence):
    books = {}
    for arm in ARMS:
        rows = evidence["owner_rows"][arm]
        owned = {oid: (norad, role) for oid, norad, role in rows}
        if len(owned) != len(rows) or signature({oid: norad for oid, (norad, _) in owned.items()}) != evidence["owner_maps"][arm]:
            raise ValueError("Original publication owner digest changed")
        books[arm] = owned
    return books


def cohort(opportunities, tracks, allowed, max_gap, min_span, prior, target, owners, tape):
    chosen, suggested, shortlist, fine, linear, selected = prior
    reachable, all_graph = [], set()
    for track in tracks:
        name, ids = track["key"], track["observation_ids"]
        all_graph.update(ids)
        for run in split_runs(ids, opportunities, allowed, max_gap):
            start, end = (opportunities[oid]["start"] for oid in (run[0], run[-1]))
            ordinary = chosen.get(name)
            actual_fine_overlap = []
            for suggestion in fine.get(name, ()):
                matches = len(set(run).intersection(ids[suggestion["start_index"]:suggestion["stop_index"]]))
                if matches:
                    actual_fine_overlap.append(dict(active_overlap=matches, alias=suggestion["alias"],
                                                    start_index=suggestion["start_index"], stop_index=suggestion["stop_index"]))
            stage = tape.get(name)
            recovered = selected.get(name)
            reachable.append(dict(component=name, lane=opportunities[run[0]]["lane"], rf_hz=opportunities[run[0]]["rf"],
                                  points=len(run), first_counter=start, last_counter=end,
                                  contiguous_candidate_scope=len(run) >= MIN_CONTIGUOUS and end-start >= min_span,
                                  target_elected=ordinary is not None and tuple(ordinary[:2]) == target,
                                  target_finalists=suggested.get(name, []), target_coarse_salvage=target[0] in shortlist.get(name, []),
                                  target_fine_overlap=actual_fine_overlap, target_predictive=name in linear,
                                  original_cold_assignment=ordinary, original_coarse_candidate_count=len(shortlist.get(name, ())),
                                  original_salvage_assignment=None if recovered is None else
                                      [recovered[key] for key in ("candidate_index", "norad", "alias", "points")],
                                  original_second_tape_overlap=0 if stage is None else
                                      len(set(run).intersection(stage["observation_ids"])),
                                  original_second_tape_pass=None if stage is None else stage["compatible"],
                                  ordinary_owner_roles={arm: dict(Counter(owners[arm][oid][1] for oid in run if oid in owners[arm]))
                                                        for arm in ARMS},
                                  observation_digest=signature(run)))
    positives = {oid for oid in allowed if opportunities[oid]["positive"]}
    if not allowed.intersection(all_graph) <= positives:
        raise ValueError("An original Graph track contains an ungated detector row")
    candidates = [row for row in reachable if row["contiguous_candidate_scope"]]
    return dict(opportunities=len(allowed), detected=len(positives), nondetections=len(allowed-positives),
                graph_observations=len(allowed & all_graph), detections_without_graph=len(positives-all_graph),
                segments=len(reachable), candidate_segments=len(candidates),
                support_in_candidate_segments=sum(row["points"] for row in candidates),
                short_segment_observations=sum(row["points"] for row in reachable if not row["contiguous_candidate_scope"]),
                observed_in_ordinary_terminal={arm: dict(Counter(owners[arm][oid][1] for oid in positives if oid in owners[arm]))
                                               for arm in ARMS},
                target_observed_in_ordinary_terminal={arm: sum(owners[arm][oid][0] == target[1]
                        for oid in positives if oid in owners[arm]) for arm in ARMS},
                target_candidate_segments={key: sum(bool(row[key]) for row in candidates) for key in (
                    "target_elected", "target_finalists", "target_coarse_salvage", "target_fine_overlap", "target_predictive")},
                rows=reachable)


def run():
    prior_graph = document(HERE / "measurements/pre-screen-owner.json.gz", PINS["prior_graph"])
    for logical, pin in prior_graph["source_sha256"].items():
        checked(RELEASE / logical, pin)
    for name, pin in LEAKAGE_SOURCE_PINS.items():
        checked(RELEASE / "src/leo/analysis/localization_v3" / name, pin)
    config = document(RELEASE / "assets/tracks.json", prior_graph["source_sha256"]["assets/tracks.json"])["config"]
    nomination = document(NOMINATION, PINS["nomination"])["rows"][CASE]
    selected = nomination["outcome"]["deferred"]
    selected_train = [*selected["survivors"], selected["peer"]]
    target = selected["peer"]["candidate_index"], selected["peer"]["norad"]
    if {(row["candidate_index"], row["norad"]) for row in selected_train} != {target}:
        raise ValueError("Deferred members do not share the nominated family")
    custody = document(HERE / "measurements/second-curve-gate.json.gz", PINS["custodian"])[CASE]
    root = CAMPAIGN / CASE / "successor/attempt-000001/publication"
    witness = document(root / "exact-named-raw-witness.json", PINS["charted"])
    native_path, = root.glob("fast-scan-automatic-work/*/detections.json")
    native_sha = nomination["native_sha256"]
    if (native_sha != custody["stage"]["native_sha256"] or native_sha != witness["evidence"]["detail"]["input_sha256"]
            or custody["ready"]["compatible_solver_sources"] != witness["source_sha256"]):
        raise ValueError("The held opportunity census must use the original charted packet and policy")
    native = document(native_path, native_sha)
    opportunities = native_opportunities(native)
    source = native["source"]
    rate = source["sample_rate_hz"]
    aperture = (rate * source["probe_ms"] + 999) // 1000
    graph_gap = round(rate * config["max_gap_s"])
    min_span = round(rate * config["min_span_s"])
    sys.path.insert(0, str(RELEASE / "src"))
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    graph = prepare_tracks(native, TrackConfig(**config))
    tracks = graph["tracks"]
    by_component = {row["key"]: row["observation_ids"] for row in tracks}
    if (len(by_component) != prior_graph["judged"][CASE]["graph_components"]
            or {row["observation_id"] for row in graph["observations"]} != {k for k,v in opportunities.items() if v["positive"]}):
        raise ValueError("Released Graph did not reproduce the original signed support")
    tape = {row["component"]: row for row in custody["masks"]["after_salvage"]["tracks"]}
    for name, row in tape.items():
        members = set(row["observation_ids"])
        if [oid for oid in by_component[name] if oid in members] != row["observation_ids"]:
            raise ValueError("Recomputed Graph changed the original second-stage members or order")
    intervals, training, lanes = [], set(), set()
    for row in selected_train:
        name, ids = row["component"], row["observation_ids"]
        if tape[name]["observation_ids"] != ids or training.intersection(ids):
            raise ValueError("Selected training scope is ambiguous")
        lane, = {opportunities[oid]["lane"] for oid in ids}
        if list(lane) != row["lane"]:
            raise ValueError("Selected training lane differs from signed acquisition")
        training.update(ids)
        lanes.add(lane)
        intervals.append([opportunities[ids[0]]["start"], opportunities[ids[-1]]["start"]])
    train_receiver, = {lane[0] for lane in lanes}
    allowed = {oid for oid, row in opportunities.items() if oid not in training and
               time_separated(row["start"], aperture, intervals, graph_gap)}
    other_radio = {oid for oid in allowed if opportunities[oid]["lane"][0] != train_receiver}
    same_lane_cohort = {oid for oid in allowed if opportunities[oid]["lane"] in lanes}
    prior = original_candidate_roster(witness["ports"]["history_risk"], target)
    owners = preserved_owners(witness["evidence"])
    common = (graph_gap, min_span, prior, target, owners, tape)
    return dict(case=CASE, pins=PINS, exact_packet_sha256=native_sha, target_family_from_nomination=target,
                offered_region=witness["evidence"]["detail"]["region"], causal_archive_sha256=custody["ready"]["archive_sha256"],
                training_observations=len(training), training_intervals_counter=intervals,
                training_lanes=sorted(lanes), original_graph_components=len(tracks), original_graph_points=graph["graph_points"],
                max_aperture_counter=aperture, graph_gap_counter=graph_gap, clock_rate_hz=rate,
                other_radio=cohort(opportunities, tracks, other_radio, *common),
                separated_same_lanes=cohort(opportunities, tracks, same_lane_cohort, *common),
                shared_training_observations=len(training & (other_radio | same_lane_cohort)),
                audited_leakage_sources=LEAKAGE_SOURCE_PINS,
                authenticated_train_only_forecast_available=False,
                authenticated_held_visibility_available=False, scored_held_cfo=False,
                disposition="no_independent_family_evidence", waveform_reads=0, orbital_reads=0, solver_calls=0)


if __name__ == "__main__":
    sys.addaudithook(deny_raw_and_orbital)
    print(json.dumps(run(), sort_keys=True, indent=2, allow_nan=False))
