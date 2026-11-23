"""Nominate signed cross-RF pilot proposals from sparse anchors and causal orbits."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
from hashlib import sha256
from itertools import combinations, product
import json
import math
from pathlib import Path
from time import process_time

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles

from .anchor_orbit_census import ADC, PERIOD, choose_anchors, factor_values, saved_ledger, selected, summarize


ALIAS = TrackConfig().alias_spacing_hz
LIGHT_KM_S = 299792.458
CFO_TOLERANCE = 2250.
PHASE_TOLERANCE = 6.
TIME_LIMIT = 8.
BIN_COUNT = round(ALIAS / 4500.)
SIGNED_LIMIT = 800000.


@dataclass(frozen=True)
class Lane:
    index: int
    visit: int
    rx: int
    channel: int
    rf: float
    edge: str
    counter: int
    time: float

    @property
    def nominal(self):
        return starlink_edge_rf_center_frequency_hz(self.channel, self.edge)

    @property
    def tuning_offset(self):
        return self.nominal - self.rf


@dataclass(frozen=True)
class Factor:
    lane: Lane
    cfo: float
    phase: float


@dataclass(frozen=True)
class Tracklet:
    satellite: int
    offset: float
    alias: int
    factors: tuple
    score: tuple


def wrap(value, period):
    return (value + period / 2) % period - period / 2


def lanes_for(rows, clock, probe_ms):
    return [Lane(index, row["visit_index"], row["receiver_id"], row["channel"],
                 row["actual_rf_hz"], row["edge"], row["valid_start_counter"],
                 (row["valid_start_counter"] - clock["sample_counter"]) / ADC + probe_ms * .0005)
            for index, row in enumerate(rows)]


def anchor_factors(rows, lanes, anchors):
    return [Factor(lane, *factor_values(lane.counter, candidate))
            for row, lane in zip(rows, lanes, strict=True) if lane.visit in anchors
            for candidate in row["candidates"]]


def projected_sky(catalogue, origin, lanes, offer, *, include_visibility=False):
    duration = max(lane.time for lane in lanes)
    coarse = np.arange(0., duration + 5., 5.)
    pos, vel, usable = ecef_states(catalogue, origin, coarse)
    screen = tuple(offer.screen_center)
    _, elevation, _, _ = look_angles(pos, vel, geodetic_to_ecef_km(*screen, 0.),
                                      ecef_to_enu_matrix(*screen))
    visible = np.flatnonzero(usable & (np.max(elevation, axis=1) >= -12.))
    if not len(visible):
        raise ValueError("No visible causal orbit in the supplied region")
    chosen = type(catalogue)(*[tuple(values[i] for i in visible) for values in (
        catalogue.names, catalogue.satellite_numbers, catalogue.satellites)])
    grid = np.arange(0., math.ceil(duration) + 1.)
    pos, vel, usable = ecef_states(chosen, origin, grid)
    usable = np.flatnonzero(usable)
    if not len(usable):
        raise ValueError("No continuously usable causal orbit over the signed recording")
    numbers = np.asarray(chosen.satellite_numbers)[usable]
    pos, vel = pos[usable], vel[usable]
    centers = np.array([lane.time for lane in lanes])
    floor = np.floor(centers).astype(int)
    fraction = centers - floor
    ceiling = np.minimum(floor + 1, len(grid) - 1)
    nominal = np.array([lane.nominal for lane in lanes])

    def projected(coordinate):
        relative = pos - geodetic_to_ecef_km(*coordinate, 0.)
        distance = np.linalg.norm(relative, axis=2)
        rate = np.einsum("sti,sti->st", relative, vel) / distance
        delay_samples = distance * (ADC / LIGHT_KM_S)
        cfo = -(rate[:, floor] * (1. - fraction) + rate[:, ceiling] * fraction) * nominal / LIGHT_KM_S
        delay = delay_samples[:, floor] * (1. - fraction) + delay_samples[:, ceiling] * fraction
        return cfo, delay

    cfo, delay = projected(offer.center)
    region = SearchRegion(offer.center, offer.width_km)
    corner_deltas = []
    for xy in product((-region.half_width_km, region.half_width_km), repeat=2):
        corner_cfo, corner_delay = projected(region.latlon(xy))
        corner_deltas.append(dict(xy_km=xy, maximum_cfo_hz=float(np.max(np.abs(cfo-corner_cfo))),
                                  maximum_range_samples=float(np.max(np.abs(delay-corner_delay)))))
    metadata = dict(coarse_visible=len(visible), usable=len(usable), corner_deltas=corner_deltas)
    if include_visibility:
        center = tuple(offer.center)
        _, elevation, _, _ = look_angles(pos, vel, geodetic_to_ecef_km(*center, 0.),
                                         ecef_to_enu_matrix(*center))
        metadata["above_horizon"] = (
            (elevation[:, floor] * (1. - fraction) + elevation[:, ceiling] * fraction) >= 0.
        )
    return cfo, delay, numbers, metadata


def stereo_offset(factors):
    by_visit = defaultdict(lambda: ([], []))
    for factor in factors:
        by_visit[factor.lane.visit][factor.lane.rx].append(factor.cfo)
    candidates = defaultdict(dict)
    paired, folded = set(), set()
    for visit, (first, second) in by_visit.items():
        for a, b in product(first, second):
            paired.add(visit)
            delta = b-a
            if abs(wrap(delta, ALIAS)) <= 25000.:
                folded.add(visit)
            if abs(delta) <= 25000.:
                bucket = round(delta / 1000.)
                # Multiple alternatives in a stereo visit are never extra votes.
                current = candidates[bucket].get(visit)
                if current is None or abs(delta-bucket*1000.) < abs(current-bucket*1000.):
                    candidates[bucket][visit] = delta
    inventory = dict(paired_anchor_visits=len(paired), within_folded_25khz=len(folded))
    if not candidates:
        return None, dict(**inventory, best_visits=0, rival_visits=0)
    best = min(candidates, key=lambda key: (-len(candidates[key]), abs(key), key))
    support = candidates[best]
    rival = max((len(votes) for key, votes in candidates.items() if abs(best-key)>1), default=0)
    accepted = len(support) >= 3 and len(support) >= 2*rival
    shift = float(np.median(list(support.values()))) if accepted else None
    return shift, dict(**inventory, best_visits=len(support), rival_visits=rival, offset_rx1_minus_rx0_hz=shift)


def cluster(factors, cfo, target_rx, stereo):
    """Screen all regional satellite columns for local shared anchor support."""
    if len(factors) < 3 or not len(cfo):
        return (), 0
    indices = [f.lane.index for f in factors]
    signed = np.array([f.cfo - f.lane.tuning_offset
                       - (0. if stereo is None else (f.lane.rx-target_rx)*stereo) for f in factors])
    raw = signed - cfo[:, indices]
    residual = wrap(raw, ALIAS)
    ordinal = np.arange(len(cfo)) * BIN_COUNT
    fits = {}
    for phase in (0., .5):
        code = np.floor((residual + ALIAS/2) * BIN_COUNT / ALIAS + phase).astype(int) % BIN_COUNT
        histogram = np.bincount((code + ordinal[:, None]).ravel(), minlength=len(cfo)*BIN_COUNT)
        histogram = histogram.reshape(-1, BIN_COUNT)
        for sat in np.flatnonzero(histogram.max(axis=1) >= 3):
            for bucket in np.flatnonzero(histogram[sat] >= 3):
                possible = np.flatnonzero(code[sat] == bucket)
                center = (bucket + .5 - phase) * ALIAS / BIN_COUNT - ALIAS/2
                # Prefer own receiver, then closest to the bin center, within each visit.
                order = sorted(possible, key=lambda i: (
                    factors[i].lane.rx != target_rx, abs(wrap(residual[sat, i]-center, ALIAS)), i))
                unique = {}
                for i in order:
                    unique.setdefault(factors[i].lane.visit, i)
                use = list(unique.values())
                channels = {(factors[i].lane.channel, factors[i].lane.rf) for i in use}
                if len(use) < 3 or len(channels) < 2:
                    continue
                angles = residual[sat, use] * (2*math.pi/ALIAS)
                offset = float(np.angle(np.mean(np.exp(1j * angles))) * ALIAS/(2*math.pi))
                error = wrap(residual[sat, use] - offset, ALIAS)
                alias = np.rint((raw[sat, use] - offset) / ALIAS).astype(int)
                votes = Counter(map(int, alias))
                mode = min(votes, key=lambda key: (-votes[key], abs(key), key))
                score = (-len(use), -len(channels), float(np.sqrt(np.mean(error**2))), int(sat))
                fit = Tracklet(int(sat), offset, mode, tuple(factors[i] for i in use), score)
                if sat not in fits or score < fits[sat].score:
                    fits[sat] = fit
    return tuple(sorted(fits.values(), key=lambda fit: fit.score)[:12]), len(fits)


def timing_proposal(fit, lane, delay, shared_rf):
    before, after = [], []
    for factor in fit.factors:
        source = factor.lane
        if (source.rx != lane.rx or source.edge != lane.edge or abs(source.time-lane.time)>TIME_LIMIT
                or (not shared_rf and (source.channel, source.rf) != (lane.channel, lane.rf))):
            continue
        phase = wrap(factor.phase - delay[fit.satellite, source.index], PERIOD)
        before.append(source.time)
        after.append(phase)
    options = []
    for a, b in combinations(range(len(before)), 2):
        delta = before[b]-before[a]
        if not delta:
            continue
        slope = wrap(after[b]-after[a], PERIOD)/delta
        if abs(slope) <= 100.:
            t = lane.time
            cost = (max(abs(t-before[a]), abs(t-before[b])), abs(slope), a, b)
            phase = after[a]+slope*(t-before[a])+delay[fit.satellite, lane.index]
            options.append((cost, float(phase % PERIOD)))
    return min(options)[1] if options else None


def proposals(lanes, factors, cfo, delay, numbers, anchors, stereo):
    blocks = defaultdict(list)
    for lane in lanes:
        if lane.visit not in anchors:
            blocks[int(lane.time // 4), lane.rx, lane.edge].append(lane)
    result, tracking = {}, Counter()
    for (tile, rx, edge), targets in blocks.items():
        midpoint = tile*4 + 2
        eligible = [f for f in factors if f.lane.edge == edge and (f.lane.rx == rx or stereo is not None)
                    and abs(f.lane.time-midpoint) <= TIME_LIMIT]
        visits = {factor.lane.visit for factor in eligible}
        rf_channels = {(factor.lane.channel, factor.lane.rf) for factor in eligible}
        fits, count = cluster(eligible, cfo, rx, stereo)
        tracking.update(blocks=1, blocks_with_tracklets=bool(fits), eligible_satellite_blocks=count,
                        retained_satellite_blocks=len(fits),
                        blocks_with_under_three_anchor_visits=len(visits) < 3,
                        blocks_with_single_rf_support=len(visits) >= 3 and len(rf_channels) < 2,
                        blocks_with_multi_rf_opportunity=len(visits) >= 3 and len(rf_channels) >= 2,
                        pooled_stereo_tracklets=sum(len({f.lane.rx for f in fit.factors})==2 for fit in fits))
        for lane in targets:
            offers = []
            for fit in fits:
                nearby = [f for f in fit.factors if abs(f.lane.time-lane.time)<=TIME_LIMIT]
                rf = (lane.channel, lane.rf)
                have_local = any((f.lane.channel, f.lane.rf) == rf for f in nearby)
                if not any((f.lane.channel, f.lane.rf) != rf for f in nearby):
                    continue
                center = float(cfo[fit.satellite, lane.index] + fit.offset)
                first = math.ceil((-SIGNED_LIMIT-center)/ALIAS)
                last = math.floor((SIGNED_LIMIT-center)/ALIAS)
                branches = sorted(range(first, last+1), key=lambda k: (abs(k-fit.alias), abs(k), k))
                if branches:
                    frequencies = [center + lane.tuning_offset + k*ALIAS for k in branches]
                    offers.append(dict(norad=int(numbers[fit.satellite]), frequencies=frequencies,
                                       phase_same=timing_proposal(fit, lane, delay, False),
                                       phase_shared=timing_proposal(fit, lane, delay, True),
                                       no_same_rf=not have_local))
            result[lane.index] = offers
    return result, dict(tracking)


def ranked(offers, limit=2):
    """Spend the signed attempt budget, prioritizing one branch per identity."""
    found = []
    width = max((len(o["frequencies"]) for o in offers), default=0)
    for branch in range(width):
        for offer in offers:
            if len(offer["frequencies"]) <= branch:
                continue
            hz = offer["frequencies"][branch]
            if any(abs(hz-value) <= CFO_TOLERANCE for value, _ in found):
                continue
            found.append((hz, offer))
            if len(found) == limit:
                return found
    return found


def diagnostic_packet(rows, anchors, nominations, evidence, source_digest, rejected_visits=()):
    """Freeze the first 48 raw visits without revealing model identities."""
    visits = {row["visit_index"] for row in rows[::2]}
    rejected = {row["visit"]: row["reason"] for row in rejected_visits}
    size = 48
    first = min(visits | rejected.keys())
    segment = range(first, first+size)
    if not set(segment) <= visits | rejected.keys() or visits & rejected.keys():
        raise ValueError("No complete 48-visit authority for an anchor diagnostic slice")
    paired = []
    metadata = ("visit_index", "receiver_id", "channel", "actual_rf_hz", "edge", "valid_start_counter")
    for index, row in enumerate(rows):
        if row["visit_index"] not in segment:
            continue
        full_anchor = row["visit_index"] in anchors
        result = {key: row[key] for key in metadata}
        result["full_anchor"] = full_anchor
        phase_at_start = ((row["valid_start_counter"]*3) % 40000) / 3
        for name, key in (("local_time", "phase_same"), ("shared_time", "phase_shared")):
            result[name] = [dict(cfo_hz=hz, epoch_sample=(offer[key]-phase_at_start) % PERIOD)
                            for hz, offer in ranked(nominations.get(index, ())) if offer[key] is not None]
        paired.append(result)
    return dict(raw_authority=evidence["raw_authority"], session_id=evidence["session_id"],
                source_predictions_sha256=source_digest, first_visit=first, visit_count=size,
                rejected_visits=[dict(visit_index=i, reason=rejected[i]) for i in segment if i in rejected],
                receiver_rows=paired)


def match(counter, factors, offers, phase_key):
    """Score a maximum-cardinality matching without reusing proposals."""
    possibilities = []
    for factor in factors:
        hz, phase = factor_values(counter, factor)
        possibilities.append([index for index, (proposal_hz, offer) in enumerate(offers)
                              if abs(hz-proposal_hz) <= CFO_TOLERANCE
                              and (phase_key is None or (offer[phase_key] is not None
                                   and abs(wrap(phase-offer[phase_key], PERIOD)) <= PHASE_TOLERANCE))])
    best = ()

    def visit(index, used, matches):
        nonlocal best
        if index == len(possibilities):
            if len(matches) > len(best):
                best = matches
            return
        for candidate in possibilities[index]:
            if candidate not in used:
                visit(index+1, used | {candidate}, (*matches, index))
        visit(index+1, used, matches)

    visit(0, set(), ())
    return [factors[i] for i in best]


def score(rows, original, cpu, anchors, nominated):
    retained = defaultdict(list)
    counts = Counter()
    channels = defaultdict(Counter)
    top_counts = []
    counts_by_budget = defaultdict(Counter)
    modes = ("signed_local_time", "signed_shared_time", "signed_exact_time_oracle",
             "all_aliases_exact_time_oracle", "foreign_rf_only_shared_time",
             "foreign_rf_only_exact_time_oracle", "four_signed_local_time",
             "four_signed_shared_time", "four_signed_exact_time_oracle")
    for index, row in enumerate(rows):
        factors = row["candidates"]
        if row["visit_index"] in anchors:
            for key in modes:
                retained[key].append(factors)
            continue
        offers = nominated[index]
        candidates = ranked(offers)
        four = ranked(offers, 4)
        foreign = ranked([offer for offer in offers if offer["no_same_rf"]])
        alias = [(hz, offer) for offer in offers for hz in offer["frequencies"]]
        counter = row["valid_start_counter"]
        choices = dict(
            signed_local_time=match(counter, factors, candidates, "phase_same"),
            signed_shared_time=match(counter, factors, candidates, "phase_shared"),
            signed_exact_time_oracle=match(counter, factors, candidates, None),
            all_aliases_exact_time_oracle=match(counter, factors, alias, None),
            foreign_rf_only_shared_time=match(counter, factors, foreign, "phase_shared"),
            foreign_rf_only_exact_time_oracle=match(counter, factors, foreign, None),
            four_signed_local_time=match(counter, factors, four, "phase_same"),
            four_signed_shared_time=match(counter, factors, four, "phase_shared"),
            four_signed_exact_time_oracle=match(counter, factors, four, None),
        )
        for key, found in choices.items():
            retained[key].append(found)
        counts.update(
            hold_lanes=1, hold_empty=not factors, hold_with_proposals=bool(candidates),
            hold_empty_with_proposals=not factors and bool(candidates),
            ranked_proposals=len(candidates), foreign_rf_ranked_proposals=len(foreign),
            ranked_with_local_time=sum(o["phase_same"] is not None for _, o in candidates),
            ranked_with_shared_time=sum(o["phase_shared"] is not None for _, o in candidates),
            ranked_without_signed_match=len(candidates)-len(choices["signed_exact_time_oracle"]),
            local_time_proposals_unmatched=sum(o["phase_same"] is not None for _, o in candidates)
            - len(choices["signed_local_time"]),
            shared_time_proposals_unmatched=sum(o["phase_shared"] is not None for _, o in candidates)
            - len(choices["signed_shared_time"]),
            all_signed_alias_offers=len(alias),
        )
        for budget, cells in ((1, candidates[:1]), (2, candidates), (4, four)):
            row_counts = counts_by_budget[budget]
            for key, phase in (("signed", None), ("local_time", "phase_same"), ("shared_time", "phase_shared")):
                testable = sum(phase is None or o[phase] is not None for _, o in cells)
                observed = match(counter, factors, cells, phase)
                row_counts[f"{key}_lanes_with_{testable}_attempts"] += 1
                row_counts[f"{key}_attempts"] += testable
                row_counts[f"{key}_matched_factors"] += len(observed)
                row_counts[f"{key}_unmatched_attempts"] += testable-len(observed)
        top_counts.append(len(alias))
        part = channels[(row["receiver_id"], row["channel"], row["actual_rf_hz"], row["edge"])]
        part.update(factors=len(factors), residuals=sum(f["candidate_rank"] == 1 for f in factors),
                    continued=len(original[index]))
        for key, found in choices.items():
            part[key] += len(found)
    evidence = {key: summarize(rows, original, selected(rows, facts), facts, anchors, cpu)
                for key, facts in retained.items()}
    return dict(counts=counts, attempt_budgets=dict(counts_by_budget), aliases_per_hold_lane={
        "median": float(np.median(top_counts)), "p95": float(np.percentile(top_counts, 95)),
        "maximum": max(top_counts)}, evidence=evidence,
        by_receiver_channel=[dict(key=key, counts=count) for key, count in sorted(channels.items())])


def sealed_inputs(pair_path, ledger_path, authority_path):
    pair_blob, ledger_blob, authority_blob = (p.read_bytes() for p in (pair_path, ledger_path, authority_path))
    pair, ledger, authority = json.loads(pair_blob), json.loads(gzip.decompress(ledger_blob)), json.loads(authority_blob)
    run = pair["runs"]["candidate"]
    receipt = run["receipt"]
    saved = pair_path.parent / "candidate/fast-scan-automatic-work"
    native_path, = saved.glob("*/detections.json")
    native_blob = native_path.read_bytes()
    native = json.loads(native_blob)
    terminal = json.loads((saved / receipt["run_id"] / "terminal.json").read_bytes())
    path = Path(pair["region"])
    offer = Algo08Region.parse(json.loads(path.read_bytes()))
    source = native["source"]
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or offer.document() != receipt["region"] or offer.document() != terminal["region"]
            or ledger["saved_detections_sha256"] != sha256(native_blob).hexdigest()
            or ledger["session_id"] != terminal["session_id"] or source["session_id"] != terminal["session_id"]
            or not ledger["raw_authority"] == run["raw_authority"] == source["raw_recording_authority_digest"]
            or ledger["detector_sha256"] != native["provenance"]["detector_sha256"].removeprefix("sha256:")):
        raise ValueError("signed ledger, recording and region binding differs")
    if "causal_snapshots" in authority:
        job = authority["job"]
        if job["identity"]["session_id"] != source["session_id"]:
            raise ValueError("causal DS30 archive references a different recording")
        archive = TleArchiveReader(Path(job["tle_root"]))
        snapshots = {s.path.name: s.sha256 for s in archive.list_snapshots("space-track")}
        if snapshots != authority["causal_snapshots"]:
            raise ValueError("causal DS30 archive differs from its frozen request")
    else:
        witness = authority["runs"]["candidate"]
        if witness["raw_authority"] != ledger["raw_authority"] or witness["receipt"]["session_id"] != ledger["session_id"]:
            raise ValueError("simulated causal archive references a different recording")
        archive = TleArchiveReader(Path(authority["archive"]["root"]))
        snapshots = {s.path.name: s.sha256 for s in archive.list_snapshots("space-track")}
        if canonical_digest(snapshots) != authority["archive"]["snapshots_sha256"]:
            raise ValueError("simulated causal archive differs from its verified pair")
    capture = native["clock_anchor"], source["probe_ms"], ledger["rows"], ledger["excluded_windows"]
    return native_path, capture, offer, archive, dict(
        raw_authority=ledger["raw_authority"], session_id=ledger["session_id"],
        terminal_sha256=receipt["terminal_sha256"], native_sha256=terminal["native_sha256"],
        pair_sha256=sha256(pair_blob).hexdigest(), archive_authority_sha256=sha256(authority_blob).hexdigest(),
        archive=str(archive.root), snapshots_sha256=canonical_digest(snapshots), region=offer.document(),
    )


def run(pair, ledger, authority, prediction_path, preview=None):
    native, capture, offer, archive, keys = sealed_inputs(pair, ledger, authority)
    clock, probe_ms, rows, rejected_visits = capture
    anchors = choose_anchors(rows)
    lanes = lanes_for(rows, clock, probe_ms)
    factors = anchor_factors(rows, lanes, anchors)
    before, after = (clock[k]["realtime_ns"] for k in ("before", "after"))
    if not 0 <= after-before <= 2e9:
        raise ValueError("invalid signed UTC interval")
    start = process_time()
    catalogue = causal_catalogue(archive, before)
    parsed = process_time()
    cfo, delay, numbers, sky = projected_sky(catalogue.catalogue, (before+after)//2, lanes, offer)
    projected = process_time()
    receiver_separate, tracking = proposals(lanes, factors, cfo, delay, numbers, anchors, None)
    tracked = process_time()
    offset, stereo = stereo_offset(factors)
    predictions = {"receiver_separate": receiver_separate}
    tracks = {"receiver_separate": tracking}
    if offset is not None:
        predictions["stereo_pooled"], tracks["stereo_pooled"] = proposals(
            lanes, factors, cfo, delay, numbers, anchors, offset)
    ended = process_time()
    compact = json.dumps(predictions, separators=(",", ":"), allow_nan=False).encode()
    prediction_digest = sha256(compact).hexdigest()
    with prediction_path.open("xb") as stream:
        stream.write(gzip.compress(compact, mtime=0))
    if preview is not None:
        packet = diagnostic_packet(rows, anchors, receiver_separate, keys, prediction_digest, rejected_visits)
        with preview.open("x") as stream:
            json.dump(packet, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    # Reveal full factors and selected outcomes only after the prediction file is fixed.
    rows, reference, cpu, ledger_receipt = saved_ledger(ledger, native)
    anchor_cpu = sum(cost for lane, cost in zip(lanes, cpu, strict=True) if lane.visit in anchors)/1e9
    input_index = Counter((lane.rx, lane.channel, lane.rf, lane.edge) for lane in lanes if lane.visit in anchors)
    anchor_index = Counter((f.lane.rx, f.lane.channel, f.lane.rf, f.lane.edge) for f in factors)
    return dict(inputs={**keys, **ledger_receipt}, visits=len(lanes)//2, anchors=sorted(anchors),
                anchor_factors=len(factors), anchor_native_cpu_s=anchor_cpu, native_cpu_s=sum(cpu)/1e9,
                anchor_support_by_receiver_rf=[dict(key=key, anchor_lanes=value, verification_factors=anchor_index[key])
                                               for key, value in sorted(input_index.items())],
                utc=dict(causal_before_ns=before, anchor_midpoint_ns=(before+after)//2,
                         initial_counter=clock["sample_counter"], bracket_width_s=(after-before)/1e9,
                         bracket_width_sampling_periods=(after-before)*ADC/1e9/PERIOD),
                orbit=dict(**sky, catalogue=len(catalogue.catalogue), snapshots=catalogue.snapshot_count,
                           element_provenance_sha256=canonical_digest(catalogue.provenance)),
                timing=dict(read_causal_catalogue_s=parsed-start, project_center_and_corners_s=projected-parsed,
                            receiver_separate_s=tracked-projected, stereo_test_and_fit_s=ended-tracked),
                stereo=stereo, provisional_tracks=tracks, predictions_sha256=prediction_digest,
                prediction_path=str(prediction_path),
                paired_scores={name: score(rows, reference, cpu, anchors, offered)
                               for name, offered in predictions.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("pair", "ledger", "authority", "prediction_path", "receipt"):
        parser.add_argument(field, type=Path)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    result = run(args.pair, args.ledger, args.authority, args.prediction_path, args.preview)
    with args.receipt.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
