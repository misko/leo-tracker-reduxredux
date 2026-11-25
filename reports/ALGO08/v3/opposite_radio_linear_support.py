"""Census opposite-radio linear eligibility on the original mixed-packet tapes."""

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import argparse
import json

from deferred_family_held_support import native_opportunities
from mixed_owner_support_0220 import GATE_PIN
from pre_screen_owner_readout import ARMS, CASES, HERE, RELEASE, SOURCES, checked, document, owner_map, signature


MIN_LINEAR_POINTS = 6


def receiver_bank(lane):
    rx, channel = lane
    return rx, int(channel > 4)


def census(opportunities, masks, graph=None):
    first = masks["first"]["tracks"]
    second = masks["after_salvage"]["tracks"]
    families = defaultdict(list)
    supported, curved = set(), set()
    for mask in (first, second):
        for row in mask:
            curved.update(row["observation_ids"])
    for row in second:
        ids = row["observation_ids"]
        lanes = {tuple(opportunities[oid]["lane"]) for oid in ids}
        if len(lanes) != 1 or not all(opportunities[oid]["positive"] for oid in ids):
            raise ValueError("Curved rows do not bind a single signed physical lane")
        (lane,) = lanes
        families[row["norad"]].append((row, lane[0]))
        if row["compatible"]:
            supported.add(receiver_bank(lane))
    surviving = {n for n, entries in families.items() if any(r["compatible"] for r, _ in entries)}
    eligible = {}
    for norad, entries in sorted(families.items()):
        radios = {rx for _, rx in entries}
        if norad in surviving or len(radios) != 1:
            continue
        (radio,) = radios
        ids = [oid for r, _ in entries for oid in r["observation_ids"]]
        counters = [opportunities[oid]["start"] for oid in ids]
        eligible[norad] = dict(seed_radio=radio, curved_points=len(ids), seed_span=[min(counters), max(counters)],
                               components=[r["component"] for r, _ in entries])
    positive = {oid: row for oid, row in opportunities.items() if row["positive"]}
    free = {oid: row for oid, row in positive.items() if oid not in curved and receiver_bank(row["lane"]) in supported}
    graph_seen = {}
    if graph is not None:
        for track in graph:
            ids = track["observation_ids"]
            if len(ids) != len(set(ids)) or graph_seen.keys() & set(ids) or not set(ids) <= positive.keys():
                raise ValueError("Graph row IDs do not bind disjoint signed positives")
            for oid in ids:
                graph_seen[oid] = track["key"]
    for value in eligible.values():
        radio = value["seed_radio"]
        lanes = Counter((*row["lane"], row["rf"]) for row in free.values() if row["lane"][0] != radio)
        value.update(opposite_positive_rows=sum(lanes.values()),
                     opposite_possible_components=sum(n // MIN_LINEAR_POINTS for n in lanes.values()),
                     opposite_rows_by_lane=[[*lane, n] for lane, n in sorted(lanes.items())])
        if graph is None:
            continue
        value["eligible_linear_components"] = [t["key"] for t in graph
                                               if not t["curved"] and t["receiver"] != radio
                                               and len(t["observation_ids"]) >= MIN_LINEAR_POINTS
                                               and set(t["observation_ids"]) <= free.keys()]
    return dict(families=eligible, surviving_families=sorted(surviving),
                supported_banks=sorted(supported), curved_tape_ids=sorted(curved),
                opportunities=positive, graph=graph)


def exact_graph(native):
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    for logical, pin in SOURCES.items():
        checked(RELEASE / logical, pin)
    config = document(RELEASE / "assets/tracks.json", SOURCES["assets/tracks.json"])["config"]
    prepared = prepare_tracks(native, TrackConfig(**config))
    curved = set(prepared["curved_indices"])
    return [dict(key=t["key"], receiver=t["receiver"], observation_ids=list(t["observation_ids"]), curved=i in curved)
            for i, t in enumerate(prepared["tracks"])]


def predict(native_paths, rebuild_graph):
    gate = document(HERE / "measurements/second-curve-gate.json.gz", GATE_PIN)
    result = {}
    for (case, pins), path in zip(CASES.items(), native_paths, strict=True):
        native = document(path, pins["native"])
        tape = gate[case]
        if tape["stage"]["native_sha256"] != "sha256:" + pins["native"] or tape["clock"]["exit"]:
            raise ValueError("Tape is detached from the original signed packet")
        graph = exact_graph(native) if rebuild_graph else None
        result[case] = census(native_opportunities(native), tape["masks"], graph)
        result[case].update(native_sha256=pins["native"], candidate_tape_sha256=tape["stage"]["masks"]["after_salvage"])
    return dict(cases=result, gate_sha256=GATE_PIN, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def grade(candidate, installed, charted):
    graph = candidate["graph"]
    track_by_id = {} if graph is None else {oid: t for t in graph for oid in t["observation_ids"]}
    rows = []
    for oid, (family, role) in sorted(installed.items()):
        if role != "predictive" or oid in charted:
            continue
        target = candidate["families"].get(str(family))
        point = candidate["opportunities"].get(oid)
        track = track_by_id.get(oid)
        opposite = None if target is None or point is None else point["lane"][0] != target["seed_radio"]
        rows.append(dict(id=oid, family=family, point=point, eliminated_seed_radio=None if target is None else target["seed_radio"],
                         opposite_radio=opposite, track=None if track is None else track["key"],
                         exact_eligible=None if graph is None else bool(target and track and
                                      track["key"] in target["eligible_linear_components"])))
    return dict(rows=rows, opposite_radio=sum(row["opposite_radio"] is True for row in rows))


def score(plan, pin, witnesses):
    prediction = document(plan, pin)
    if prediction["gate_sha256"] != GATE_PIN or prediction["source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Seal did not bind this selection algorithm")
    result = {}
    for (case, pins), path in zip(CASES.items(), witnesses, strict=True):
        evidence = document(path, pins["charted"])["evidence"]
        crossover = document(HERE / f"measurements/field-receiver-solver-cross-{case[-4:]}.json.gz", pins["crossover"])
        candidate = prediction["cases"][case]
        mixed = "sha256:" + pins["native"]
        if (candidate["native_sha256"] != pins["native"] or evidence["detail"]["input_sha256"] != mixed
                or crossover["admission"]["native_sha256"] != mixed
                or crossover["score"]["named_mixed"]["region"] != evidence["detail"]["region"]):
            raise ValueError("Reference owners do not bind the same signed mixed packet and offer")
        named = crossover["score"]
        if named["new_owners"] != crossover["worker"]["ordered_owners"] or crossover["clock"]["exit_code"]:
            raise ValueError("Saved crossover ownership is unqualified")
        result[case] = dict(families=candidate["families"], surviving_families=len(candidate["surviving_families"]),
                            graph_table_available=candidate["graph"] is not None,
                            opportunity_table_sha256=signature(candidate["opportunities"]),
                            candidate_tape_sha256=candidate["candidate_tape_sha256"],
                            arms={arm: grade(candidate, owner_map(named["new_owners"][arm], named["new_owner_maps"][arm]),
                                             owner_map(evidence["owner_rows"][arm], evidence["owner_maps"][arm])) for arm in ARMS})
    return dict(cases=result, plan_sha256=pin, gate_sha256=GATE_PIN, source_sha256=prediction["source_sha256"],
                tracks_forecast=0, orbit_reads=0, location_solves=0, waveform_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare = commands.add_parser("predict")
    prepare.add_argument("native", nargs=2, type=Path, metavar=("MIXED_0220", "MIXED_0086"))
    prepare.add_argument("--released-graph", action="store_true", help="Requires a normally admitted idle Gauss lease")
    assess = commands.add_parser("score")
    assess.add_argument("plan", type=Path)
    assess.add_argument("pin")
    assess.add_argument("witnesses", nargs=2, type=Path, metavar=("CHARTED_0220", "CHARTED_0086"))
    args = parser.parse_args()
    result = predict(args.native, args.released_graph) if args.mode == "predict" else score(args.plan, args.pin, args.witnesses)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
