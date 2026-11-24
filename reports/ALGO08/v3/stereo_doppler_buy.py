"""Causal signed-arc purchases on the original censored held North receiver."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from time import perf_counter, process_time

from tools.pipeline_eval.variants.capture_bursts import visit_pairs

from whole_stereo_blocks import CONTINUATION_SHA, load_checked, project, schedule


HERE = Path(__file__).resolve().parent
PAIR = Path("/dev/shm/leo-live-stereo-north.BYuWvuyj/pair")
NATIVE = {"unmasked": "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427",
          "masked": "2f81ae03d1112af526e17faca7f41101ba16fd50e4b65cb8076bd7af14776775"}
RECEIPT = HERE/"measurements/live-stereo-north.json.gz"
RECEIPT_SHA = "aa80cb5d7d38770e6f43344099ba856cc6ae576a4c2e8ed92ec5c4214f523a7d"
ARM_NAMES = ("c0", "fitted_c")
RULES = ("doppler", "earliest", "uniform")
QUARTETS = 80
TICKS = 10_000_000


def elapsed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def native(mode):
    source, = (PAIR/mode).glob("fast-scan-automatic-work/*/detections.json")
    return load_checked(source, NATIVE[mode])


def forecast(history, counter):
    """Return the strongest separated bands supported by disjoint earlier triplets."""
    if any(t >= counter for t, _, _ in history):
        raise ValueError("Forecast history must precede the current original visit")
    paid = [((t-counter)/TICKS, visit, hz) for t, visit, hz in history if hz is not None and counter-t <= 8*TICKS]
    if len(paid) < 6:
        return None
    arcs = []
    for (a, i, f), (b, j, g), (c, k, h) in combinations(paid, 3):
        span, age = c-a, -c
        if span < .4 or age > span:
            continue
        slope = (h-f)/span
        if abs(slope) > 8000 or abs(g-(f+slope*(b-a))) > 800:
            continue
        predicted = h + slope*age
        width = 800*(1+2*age/span)
        arcs.append((predicted-width, predicted+width, (i,j,k), slope))
    best = None
    for low, high in combinations(sorted(arcs), 2):
        gap = high[0]-low[1]
        if gap > (best[0] if best else 0) and set(low[2]).isdisjoint(high[2]):
            best = (gap, low, high)
    if best is None:
        return None
    gap, *bands = best
    return dict(gap_hz=gap, bands=[dict(lower_hz=a, upper_hz=b, support_visits=c, slope_hz_per_s=d) for a,b,c,d in bands])


def plan_rows(packet):
    history = defaultdict(lambda: deque(maxlen=12))
    restored, targets, counts = set(), [], Counter()
    for (visit, mode, keep), (_, rows) in zip(schedule(packet), visit_pairs(packet["source"]["probes"]), strict=True):
        lanes = [(r["receiver_id"],r["edge"],r["channel"],r["actual_rf_hz"]) for r in rows]
        now = rows[0]["valid_start_counter"]
        counts["base_"+mode if keep else "omitted"] += 2
        if keep:
            for lane, row in zip(lanes, rows, strict=True):
                candidates = row["candidates"]
                if len(candidates) > 1 or any(not c["passed_fractional_margin_gate"] for c in candidates):
                    raise ValueError("North routing needs original admitted mixed maxima")
                history[lane].append((now, visit, candidates[0]["fractional_tracking_cfo_hz"] if candidates else None))
            continue
        # The pre-admission digest binds the live censored packet. The decisions
        # consume no fields from the omitted detectors, including their ranks.
        block, ordinal = divmod(len(targets), 4)
        offers = [forecast(history[lane], now) for lane in lanes]
        buys = {}
        if block < QUARTETS:
            separable = any(offer is not None for offer in offers)
            if block not in restored and (separable or ordinal == 3):
                restored.add(block)
                buys["doppler"] = "forecast" if separable else "forced"
            if ordinal == 0:
                buys["earliest"] = "fixed"
            if ordinal == 2:
                buys["uniform"] = "fixed"
        targets.append(dict(visit=visit, block=block, ordinal=ordinal, buys=buys, forecasts=offers, counter=now,
                            lanes=lanes))
        for lane in lanes:
            history[lane].append((now, visit, None))
    if not all(sum(rule in row["buys"] for row in targets) == QUARTETS for rule in RULES):
        raise ValueError("Require identical complete quartet budgets")
    return dict(targets=targets, counts=dict(counts))


def plan(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from tools.pipeline_eval.variants import carrier_continuation

    if not root.parent.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Use a fresh private tmpfs study directory")
    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA:
        raise ValueError("The signed continuation thresholds require the pinned source")
    machine = host()
    start = process_time(), perf_counter()
    packet = native("masked")
    parsed = elapsed(start)
    start = process_time(), perf_counter()
    predicted = plan_rows(packet)
    clock = elapsed(start)
    root.mkdir()
    write(root/"plan.json", dict(**predicted, machine=machine, clock=clock, parse=parsed, masked_sha256=NATIVE["masked"],
                                 current_or_restored_outcomes_used=False,
                                 source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                                 protocol_sha256=sha256((HERE/"stereo-doppler-buy-protocol.md").read_bytes()).hexdigest()))


def observation_id(session, row):
    slot = f'{session}:{row["receiver_id"]}:{row["valid_start_counter"]}'
    return "sha256:" + sha256(slot.encode()).hexdigest()


def score(root):
    from aperture_trial import read, write

    plan_path = root/"plan.json"
    frozen = read(plan_path)
    if frozen["source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Score the sealed plan with the same receiver rule")
    original, masked = native("unmasked"), native("masked")
    derived, manifest = project(original, schedule(original))
    if (derived["source"]["probes"] != masked["source"]["probes"] or derived["clock_anchor"] != masked["clock_anchor"]
            or set(manifest["skipped_visits"]) != {r["visit"] for r in frozen["targets"]}):
        raise ValueError("Live North mask differs from the original unfiltered projection")
    receipt = load_checked(RECEIPT, RECEIPT_SHA)["runs"]
    support = {arm: {owner[0] for owner in receipt["unmasked"]["ordered_rows"][arm]} for arm in ARM_NAMES}
    probes = dict(visit_pairs(original["source"]["probes"]))
    original_session = original["source"]["session_id"]
    known = {observation_id(original_session, row) for row in original["source"]["probes"] if row["candidates"]}
    if not all(rows <= known and rows for rows in support.values()):
        raise ValueError("The held original owners cannot be joined to verified detector factors")
    rows, common = [], Counter()
    restored = {rule: Counter() for rule in RULES}
    by_block = defaultdict(list)
    for row in frozen["targets"]:
        valid, tested, match, owners = 0, 0, 0, Counter()
        for p, forecasted in zip(probes[row["visit"]], row["forecasts"], strict=True):
            values = p["candidates"]
            owner_id = observation_id(original_session, p)
            owns = {arm: int(owner_id in index) for arm,index in support.items()}
            owners.update(owns)
            valid += bool(values)
            if forecasted and values:
                (factor,) = values
                hz = factor["fractional_tracking_cfo_hz"]
                tested += 1
                match += any(band["lower_hz"] <= hz <= band["upper_hz"] for band in forecasted["bands"])
        lanes_with_forecasts = sum(bool(offer) for offer in row["forecasts"])
        common.update(positive_lanes=valid, forecast_visits=int(lanes_with_forecasts>0), forecast_lanes=lanes_with_forecasts,
                      tested_forecast_lanes=tested, signed_cfo_inside_forecast=match, **owners)
        rows.append(dict(visit=row["visit"], positive_lanes=valid, forecast_lanes=lanes_with_forecasts,
                         tested_forecast_lanes=tested, signed_cfo_inside_forecast=match, owners=dict(owners)))
        if row["block"] < QUARTETS:
            by_block[row["block"]].append(owners)
        for rule, reason in row["buys"].items():
            restored[rule].update(buys=1, positive_lanes=valid, **{reason: 1}, **owners)
            if reason == "forecast":
                restored[rule].update(tested_forecast_lanes=tested, signed_cfo_inside_forecast=match)
    acquired = receipt["unmasked"]["acquisition"]["native"]
    mean = acquired["native_cpu_ns"]["short_primary"]/acquired["native_calls"]["short_primary"]/1e9
    remaining_credit = (frozen["counts"]["omitted"]-2*QUARTETS)*mean
    active = restored["doppler"]
    conditions = dict(triggers=active["forecast"] >= 16,
                      owner_gain=all(active[arm] >= restored[name][arm]+4 for arm in ARM_NAMES for name in RULES[1:]),
                      signed_coverage=bool(active["tested_forecast_lanes"]) and 2*active["signed_cfo_inside_forecast"] >= active["tested_forecast_lanes"],
                      cost=frozen["clock"]["cpu_s"] < remaining_credit)
    write(root/"score.json", dict(forecasts=dict(common), restored=restored, revealed=rows, assessed_count=frozen["counts"],
                                  owner_oracle={arm:sum(max(r[arm] for r in group) for group in by_block.values()) for arm in ARM_NAMES},
                                  qualification=conditions, eligible=all(conditions.values()), waveform_calls=0, position_solves=0,
                                  modeled=dict(unit_short_call_cpu_s=mean, direct_extra_cpu_s=2*QUARTETS*mean,
                                               native_cpu_before_unfiltered=acquired["native_cpu_ns"],
                                               remaining_credit_cpu_s=remaining_credit, fixed_reads=True),
                                  plan_sha256=sha256(plan_path.read_bytes()).hexdigest(), native_sha256=NATIVE, live_receipt_sha256=RECEIPT_SHA))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "score"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"plan": plan, "score": score}[args.action](args.output)
