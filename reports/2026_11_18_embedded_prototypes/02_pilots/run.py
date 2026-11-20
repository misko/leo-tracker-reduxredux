"""Replay a bounded causal pilot search schedule and its all-blind control."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, latlon

import numpy as np

import cold_replay as cold
from winner_to_fix import track_document, winners


INPUTS = Path("/srv/bulk/leo-dev/algo07v3-shortcuts-20261107/inputs")
FREQUENCY_PERIOD = 1 / 4.4e-6
PHASE_PERIOD_US = 1e6 / 750
SCOUT_INTERVAL = 4
MAX_HYPOTHESES = 3
MAX_AGE_S = 5.0


def wrap(value, period):
    return (value + period / 2) % period - period / 2


@dataclass(frozen=True, slots=True)
class Peak:
    rank: int
    frequency: float
    phase_us: float
    margin: float


@dataclass(frozen=True, slots=True)
class Probe:
    index: int
    receiver: int
    channel: int
    rf_hz: float
    time: float
    peaks: tuple[Peak, ...]

    @property
    def lane(self):
        return self.receiver, self.channel, self.rf_hz

    def observation(self, peak):
        return self.index, self.receiver, self.channel, self.rf_hz, self.time, peak.frequency


@dataclass(frozen=True, slots=True)
class Gate:
    frequency: float
    phase_us: float
    half_hz: float
    half_us: float

    def distance(self, peak):
        df = abs(wrap(peak.frequency - self.frequency, FREQUENCY_PERIOD))
        dp = abs(wrap(peak.phase_us - self.phase_us, PHASE_PERIOD_US))
        return max(df / self.half_hz, dp / self.half_us)

    @property
    def area(self):
        return (2 * self.half_hz / FREQUENCY_PERIOD) * (2 * self.half_us / PHASE_PERIOD_US)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    time: float
    peak: Peak
    hits: int = 1
    frequency_rate: float = 0.0
    phase_rate: float = 0.0

    def predict(self, now):
        dt = now - self.time
        if self.hits == 1:
            half_hz = 800 + 8000 * dt
            half_us = 12 + 30 * dt
        else:
            half_hz = 750 + 500 * dt + 100 * dt**2
            half_us = 10 + 8 * dt + 2 * dt**2
        return Gate(self.peak.frequency + dt * self.frequency_rate,
                    self.peak.phase_us + dt * self.phase_rate, half_hz, half_us)

    def update(self, now, peak):
        dt = now - self.time
        frequency_rate = wrap(peak.frequency - self.peak.frequency, FREQUENCY_PERIOD) / dt
        phase_rate = wrap(peak.phase_us - self.peak.phase_us, PHASE_PERIOD_US) / dt
        weight = 1.0 if self.hits == 1 else 0.45
        frequency_rate = weight * frequency_rate + (1 - weight) * self.frequency_rate
        phase_rate = weight * phase_rate + (1 - weight) * self.phase_rate
        return Hypothesis(now, peak, self.hits + 1,
                          max(-8000., min(8000., frequency_rate)),
                          max(-50., min(50., phase_rate)))


@dataclass(slots=True)
class Lane:
    visits: int = 0
    last_blind: int = -SCOUT_INTERVAL
    misses: int = 0
    hypotheses: list[Hypothesis] = field(default_factory=list)

    def observe(self, probe):
        """Return mode, selected peak, and fractional search area for this visit."""
        self.visits += 1
        self.hypotheses = [h for h in self.hypotheses if 0.0 < probe.time - h.time <= MAX_AGE_S]
        gates = [h.predict(probe.time) for h in self.hypotheses]
        area = min(1., sum(gate.area for gate in gates))

        if self.visits - self.last_blind >= SCOUT_INTERVAL:
            mode = "scout"
        elif not gates:
            return "idle", None, 0.
        else:
            eligible = tuple(p for p in probe.peaks if any(g.distance(p) <= 1. for g in gates))
            if eligible:
                self.misses = 0
                self.update(probe.time, eligible, gates, blind=False)
                return "guided", eligible[0], area
            self.misses += 1
            if self.misses < 2:
                return "guided", None, area
            mode = "rescue"

        self.last_blind = self.visits
        self.misses = 0
        if probe.peaks:
            self.update(probe.time, probe.peaks, gates, blind=True)
        else:
            self.hypotheses.clear()
        # Charge the full blind grid plus any guided work already done on rescue.
        return mode, next(iter(probe.peaks), None), 1. + (area if mode == "rescue" else 0.)

    def update(self, now, peaks, gates, *, blind):
        # An observed peak may update at most one hypothesis. A blind visit may
        # also seed previously unknown peaks. A guided visit can extend locks only.
        remaining = set(range(len(gates)))
        updated = []
        for peak in peaks:
            match = min(remaining, key=lambda j: (gates[j].distance(peak), j), default=None)
            if match is not None and gates[match].distance(peak) <= 1.:
                updated.append(self.hypotheses[match].update(now, peak))
                remaining.remove(match)
            elif blind:
                updated.append(Hypothesis(now, peak))
            if len(updated) == MAX_HYPOTHESES:
                break
        updated.extend(self.hypotheses[j] for j in sorted(remaining))
        self.hypotheses = updated[:MAX_HYPOTHESES]


def native_probes(native):
    source = native["source"]
    fs = source["sample_rate_hz"]
    anchor = native["clock_anchor"]["sample_counter"]
    half_probe = source["probe_ms"] / 2000.
    assert fs == 10_000_000 and source["probe_ms"] == 20
    probes = []
    for index, row in enumerate(source["probes"]):
        assert row["probe_start_ms"] == 0
        counter = row["valid_start_counter"] - anchor
        phase_us = ((counter * 750) % fs) / fs * PHASE_PERIOD_US
        peaks = [Peak(candidate["candidate_rank"], candidate["fractional_tracking_cfo_hz"],
                      (phase_us + (candidate["integer_epoch_sample"] +
                                   candidate["fractional_epoch_offset_samples"]) * 1e6 / fs)
                      % PHASE_PERIOD_US, candidate["fractional_margin"])
                 for candidate in row["candidates"] if candidate["passed_fractional_margin_gate"]]
        peaks.sort(key=lambda peak: (-peak.margin, peak.rank))
        probes.append(Probe(index, row["receiver_id"] + 1, row["channel"], row["actual_rf_hz"],
                            counter / fs + half_probe, tuple(peaks)))
    return sorted(probes, key=lambda probe: (probe.time, probe.receiver, probe.channel))


def replay(probes):
    lanes = defaultdict(Lane)
    emitted = []
    counts = Counter()
    difference_hz = []
    for probe in probes:
        mode, peak, area = lanes[probe.lane].observe(probe)
        counts[mode] += 1
        counts["search_area_units_upper"] += area
        # The archived blind winner serves only as a reference for these counts.
        if probe.peaks:
            counts["blind_reference_winners"] += 1
            counts[f"{mode}_with_reference"] += 1
        if peak is None:
            counts["omitted"] += bool(probe.peaks)
            continue
        emitted.append(probe.observation(peak))
        reference = probe.peaks[0]
        if peak == reference:
            counts["exact"] += 1
        else:
            counts["substituted"] += 1
            difference_hz.append(abs(wrap(peak.frequency - reference.frequency, FREQUENCY_PERIOD)))
    return emitted, counts, difference_hz


def fit(rows, bank):
    document, counts = track_document(rows)
    descriptors = cold.descriptors(document, bank)
    if descriptors is None:
        return {arm: {"status": "abstain", "reason": "no_curved_tracks"}
                for arm in ("c0", "fitted_c")}, counts
    bias = cold.bias_vote(descriptors)
    score, position, assignment, costs = cold.grid_vote(descriptors, bias)
    selected = np.flatnonzero(costs < 12.)
    counts.update(grid_score=float(score), selected_tracks=len(selected),
                  satellite_ids=descriptors["ids"][selected, assignment[selected]].tolist())
    arms = {}
    for arm in ("c0", "fitted_c"):
        estimate = cold.solve(descriptors, selected, assignment, bias, position,
                              fitted_c=(arm == "fitted_c"))
        if estimate["status"] == "estimate":
            estimate["latlon"] = latlon(estimate["xy"])
        else:
            estimate = {"status": "abstain", "reason": estimate["status"]}
        arms[arm] = estimate
    return arms, counts


def paired_effects(arms, control):
    comparisons = {}
    for arm, estimate in arms.items():
        blind = control[arm]
        if estimate["status"] == blind["status"] == "estimate":
            comparisons[arm] = dict(xy_distance_from_blind_km=math.dist(estimate["xy"], blind["xy"]),
                                    own_fit_rms_minus_blind_hz=estimate["rms_hz"] - blind["rms_hz"])
    return comparisons


def c_effect(arms):
    zero, fitted = arms["c0"], arms["fitted_c"]
    if zero["status"] != "estimate" or fitted["status"] != "estimate":
        return None
    return dict(fitted_minus_zero_rms_hz=fitted["rms_hz"] - zero["rms_hz"],
                endpoint_shift_km=math.dist(fitted["xy"], zero["xy"]))


def detection_summary(counts, differences):
    counts = dict(counts)
    probes = sum(counts.get(mode, 0) for mode in ("scout", "guided", "rescue", "idle"))
    reference = counts["blind_reference_winners"]
    return dict(counts, probes=probes,
                full_blind_visits_fraction=(counts.get("scout", 0) + counts.get("rescue", 0)) / probes,
                search_area_fraction_upper=counts["search_area_units_upper"] / probes,
                exact_winner_recall=counts["exact"] / reference,
                winner_reporting_fraction=(counts["exact"] + counts.get("substituted", 0)) / reference,
                substitute_abs_wrapped_cfo_hz=dict(p50=float(np.median(differences)),
                                                  p95=float(np.percentile(differences, 95)))
                if differences else None)


def run_case(case):
    start = time.perf_counter()
    root = INPUTS / case
    native = json.loads((root / "native.json").read_bytes())
    probes = native_probes(native)
    prepared = time.perf_counter()
    rows, counts, differences = replay(probes)
    scheduled = time.perf_counter()
    blind, meta, half_probe = winners(native)
    assert blind == [p.observation(p.peaks[0]) for p in probes if p.peaks]
    assert probes[-1].time + half_probe <= meta["duration_s"] + 1e-8
    bank, bank_info = cold.build_bank(case, meta, check_approximation=False)
    before_fit = time.perf_counter()
    arms, tracks = fit(rows, bank)
    fitted = time.perf_counter()
    blind_start = time.perf_counter()
    control, control_tracks = fit(blind, bank)
    blind_wall = time.perf_counter() - blind_start
    prefix = probes[:len(probes) // 2]
    prefix_rows, _, _ = replay(prefix)
    prefix_ids = {p.index for p in prefix}
    assert prefix_rows == [row for row in rows if row[0] in prefix_ids]
    detector = detection_summary(counts, differences)
    assert detector["blind_reference_winners"] == len(blind)
    assert len(rows) == detector["exact"] + detector.get("substituted", 0)
    assert len(blind) == len(rows) + detector.get("omitted", 0)
    timing = dict(load_and_decode_wall_s=prepared - start, scheduler_wall_s=scheduled - prepared,
                  bank_wall_s=before_fit - scheduled, two_arm_fit_wall_s=fitted - before_fit,
                  blind_two_arm_fit_wall_s=blind_wall)
    return (dict(case=case, wall_s=fitted - start, arms=arms, c_effect=c_effect(arms), timing=timing,
                 recording_duration_s=meta["duration_s"], orbit_bank=bank_info, detector=detector,
                 tracking=tracks, blind_control=dict(arms=control, tracking=control_tracks,
                                                     c_effect=c_effect(control)),
                 compared_with_blind=paired_effects(arms, control)), counts, differences)


def check():
    near = Peak(0, FREQUENCY_PERIOD / 2 - 500., PHASE_PERIOD_US - 2., .6)
    through_wrap = Peak(1, -FREQUENCY_PERIOD / 2 + 500., 1., .58)
    next_peak = Peak(0, -FREQUENCY_PERIOD / 2 + 1500., 4., .5)
    newcomer = Peak(0, 80_000., 600., .7)
    lanes = defaultdict(Lane)

    def visit(index, time, *peaks, receiver=1):
        probe = Probe(index, receiver, 1, 10.7e9, time, peaks)
        return lanes[probe.lane].observe(probe)

    assert visit(0, 0., near) == ("scout", near, 1.)
    mode, peak, cost = visit(1, 0.35, newcomer, through_wrap)
    assert mode == "guided" and peak is through_wrap and 0. < cost < 0.01
    assert visit(2, 0.7, next_peak)[0:2] == ("guided", next_peak)
    assert visit(3, 1.05, newcomer)[0:2] == ("guided", None)
    assert visit(4, 1.4, newcomer) == ("scout", newcomer, 1.)
    assert visit(5, 1.75)[0:2] == ("guided", None)
    mode, peak, cost = visit(6, 2.10, next_peak)
    assert mode == "rescue" and peak is next_peak and cost > 1.
    assert visit(7, 2.10, next_peak, receiver=2) == ("scout", next_peak, 1.)
    assert visit(8, 2.45)[0:2] == ("guided", None)
    assert visit(9, 2.80)[0:2] == ("rescue", None)
    assert visit(10, 3.15, next_peak) == ("idle", None, 0.)
    assert len(lanes) == 2 and all(len(lane.hypotheses) <= MAX_HYPOTHESES for lane in lanes.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "result.json")
    args = parser.parse_args()
    check()
    if args.check_only:
        print("Pilot scheduler checks passed")
        return
    results, counts, differences = [], Counter(), []
    for case in CASES:
        result, per_case, errors = run_case(case)
        results.append(result)
        counts.update(per_case)
        differences.extend(errors)
        print(f"{case} {result['wall_s']:.3f} s", flush=True)
    iq_report = HERE / "iq-check.json"
    iq_scope = dict(endpoint_input="Saved detector candidates; the supplemental waveform check does not feed positions.",
                    supplemental_result=iq_report.name if iq_report.is_file() else None)
    report = dict(
        method="Causal predictive pilot gates with periodic blind scouting and lost-lock rescue",
        timing_scope="Host wall time from decoded-input load through the guided full-record endpoint in both c arms, including candidate replay, prior orbit table and blind-control row validation; separate timed blind endpoint fit. Excludes IQ detection and radio acquisition.",
        cases=results,
        checks=dict(synthetic="passed", half_prefix_exact="8/8", blind_rows_match_shared_winners="8/8",
                    aggregate_detector=detection_summary(counts, differences),
                    c_ablation="Within each frontend, both arms share the accepted rows, candidate identities, assignments, priors other than c, grid and fit iteration limits.",
                    raw_iq=iq_scope),
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
