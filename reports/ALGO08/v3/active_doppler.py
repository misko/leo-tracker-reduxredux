"""Paid-history satellite competition on one archived dense acquisition interval."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
from itertools import islice, product
import json
from math import ceil, floor
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.region import SearchRegion
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from tools.pipeline_eval.variants.capture_bursts import visit_pairs

from .anchor_sky import (ADC, ALIAS, CFO_TOLERANCE, LIGHT_KM_S, SIGNED_LIMIT, Factor, cluster,
                         lanes_for)
from .causal_mask_recovery import HORIZON, MASK_PINS, MASK_ROOT, ORIGINALS, supported
from .scout_readout_trial import check_machine
from .stereo_lane_schedule import StereoSchedule


HERE = Path(__file__).resolve().parent
CASE = "DS30-0008"
VISITS = 1024
REQUEST = Path("/dev/shm/leo-held-anchor-selected-dense-01/request.json")
REQUEST_SHA = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
PROTOCOL = HERE / "active-doppler-protocol.md"
MODES = ("active", "recent", "uniform")
ARMS = ("c0", "fitted_c")
COMPETITOR_TOLERANCE = 4550.
EXPLORATION = 4


def clock():
    return process_time(), perf_counter()


def since(start):
    return dict(zip(("cpu_s", "elapsed_s"), (now-old for now, old in zip(clock(), start, strict=True))))


def digest(data):
    return sha256(data).hexdigest()


def load(path, pinned):
    data = path.read_bytes()
    if digest(data) != pinned:
        raise ValueError(f"Unexpected staged evidence at {path}")
    return json.loads(data)


def stream(lane):
    return lane.rx, lane.edge, lane.channel, lane.rf


def metadata(document):
    """Split opportunities and observed base winners before opening any full outcome."""
    schedule = StereoSchedule("target")
    recorded = list(islice(visit_pairs(document["source"]["probes"]), VISITS))
    rows = [row for _, pair in recorded for row in pair]
    lanes = lanes_for(rows, document["clock_anchor"], document["source"]["probe_ms"])
    choices = []
    for i, (visit, pair) in enumerate(recorded):
        left = pair[0]
        mode, omitted = schedule.next((left["edge"], left["channel"], left["actual_rf_hz"]))
        visit_rows = []
        for lane, row in zip(lanes[2*i:2*i+2], pair, strict=True):
            concepts = row["candidates"]
            if (len(concepts) > 1 or any(c["passed_fractional_margin_gate"] is not True for c in concepts)
                    or (lane.rx == omitted and (concepts or mode == "full"))):
                raise ValueError("A short planning input disclosed an unpaid observation")
            visit_rows.append((lane, concepts[0]["fractional_tracking_cfo_hz"] if concepts else None,
                               lane.rx == omitted, mode))
        if visit_rows[0][0].visit != visit or visit_rows[1][0].time != visit_rows[0][0].time:
            raise ValueError("Mismatched stereo visit timing authority")
        choices.extend(visit_rows)
    if len(recorded) != VISITS:
        raise ValueError("The original bounded interval is incomplete")
    return lanes, choices


def predict_geometry(catalogue, origin, lanes, offer):
    """Evaluate predictable geometry only, sharing times across both radios."""
    start = clock()
    times = np.array([row.time for row in lanes[::2]])
    nominal = np.array([row.nominal for row in lanes[::2]])
    if any(left.nominal != right.nominal for left, right in zip(lanes[::2], lanes[1::2], strict=True)):
        raise ValueError("Stereo orbit columns require identical nominal RF")
    coarse = np.arange(0., max(times)+5., 5.)
    pos, vel, usable = ecef_states(catalogue, origin, coarse)
    screen = tuple(offer.screen_center)
    _, elevation, _, _ = look_angles(pos, vel, geodetic_to_ecef_km(*screen, 0.), ecef_to_enu_matrix(*screen))
    visible = np.flatnonzero(usable & (np.max(elevation, axis=1) >= -12.))
    chosen = type(catalogue)(*[tuple(values[i] for i in visible) for values in (
        catalogue.names, catalogue.satellite_numbers, catalogue.satellites)])
    seconds = np.arange(0., ceil(max(times))+1.)
    pos, vel, usable = ecef_states(chosen, origin, seconds)
    pos, vel = pos[usable], vel[usable]
    norads = np.asarray(chosen.satellite_numbers)[usable]
    position = tuple(offer.center)
    region = SearchRegion(position, offer.width_km)
    coordinates = [position, *(region.latlon(xy) for xy in product((-region.half_width_km, region.half_width_km), repeat=2))]
    first = np.floor(times).astype(int)
    last = np.minimum(first+1, len(seconds)-1)
    fraction = times-first
    _, elevation, _, _ = look_angles(pos, vel, geodetic_to_ecef_km(*position, 0.), ecef_to_enu_matrix(*position))
    visibility = (elevation[:, first]*(1.-fraction)+elevation[:, last]*fraction) >= 0.
    propagation = since(start)
    start = clock()
    views = []
    for coordinate in coordinates:
        relative = pos-geodetic_to_ecef_km(*coordinate, 0.)
        radial = np.einsum("sti,sti->st", relative, vel)/np.linalg.norm(relative, axis=2)
        views.append(-(radial[:, first]*(1.-fraction)+radial[:, last]*fraction)*nominal/LIGHT_KM_S)
    projected = since(start)
    return np.asarray(views), visibility, norads, dict(propagation=propagation, five_sites=projected,
        single_screen_orbit_epochs=len(catalogue.satellite_numbers)*len(coarse), propagated_orbit_epochs=len(visible)*len(seconds),
        active_satellites=len(norads), map_sites=len(coordinates), predicted_lane_times=len(times),
        projected_rf_cells=len(norads)*len(times)*len(coordinates), duration_s=float(max(times)),
        forecast_25_site_projection_cpu_s=projected["cpu_s"]*5)


def nominate(lane, fits, views, visibility, norads):
    offers = []
    for fit in fits:
        sat, index = fit.satellite, lane.index//2
        if not visibility[sat, index]:
            continue
        center = float(views[0, sat, index])+fit.offset
        low = ceil((-SIGNED_LIMIT-center)/ALIAS)
        high = floor((SIGNED_LIMIT-center)/ALIAS)
        alias = min(max(fit.alias, low), high)
        if low > high:
            continue
        signed = center+alias*ALIAS+lane.tuning_offset
        past = [factor.lane.index//2 for factor in fit.factors]
        at_past, at_target = views[:, sat, past], views[:, sat, index]
        delta = at_target-at_target[0]-np.median(at_past-at_past[0], axis=1)
        width = max(CFO_TOLERANCE, fit.score[2])
        offers.append(dict(norad=int(norads[sat]), signed_hz=signed, alias=int(alias), historical_rows=len(past),
                           training_rms_hz=fit.score[2], lower_hz=float(signed+min(delta)-width),
                           upper_hz=float(signed+max(delta)+width)))
        if len(offers) == 2:
            break
    return offers


def separation(offers):
    if len(offers) != 2:
        return None
    first, second = sorted(offers, key=lambda offer: offer["lower_hz"])
    return second["lower_hz"]-first["upper_hz"]


def buy(ordinal, paid_optional, triggered):
    """Reserve the fixed exploration call and always honor the two remaining calls."""
    if ordinal == EXPLORATION:
        return "explore"
    remaining = 2-paid_optional
    if not remaining:
        return None
    ordinary_after = 7-ordinal-int(ordinal < EXPLORATION)
    if remaining > ordinary_after:
        return "force"
    return "trigger" if triggered else None


def strict_support(history, start):
    return tuple(factor for factor in history if start-8. <= factor.lane.time < start)


def make_plan(rows, views, visibility, norads):
    start = clock()
    inventory, active_counts = Counter(), Counter()
    for lane, _, omitted, mode in rows:
        if omitted:
            inventory[stream(lane)] += 1
        else:
            active_counts["base_"+mode] += 1
    history, last_paid = defaultdict(deque), defaultdict(lambda: deque(maxlen=2))
    progress, paid = Counter(), Counter()
    menus, traces, decisions, stats = {}, [], [], Counter()
    center = np.repeat(views[0], 2, axis=1)
    for lane, measured, omitted, _ in rows:
        tile = int(lane.time//4)
        lane_key, track_key = stream(lane), (lane.rx, lane.edge)
        if not omitted:
            last_paid[lane_key].append((lane.counter, measured))
            if measured is not None:
                old = history[track_key]
                while old and old[0].lane.time < tile*4-8.:
                    old.popleft()
                old.append(Factor(lane, measured, 0.))
            continue
        cache_key = (tile, *track_key)
        if cache_key not in menus:
            earlier = strict_support(history[track_key], tile*4)
            fits, eligible = cluster(earlier, center, lane.rx, None)
            menus[cache_key] = fits
            stats.update(fit_blocks=1, historic_lanes=len(earlier),
                         compared_satellite_history_cells=len(norads)*len(earlier) if len(earlier) >= 3 else 0,
                         admissible_satellite_blocks=eligible, blocks_with_two=len(fits) >= 2)
            traces.append(dict(block_start=tile*4, receiver=lane.rx, edge=lane.edge, paid=len(earlier),
                               latest_paid_time=earlier[-1].lane.time if earlier else None,
                               admissible=eligible, retained=len(fits)))
        offers = nominate(lane, menus[cache_key], views, visibility, norads)
        gap = separation(offers)
        trigger = gap is not None and gap > 0.
        recent = supported(last_paid[lane_key], lane.counter, "recent")
        offset, previous = divmod(progress[lane_key], 8)
        progress[lane_key] += 1
        included = (offset+1)*8 <= inventory[lane_key]
        picked = {}
        if included:
            for mode, enabled in (("active", trigger), ("recent", recent)):
                key = (mode, lane_key, offset)
                reason = buy(previous, paid[key], enabled)
                if reason not in (None, "explore"):
                    paid[key] += 1
                if reason:
                    picked[mode] = reason
            if previous in (1, EXPLORATION, 6):
                picked["uniform"] = "uniform"
        decisions.append(dict(slot=[lane.visit, lane.rx], lane=lane_key, counter=lane.counter, block=offset, ordinal=previous,
                              included=included, offers=offers, gap_hz=gap, recent=recent, bought=picked))
    return dict(decisions=decisions, recent_horizon_ticks=HORIZON, routing=since(start), trajectory_fit=dict(stats),
                track_blocks=traces, base_counts=dict(active_counts))


def plan(output):
    machine = check_machine()
    total = clock()
    native = load(MASK_ROOT / CASE / "target-input.json", MASK_PINS[CASE][0])
    request = load(REQUEST, REQUEST_SHA)
    offer_path = Path(request["offer"])
    archive_path = Path(request["archive"]["root"])
    if not all(path.resolve(strict=True).is_relative_to(REQUEST.parent) for path in (offer_path, archive_path)):
        raise ValueError("Use only the staged causal archive and offer")
    source, anchor = native["source"], native["clock_anchor"]
    before, after = (anchor[name]["realtime_ns"] for name in ("before", "after"))
    if ((source["session_id"], source["input_manifest_sha256"], source["raw_recording_authority_digest"], before)
            != tuple(request[name] for name in ("session", "inventory", "authority", "cutoff_utc_ns"))):
        raise ValueError("The planning packet differs from its causal authority")
    reader = TleArchiveReader(archive_path)
    archive = {item.path.name: item.sha256 for item in reader.list_snapshots("space-track")}
    if canonical_digest(archive) != request["archive"]["snapshots_sha256"] or not 0 <= after-before <= 2e9:
        raise ValueError("The earlier orbit archive or clock bracket changed")
    offer = Algo08Region.parse(load(offer_path, request["offer_sha256"]))
    lanes, rows = metadata(native)
    start = clock()
    catalogue = causal_catalogue(reader, before)
    cat_time = since(start)
    views, visibility, norads, geometry = predict_geometry(catalogue.catalogue, (before+after)//2, lanes, offer)
    data = make_plan(rows, views, visibility, norads)
    output.mkdir()
    write(output / "plan.json", dict(**data, machine=machine, geometry=geometry, catalogue=cat_time,
                                     snapshots=catalogue.snapshot_count, total=since(total), visits=VISITS,
                                     source_sha256=digest(Path(__file__).read_bytes()), protocol_sha256=digest(PROTOCOL.read_bytes()),
                                     target_sha256=MASK_PINS[CASE][0], request_sha256=REQUEST_SHA))


def summarize(decisions, positives, owned, published_ids, cost):
    groups = defaultdict(list)
    for row in decisions:
        groups[(*row["lane"], row["block"])].append(row)
    paid = {mode: [] for mode in MODES}
    ceilings = {arm: Counter() for arm in ARMS}
    for rows in groups.values():
        if len(rows) == 8:
            if any(sum(mode in row["bought"] for row in rows) != 3 for mode in MODES):
                raise ValueError("The matched block budgets differ")
            for arm in ARMS:
                is_owner = [tuple(row["slot"]) in owned[arm] for row in rows]
                pinned = int(is_owner[EXPLORATION])
                ceilings[arm].update(any_three=min(3, sum(is_owner)), with_exploration=pinned+min(2, sum(is_owner)-pinned))
        elif any(row["bought"] for row in rows):
            raise ValueError("Bought from an incomplete block")
        for mode in MODES:
            paid[mode].extend((tuple(row["slot"]), row["bought"][mode]) for row in rows if mode in row["bought"])
    query_map = {tuple(row["slot"]): row for row in decisions}
    cohort = set(query_map)
    possible = {arm: owned[arm] & cohort for arm in ARMS}

    def hits(slots, arm):
        values = Counter()
        for slot in slots & possible[arm]:
            row = query_map[slot]
            cfo, sat = published_ids[arm][slot]
            values.update(owned=1, two_hypotheses=len(row["offers"]) == 2, separable=(row["gap_hz"] or 0.) > 0.,
                          right_norad=any(x["norad"] == sat for x in row["offers"]),
                          right_norad_and_signed_cfo=any(x["norad"] == sat and abs(x["signed_hz"]-cfo) <= COMPETITOR_TOLERANCE
                                                         for x in row["offers"]))
        return dict(values)

    measured = {}
    for mode, entries in paid.items():
        slots = {slot for slot, _ in entries}
        measured[mode] = dict(buys=len(slots), buys_by_reason=dict(Counter(why for _, why in entries)),
                              positives=len(slots & positives), empty=len(slots-positives),
                              simulated_native_cpu_s=cost*len(slots), owners={arm: hits(slots, arm) for arm in ARMS})
    return dict(omitted=len(cohort), positives=len(cohort & positives), possible={arm: len(slots) for arm, slots in possible.items()},
                model_coverage={arm: hits(cohort, arm) for arm in ARMS},
                lanes_with_two=sum(len(row["offers"]) == 2 for row in decisions),
                lanes_separable=sum((row["gap_hz"] or 0.) > 0. for row in decisions),
                oracle={arm: dict(value) for arm, value in ceilings.items()}, modes=measured)


def score(root):
    from .causal_mask_recovery import observe_cases

    plan_path = root / "plan.json"
    plan = json.loads(plan_path.read_bytes())
    if plan["source_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("Prediction source changed after sealing")
    omitted, positives, owned, cost = observe_cases(CASE)
    binding = load(MASK_ROOT / CASE / "binding.json", MASK_PINS[CASE][1])
    full = load(*ORIGINALS[CASE])
    mappings = [{oid: norad for oid, norad, _ in binding["controls"]["full"]["selected_rows"][arm]} for arm in ARMS]
    measurements = {arm: {} for arm in ARMS}
    for row in full["source"]["probes"]:
        slot = (row["visit_index"], row["receiver_id"])
        if slot not in owned["c0"] | owned["fitted_c"]:
            continue
        oid = f'{full["source"]["session_id"]}:{slot[1]}:{row["valid_start_counter"]}'
        identity = "sha256:"+digest(oid.encode())
        factor, = row["candidates"]
        for arm, mapping in zip(ARMS, mappings, strict=True):
            if slot in owned[arm]:
                measurements[arm][slot] = [factor["fractional_tracking_cfo_hz"], mapping[identity]]
    if not {tuple(row["slot"]) for row in plan["decisions"]} <= omitted:
        raise ValueError("Planned lane is outside the authentic omitted slots")
    assessed = summarize(plan["decisions"], positives, owned, measurements, cost)
    write(root / "score.json", dict(plan=plan, plan_sha256=digest(plan_path.read_bytes()), held=assessed,
                                    unit_short_cpu_s=cost, original_omitted=len(omitted),
                                    original_required_owned={arm: len(slots) for arm, slots in owned.items()},
                                    waveform_calls=0, solver_calls=0))


def write(path, doc):
    with path.open("x") as stream:
        json.dump(doc, stream, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "score"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    {"plan": plan, "score": score}[args.stage](args.path)
