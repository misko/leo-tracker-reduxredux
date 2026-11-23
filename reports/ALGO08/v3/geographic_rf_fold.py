"""Audit one fixed reciprocal RF-channel rule on the original regional score lattice."""

import argparse
from collections import Counter, defaultdict
import gzip
import json
from math import isfinite
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import BENCH, RELEASE, archive_identity, machine, read, write
from india_saved_transfer import HERE, MODES as INDIA_OFFERS, STAGED, bind, digest
from mixture_trial import elapsed


SITES = ("india", "north", "south")
RECEIVERS = (1, 2)
SCORE_SOURCE = "6e7ae57a5762be3028756e3033c070de587c461707dda059692aee5d7c717b96"
CONTROL = HERE.parent / "single-core-2x/measurements"
OLD = {"regional-reassignment.json.gz": "735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a",
       "region-mirrors.json.gz": "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728"}
INDIA = HERE / "measurements/india-regional-diagnostic.json.gz"
INDIA_PIN = "3879605a5b35d2bbb9e714cb9bd5ce1f40cb28d43ec6443ff6772879e3641913"
PAIR_PINS = dict(north="9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb",
                 south="48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0")
EVIDENCE = ("points", "catalogue_orbits", "potentially_visible_orbits", "track_count", "graph_points",
            "original_points", "receiver_points", "snapshots")


def checked_bytes(path, pin):
    payload = path.read_bytes()
    if digest(payload) != pin:
        raise ValueError(f"Archived development input changed: {path.name}")
    return payload


def previous_inputs(site):
    from leo.contracts.digests import canonical_digest

    if site == "india":
        old = json.loads(gzip.decompress(checked_bytes(INDIA, INDIA_PIN)))["runs"]
        native, archive, _, original, verify = bind(STAGED, "matched-tile")
        offers = {}
        for name in INDIA_OFFERS:
            released = old[name]["stock"]
            identity = released["identity"]
            if any(identity[key] != original[key] for key in ("document_sha256", "history_sha256", "requests_sha256")):
                raise ValueError("India offers do not share the original waveform and archive")
            offers[name] = dict(released["full_diagnostic"], offer=identity["offer"])
        return native, archive, offers, verify, original["document_sha256"]

    prior = {file: json.loads(gzip.decompress(checked_bytes(CONTROL / file, pin))) for file, pin in OLD.items()}
    offers = prior["region-mirrors.json.gz"]["sites"][site]
    contained = prior["regional-reassignment.json.gz"][f"{site}-edge"]
    if any(offers["inside"][key] != contained[key] for key in (*EVIDENCE, "offer", "native_sha256")):
        raise ValueError("Mirrored containing offer differs from its original edge probe")
    if offers["outside"]["native_sha256"] != contained["native_sha256"]:
        raise ValueError("The two mirrored offers must share one waveform")
    public_pair = BENCH / f"exact-curved-lookahead-{site}-inside"
    pair = json.loads(checked_bytes(public_pair / "pair.json", PAIR_PINS[site]))
    archived = pair["runs"]["baseline"]
    work = public_pair / "baseline/fast-scan-automatic-work"
    path, = work.glob("*/detections.json")
    native = json.loads(checked_bytes(path, contained["native_sha256"]))
    terminal = read(work / archived["receipt"]["run_id"] / "terminal.json")
    if (terminal["native_sha256"] != canonical_digest(native)
            or canonical_digest(terminal) != archived["receipt"]["terminal_sha256"]
            or native["source"]["raw_recording_authority_digest"] != archived["raw_authority"]):
        raise ValueError("Original published detector provenance changed")
    archive = Path(pair["archive"]["root"])

    def verify():
        if archive_identity(archive) != pair["archive"]:
            raise ValueError("Matched public causal archive changed")

    verify()
    return native, archive, offers, verify, contained["native_sha256"]


def probe_terms(kernel, graph, catalogue, region):
    score_track = kernel.score_track
    observed = []

    def capture(*args, **kwargs):
        result = score_track(*args, **kwargs)
        observed.append(result)
        return result

    with patch.object(kernel, "score_track", capture):
        complete = kernel.evaluate(graph, catalogue, region)
    tracks, points = graph["tracks"], complete["points"]
    if len(points) != 96 or len(observed) != len(tracks) * len(points):
        raise ValueError("Expected every Graph track at every original probe")
    scores = []
    for i, point in enumerate(points):
        current = observed[i*len(tracks):(i+1)*len(tracks)]
        if {t["key"]: owner for t, (_, owner) in zip(tracks, current, strict=True)} != point["owners"]:
            raise ValueError("Recorded track order differs from regional scoring")
        scores.append([value for value, _ in current])
    return complete, scores


def channel_split(graph):
    rows = graph["observations"]
    channels = sorted({row["channel"] for row in rows})
    fold_by_channel = {channel: i % 2 for i, channel in enumerate(channels)}
    observations = Counter((fold_by_channel[row["channel"]], row["receiver"]) for row in rows)
    tracks = Counter((fold_by_channel[row["channel"]], row["receiver"]) for row in graph["tracks"])
    counts = {str(fold): {str(rx): dict(observations=observations[fold, rx], tracks=tracks[fold, rx]) for rx in RECEIVERS}
              for fold in (0, 1)}
    return fold_by_channel, counts


def nominate(points, values, side):
    ranks = sorted((i for i, p in enumerate(points) if p["side"] == side), key=lambda i: values[i], reverse=True)
    if len(ranks) != 48 or not all(isfinite(values[i]) for i in ranks):
        raise ValueError("Expected a finite original 48-point side")
    first, second, *_ = ranks
    return first, values[first] - values[second]


def crosscheck(graph, points, terms):
    folds, counts = channel_split(graph)
    if any(not all(c.values()) for receiver in counts.values() for c in receiver.values()):
        return dict(verdict="abstain_empty", fold_by_channel=folds, coverage=counts, directions=[])
    tracks = graph["tracks"]
    if len(points) != 96 or any(len(row) != len(tracks) for row in terms) or len(terms) != 96:
        raise ValueError("Fold audit needs original track terms for all 96 probes")
    split_scores = []
    for scores in terms:
        sums = defaultdict(float)
        for track, value in zip(tracks, scores, strict=True):
            sums[folds[track["channel"]], track["receiver"]] += value
        split_scores.append(sums)

    outcomes = []
    for train, held in ((0, 1), (1, 0)):
        n = sum(counts[str(train)][str(rx)]["observations"] for rx in RECEIVERS)
        training = [sum(s[train, rx] for rx in RECEIVERS) / n for s in split_scores]
        inside, inside_gap = nominate(points, training, "inside")
        outside, outside_gap = nominate(points, training, "exterior")
        trial = dict(train=train, held=held, training_gap=dict(inside=inside_gap, exterior=outside_gap))
        outcomes.append(trial)
        if inside_gap == 0 or outside_gap == 0:
            trial["verdict"] = "abstain_tie"
            continue
        trial.update(inside=dict(index=inside, xy_km=points[inside]["xy_km"], train_score=training[inside]),
                     exterior=dict(index=outside, xy_km=points[outside]["xy_km"], train_score=training[outside]))
        gains = {str(rx): (split_scores[outside][held, rx] - split_scores[inside][held, rx])
                 / counts[str(held)][str(rx)]["observations"] for rx in RECEIVERS}
        owner_overlap = {}
        for side, idx in (("inside", inside), ("exterior", outside)):
            sat = [set(points[idx]["owners"][track["key"]] for track in tracks if folds[track["channel"]] == fold) - {None}
                   for fold in (0, 1)]
            owner_overlap[side] = dict(fold_sizes=list(map(len, sat)), both=sorted(sat[0] & sat[1]))
        trial.update(held_gain=gains, satellite_overlap=owner_overlap,
                     verdict="positive" if all(isfinite(gain) and gain > 0 for gain in gains.values()) else "nonpositive")
    verdicts = [row["verdict"] for row in outcomes]
    decision = ("possible_withhold" if all(v == "positive" for v in verdicts) else
                "abstain_tie" if "abstain_tie" in verdicts else "keep")
    return dict(verdict=decision, fold_by_channel=folds, coverage=counts, directions=outcomes)


def run(site, output):
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared Gauss slot")
    if digest(Path(kernel.__file__).read_bytes()) != SCORE_SOURCE:
        raise ValueError("Original regional scorer changed")
    native, archive, offers, verify, native_sha256 = previous_inputs(site)
    track_config = checked_bytes(RELEASE / "assets/tracks.json", "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a")
    start = process_time(), perf_counter()
    graph = prepare_tracks(native, TrackConfig(**json.loads(track_config)["config"]))
    graph_clock = elapsed(*start)
    start = process_time(), perf_counter()
    catalogue = causal_catalogue(TleArchiveReader(archive), graph["metadata"]["causal_cutoff_utc_ns"], element_parser=ElementParser())
    catalogue_clock = elapsed(*start)
    snapshots = sorted({row["snapshot_digest"] for row in catalogue.provenance})
    data = {}
    for name, original in offers.items():
        offer = original["offer"]
        region = SearchRegion(tuple(offer["center"]), width_km=offer["width_km"])
        start = process_time(), perf_counter()
        full, terms = probe_terms(kernel, graph, catalogue.catalogue, region)
        probe_clocks = elapsed(*start)
        full.update(snapshots=snapshots)
        measured = json.loads(json.dumps(full, allow_nan=False))
        changed = [key for key in EVIDENCE if measured[key] != original[key]]
        if changed:
            raise ValueError(f"Original all-channel probe evidence did not match on {name}: {changed}")
        start = process_time(), perf_counter()
        folded = crosscheck(graph, full["points"], terms)
        fold_clocks = elapsed(*start)
        data[name] = dict(offer=offer, diagnostic=folded, all_channel=kernel.summarize(full["points"]),
                          full_score_sha256=canonical_digest(measured), complete_score_match=True,
                          term_order=[{k: track[k] for k in ("key", "receiver", "channel", "rf_hz")} for track in graph["tracks"]],
                          terms=terms, points=full["points"], probe_clocks=probe_clocks, fold_clocks=fold_clocks)
    verify()
    sources = {name: digest((HERE / name).read_bytes()) for name in
               ("geographic_rf_fold.py", "geographic-rf-fold-protocol.md")}
    write(output, dict(site=site, native_sha256=native_sha256, catalogue_members=len(catalogue.catalogue.satellites),
                       graph_clocks=graph_clock, catalogue_clocks=catalogue_clock, host=host, sources=sources, offers=data))


def score(directory, summary, full):
    paths = {site: directory / f"{site}.json" for site in SITES}
    sealed = {site: read(path) for site, path in paths.items()}
    cards, tally = {}, Counter()
    for site, result in sealed.items():
        expected = set(INDIA_OFFERS) if site == "india" else {"inside", "outside"}
        if result["site"] != site or set(result["offers"]) != expected:
            raise ValueError("Expected exactly the two published offers at each development site")
        scores = {}
        for name, row in result["offers"].items():
            if not row["complete_score_match"]:
                raise ValueError("Fold rule requires exact original score reconstruction")
            contains = name in ("matched-tile", "inside")
            diagnostic = row["diagnostic"]
            old = row["all_channel"]
            bilateral = all(v["gain"] > 0 for v in old["receivers"].values())
            decision = diagnostic["verdict"]
            if decision == "possible_withhold":
                tally["false_withhold" if contains else "correct_possible_withhold"] += 1
            elif decision == "keep":
                tally["correct_keep" if contains else "missed_omission"] += 1
            else:
                tally["abstain"] += 1
            scores[name] = dict(contained=contains, **diagnostic,
                                original_pooled=old["pooled"]["gain"],
                                original_receiver_gains={rx: v["gain"] for rx, v in old["receivers"].items()},
                                original_pooled_would_withhold=old["would_withhold"],
                                original_bilateral_would_withhold=bilateral,
                                probe_clocks=row["probe_clocks"], fold_clocks=row["fold_clocks"])
        cards[site] = dict(offers=scores, native_sha256=result["native_sha256"],
                           graph_clocks=result["graph_clocks"], catalogue_clocks=result["catalogue_clocks"])
    verification = {site: digest(path.read_bytes()) for site, path in paths.items()}
    scored = dict(sites=cards, tally=dict(tally), verification=verification)
    write(summary, scored)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(scores=scored, sites=sealed), separators=(",", ":"),
                                             allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("site", choices=SITES)
    trial.add_argument("output", type=Path)
    scoring = actions.add_parser("score")
    for name in ("directory", "summary", "full"):
        scoring.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
