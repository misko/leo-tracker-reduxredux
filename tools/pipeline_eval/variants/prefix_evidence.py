"""Choose one detector after a fixed early window of physically recurring pilot support."""

from collections import Counter, defaultdict, deque

from .coherent_peak_filter import Peak, continuation, step

SECONDS = 24
METHOD = "prefix_evidence"


def counter(probe, rate):
    offset, remainder = divmod(probe["probe_start_ms"] * rate, 1000)
    if remainder:
        raise ValueError("Probe time is not an integer ADC sample")
    return probe["valid_start_counter"] + offset


def geometry(document):
    source, anchor = document["source"], document["clock_anchor"]["sample_counter"]
    rate = source["sample_rate_hz"]
    if (rate, source["probe_ms"]) != (10_000_000, 20) or type(anchor) is not int:
        raise ValueError("Prefix policy requires the measured 10 MS/s and 20 ms geometry")
    return rate, rate // 50, anchor, anchor + SECONDS * rate


def support(probes, rate, dwell, anchor, cutoff):
    ends, lanes = {}, {}
    first_rf, last = {}, {}
    history = defaultdict(lambda: deque(maxlen=2))
    for p in probes:
        start = counter(p, rate)
        if not anchor <= start or start + dwell > cutoff:
            raise ValueError("Prefix decision was given an unavailable dwell")
        lane = p["receiver_id"], p["channel"], p["edge"]
        rf = p["actual_rf_hz"]
        offset = rf - first_rf.setdefault(lane, rf)
        visit = p["visit_index"], p["receiver_id"]
        if start <= last.get(lane, -1):
            raise ValueError("Physical-lane input must proceed in exact sample-counter order")
        last[lane] = start
        peaks = tuple(
            Peak(
                p["visit_index"],
                start,
                c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"],
                c["fractional_tracking_cfo_hz"] + offset,
            )
            for c in p["candidates"]
            if c["passed_fractional_margin_gate"]
        )
        before = history[lane]
        if (
            len(before) == 2
            and peaks
            and any(
                (paired := step(a, b, rate)) is not None
                and any(continuation(b, paired, c, rate, rf, dwell / rate) for c in peaks)
                for a in before[0]
                for b in before[1]
            )
        ):
            ends[visit] = int(start - anchor >= SECONDS * rate // 2)
            lanes[visit] = lane
        before.append(peaks)
    return ends, lanes


def decide(before, after, rate, dwell, anchor, cutoff):
    stock, stock_lanes = support(before, rate, dwell, anchor, cutoff)
    five, five_lanes = support(after, rate, dwell, anchor, cutoff)
    only_five, only_stock = five.keys() - stock.keys(), stock.keys() - five.keys()
    halves = [
        sum(five[k] == h for k in only_five) - sum(stock[k] == h for k in only_stock)
        for h in (0, 1)
    ]
    added, lost = (
        Counter(five_lanes[k] for k in only_five),
        Counter(stock_lanes[k] for k in only_stock),
    )
    gained_lanes = sum(added[k] > lost[k] for k in added)
    net, union = len(only_five) - len(only_stock), len(stock.keys() | five.keys())
    selected = (
        "fifth"
        if (net >= 8 and 8 * net >= union and min(halves) > 0 and gained_lanes >= 2)
        else "stock"
    )
    return dict(
        chosen=selected,
        stock_endpoints=len(stock),
        fifth_endpoints=len(five),
        fifth_only=len(only_five),
        stock_only=len(only_stock),
        net=net,
        union=union,
        net_by_half=halves,
        gained_lanes=gained_lanes,
    )
