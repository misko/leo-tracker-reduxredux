"""Replay causal pilot prediction against saved native candidates, without IQ or satellite labels."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


INPUTS = Path("/srv/bulk/leo-dev/algo07v3-shortcuts-20261107/inputs")
OUTPUT = Path(__file__).parent
FREQ_PERIOD = 1.0 / 4.4e-6
FRAME_US = 1e6 / 750
FREQ_GATE = 8000.0
TIME_GATE_US = 25.0
MAX_AGE = 6.0
MAX_TRACKS = 3


def wrap(x, period):
    return (x + period * 0.5) % period - period * 0.5


def extract(document):
    source = document["source"]
    fs = source["sample_rate_hz"]
    zero = document["clock_anchor"]["sample_counter"]
    assert fs == 10_000_000 and source["probe_ms"] == 20
    rows = defaultdict(list)
    for p in source["probes"]:
        assert p["probe_start_ms"] == 0
        count = p["valid_start_counter"] - zero
        fphase = ((count * 750) % fs) / fs * FRAME_US
        eligible = sorted((c for c in p["candidates"] if c["passed_fractional_margin_gate"]),
                          key=lambda c: (-c["fractional_margin"], c["candidate_rank"]))
        peaks = [(c["fractional_tracking_cfo_hz"], (fphase + (
            c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]) * 1e6/fs) % FRAME_US)
            for c in eligible]
        key = (p["channel"], p["receiver_id"], p["actual_rf_hz"])
        rows[key].append((count/fs, p["visit_index"], peaks))
    return {lane: sorted(points) for lane, points in rows.items()}


def distance(candidate, prediction, phase_gate):
    freq, phase = candidate
    df = abs(wrap(freq - prediction[0], FREQ_PERIOD)) / FREQ_GATE
    if phase_gate:
        return max(df, abs(wrap(phase - prediction[1], FRAME_US)) / TIME_GATE_US)
    return df


def replay(lanes, period, phase_gate, emit=None):
    stats = Counter()
    for lane, rows in lanes.items():
        states = []
        for i, (t, visit, peaks) in enumerate(rows):
            states = [s for s in states if t-s[0] <= MAX_AGE]
            predictions = [(f + df*(t-last), e + de*(t-last)) for last, f, e, df, de in states]
            scheduled = i % period == 0
            blind = scheduled or not states
            stats["probes"] += 1
            stats["blind_probes"] += blind
            stats["scheduled_blind"] += scheduled
            stats["cold_blind"] += (not scheduled and not states)
            single_area = 2*FREQ_GATE/FREQ_PERIOD * (2*TIME_GATE_US/FRAME_US if phase_gate else 1.)
            stats["search_area_upper"] += 1. if blind else min(1., len(states)*single_area)
            if not peaks:
                continue
            stats["reference_winners"] += 1
            stats["blind_winners"] += blind
            if blind:
                observed = peaks[0]
            else:
                stats["guided_winners"] += 1
                nearest = lambda peak: min(distance(peak, q, phase_gate) for q in predictions)
                shifted = [(f+FREQ_PERIOD/3, e+FRAME_US/2) for f, e in predictions]
                stats["guided_shift_control_hits"] += any(
                    distance(peaks[0], q, phase_gate) <= 1. for q in shifted)
                observed = next((p for p in peaks if nearest(p) <= 1.), None)
                if observed is None:
                    continue
                stats["guided_exact"] += (observed == peaks[0])
                stats["guided_substitute"] += (observed != peaks[0])
            stats["reference_winners_reproduced"] += observed == peaks[0]
            if emit:
                emit(lane,visit,t,observed[0])
            f, e = observed
            dists = [distance(observed, q, phase_gate) for q in predictions]
            df = de = 0.
            if dists and min(dists) <= 1.:
                j = dists.index(min(dists))
                last, oldf, olde, olddf, oldde = states.pop(j)
                assert t > last
                step_df = max(-8000., min(8000., wrap(f-oldf,FREQ_PERIOD)/(t-last)))
                step_de = max(-50., min(50., wrap(e-olde,FRAME_US)/(t-last)))
                df, de = 0.5*(olddf+step_df), 0.5*(oldde+step_de)
            states = (states + [(t, f, e, df, de)])[-MAX_TRACKS:]
    return dict(stats)


def cross_receiver(lanes):
    pair = defaultdict(dict)
    unique_times = set()
    for (ch, rx, rf), rows in lanes.items():
        for t, visit, peaks in rows:
            unique_times.add(t)
            if peaks:
                pair[(ch, rf, visit)][rx] = peaks[0]
    stats = Counter()
    for winners in pair.values():
        stats["with_hit_on_either_rx"] += 1
        stats["hits_rx0"] += 0 in winners
        stats["hits_rx1"] += 1 in winners
        if 0 in winners and 1 in winners:
            stats["both"] += 1
            stats["agree_frequency"] += distance(winners[0],winners[1],False) <= 1.
            stats["agree_both_coordinates"] += distance(winners[0],winners[1],True) <= 1.
    times = sorted(unique_times)
    differences_ms = [(u-t)*1000 for t, u in zip(times,times[1:])]
    return dict(stats), median(differences_ms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=10)
    args = parser.parse_args()
    panel = sorted(p for p in INPUTS.glob("DS26-*/native.json"))[::args.stride]
    controls = [(4,True),(8,True),(16,True),(8,False)]
    totals = defaultdict(Counter)
    result = []
    for path in panel:
        raw = path.read_bytes()
        lanes = extract(json.loads(raw))
        per_case = {}
        for period, phase in controls:
            name = f"every{period}-{'joint' if phase else 'cfo'}"
            counter = replay(lanes, period, phase)
            totals[name].update(counter)
            per_case[name] = counter
        both, dt = cross_receiver(lanes)
        totals["paired_rx"].update(both)
        result.append(dict(case=path.parent.name, input_sha256=sha256(raw).hexdigest(),
                           paired_rx=both, median_probe_arrival_spacing_ms=dt, modes=per_case))
    doc = dict(selection=f"Every {args.stride}-th available native file in case order, starting at first",
               frame_us=FRAME_US, alias_hz=FREQ_PERIOD, frequency_gate_hz=FREQ_GATE,
               frame_gate_us=TIME_GATE_US, max_age_s=MAX_AGE, max_tracks=MAX_TRACKS,
               summary=totals, median_scan_probe_spacing_ms=median(
                   r["median_probe_arrival_spacing_ms"] for r in result), rows=result)
    dest = OUTPUT/f"pilot-prediction-stride{args.stride}.json"
    dest.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:v for k,v in doc.items() if k!="rows"},indent=2))


if __name__ == "__main__":
    main()
