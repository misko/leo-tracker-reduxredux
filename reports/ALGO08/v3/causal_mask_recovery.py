"""Test causal paid-history rules for restoring skipped short receiver lanes."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from aperture_trial import ARMS, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from stereo_lane_schedule import StereoSchedule
from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs


HERE = Path(__file__).resolve().parent
MASK_ROOT = Path("/dev/shm/leo-v3-modest-mask-results.0qfAjbDv")
ORIGINALS = {
    "DS30-0008": (Path("/dev/shm/leo-cumulative-grid-projection-01/dense-pair/detections.json"),
                   "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"),
    "DS30-0016": (Path("/dev/shm/leo-cumulative-grid-projection-01/weak/detections.json"),
                   "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "south": (Path("/dev/shm/leo-past-anchor-held-south/fast-scan-automatic-work/algo08-v2-3d8fc8f57b655c3425248304c2776096/detections.json"),
              "a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"),
}
MASK_PINS = {
    "DS30-0008": ("09e83c2bb448351638bcc7e7be164025e7a793dc58df61d582e77d58213760dc",
                   "c1fa8fc87db8c2836c616b843d99527c8ec317264d7cd638bb280f70e61a7f1b",
                   "7ccb374875fee65bd88e24236b18b59b6d5aac2aa8443e07b42d2b5910cd9cc7"),
    "DS30-0016": ("75b929db168a7671d3b5e71597033a6548c0b15d5f82d0f8d64eb90d7a89dba9",
                   "5ece20b49e82a5362eb8f13345078a1eb2ab2492c367875c396690f842154640",
                   "05be8813345cf5be010c5525cd1144d0e80df56c036bf08d88673fb0f2e39a7d"),
    "south": ("04c2563b55ce2230ecd4bb4cdf3d17e68449bd819d1a7a1ba2bcac9b6b43d3ef",
              "707c3341015802584761d6858c79a1e65af5b853f100fafe68ea62c5d2af89de",
              "f44011f4fef661f3ccb17c0f4bce6e69c3aa456fdde77751bef51afc11378150"),
}
RULES = ("recent", "smooth")
FRACTIONS = ((1, 64), (1, 8), (1, 4), (3, 8))
HORIZON = 80_000_000
TICKS_PER_SECOND = 10_000_000
SLOPE = 8_000


def supported(history, now, rule):
    if not history:
        return False
    end, last = history[-1]
    if last is None or not 0 < now-end <= HORIZON:
        return False
    if rule == "recent":
        return True
    if len(history) < 2:
        return False
    start, previous = history[-2]
    return (previous is not None and 0 < now-start <= HORIZON
            and abs(last-previous)*TICKS_PER_SECOND <= SLOPE*(end-start))


class Recovery:
    def __init__(self, rule, fraction):
        self.rule, self.fraction = rule, fraction
        self.history = defaultdict(lambda: deque(maxlen=2))
        self.omissions, self.purchases = Counter(), Counter()

    def buy(self, lane, counter):
        """Decide at an omitted lane from metadata and previously paid base data."""
        self.omissions[lane] += 1
        numerator, denominator = self.fraction
        allowance = self.omissions[lane]*numerator//denominator
        if self.purchases[lane] >= allowance or not supported(self.history[lane], counter, self.rule):
            return False
        self.purchases[lane] += 1
        return True

    def observe_base(self, lane, counter, cfo):
        history = self.history[lane]
        if history and history[-1][0] >= counter:
            raise ValueError("Nonincreasing paid hardware clock")
        history.append((counter, cfo))


def replay(native, rule, fraction):
    start = process_time()
    schedule, policy = StereoSchedule("target"), Recovery(rule, fraction)
    skipped, bought = defaultdict(list), defaultdict(list)
    for visit, pair in visit_pairs(native["source"]["probes"]):
        p, _ = pair
        stream = (p["edge"], p["channel"], p["actual_rf_hz"])
        _, omitted_radio = schedule.next(stream)
        for p in pair:
            radio, counter, factors = p["receiver_id"], p["valid_start_counter"], p["candidates"]
            lane = (radio, *stream)
            if radio == omitted_radio:
                if factors:
                    raise ValueError("The routing replay must use censored target-mask observations")
                skipped[lane].append((visit, radio))
                if policy.buy(lane, counter):
                    bought[lane].append((visit, radio))
            else:
                if len(factors) > 1 or any(not f["passed_fractional_margin_gate"] for f in factors):
                    raise ValueError("The base envelope must contain original local receiver winners")
                policy.observe_base(lane, counter, factors[0]["fractional_tracking_cfo_hz"] if factors else None)
    clocks = process_time()-start
    return dict(rule=rule, fraction=list(fraction), policy_cpu_s=clocks,
                lanes=[dict(lane=list(lane), omitted=slots, bought=bought[lane]) for lane, slots in skipped.items()])


def uniform(slots, purchases):
    """Compare exact total purchases within each lane, at chronological bin centers."""
    n = len(slots)
    if not 0 <= purchases <= n:
        raise ValueError("Matched purchase count outside omitted opportunities")
    return [slots[(2*i+1)*n//(2*purchases)] for i in range(purchases)]


def build_plan(output):
    machine = host()
    output.mkdir()
    cases = {}
    for case, (target_pin, _, _) in MASK_PINS.items():
        native = read(checked(MASK_ROOT / case / "target-input.json", target_pin))
        inventories(native)
        if native["source"]["sample_rate_hz"] != TICKS_PER_SECOND:
            raise ValueError("Does not use the expected hardware counter frequency")
        cases[case] = dict(target_bytes_sha256=target_pin,
                           schedules=[replay(native, rule, fraction) for rule in RULES for fraction in FRACTIONS])
    write(output / "plans.json", dict(machine=machine, cases=cases, read_omitted_signals_or_owners=False,
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "causal-mask-recovery-protocol.md").read_bytes()).hexdigest()))


def observe_cases(case):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.selective_capture import same_support

    root = MASK_ROOT / case
    target_pin, binding_pin, sealed_pin = MASK_PINS[case]
    full_path, full_pin = ORIGINALS[case]
    target = read(checked(root / "target-input.json", target_pin))
    native = read(checked(full_path, full_pin))
    binding = read(checked(root / "binding.json", binding_pin))
    saved = read(checked(root / "target-sealed.json", sealed_pin))
    source = native["source"]
    if (canonical_digest(native) != binding["binding"]["original_native_sha256"]
            or canonical_digest(target) != saved["mask"]["native_sha256"]
            or source["raw_recording_authority_digest"] != binding["binding"]["raw_authority"]):
        raise ValueError("Mismatched original factor and ownership panel")
    same_support(native, target)
    full_owners = {arm: {v[0] for v in rows} for arm, rows in binding["controls"]["full"]["selected_rows"].items()}
    omitted = {tuple(row) for row in saved["mask"]["skipped_slots"]}
    if len(omitted) != saved["mask"]["skipped_native_lanes"]["short_primary"]:
        raise ValueError("Historical mask clock does not close")
    positives, oracle = set(), {arm: set() for arm in ARMS}
    for before, after in zip(source["probes"], target["source"]["probes"], strict=True):
        slot = (before["visit_index"], before["receiver_id"])
        if slot not in omitted:
            if before != after:
                raise ValueError("A base-paid observation changed in the target mask")
            continue
        if before["candidates"]:
            positives.add(slot)
            key = f"{source['session_id']}:{slot[1]}:{before['valid_start_counter']}".encode()
            oid = "sha256:"+sha256(key).hexdigest()
            for arm in ARMS:
                if oid in full_owners[arm]:
                    oracle[arm].add(slot)
    return omitted, positives, oracle, saved["budget"]["per_short_cpu_s"]


def compare(plan, omitted, positives, oracle, rate):
    selected, uniform_slots, all_slots = set(), set(), set()
    expected = dict.fromkeys(ARMS, 0.0)
    for lane in plan["lanes"]:
        slots, bought = ([tuple(slot) for slot in lane[key]] for key in ("omitted", "bought"))
        pool, extra = set(slots), set(bought)
        if not extra <= pool or all_slots.intersection(pool) or len(bought) != len(extra):
            raise ValueError("Invalid or duplicate paid opportunity")
        all_slots.update(pool)
        selected.update(extra)
        uniform_slots.update(uniform(slots, len(bought)))
        for arm in ARMS:
            expected[arm] += len(bought)*len(oracle[arm] & pool)/len(pool)
    if all_slots != omitted or len(selected) != len(uniform_slots):
        raise ValueError("Replay differs from the original omission universe or the matched comparator")
    purchased = len(selected)
    owner = {arm:dict(recalled=len(selected & oracle[arm]), uniform=len(uniform_slots & oracle[arm]), expected=expected[arm],
                      positives_outside_owner=len(selected & positives - oracle[arm]), possible=len(oracle[arm]))
             for arm in ARMS}
    gross = (len(omitted)-purchased)*rate
    return dict(rule=plan["rule"], fraction=plan["fraction"], recovered_calls=purchased, owner=owner,
                positive_buys=len(selected & positives), empty_buys=purchased-len(selected & positives),
                uniform_positive_buys=len(uniform_slots & positives), policy_cpu_s=plan["policy_cpu_s"],
                estimated_recovery_call_cpu_s=purchased*rate, estimated_remaining_native_saving_s=gross,
                remaining_after_policy_s=gross-plan["policy_cpu_s"])


def promising(measurements, index):
    dense = measurements["DS30-0008"]["rows"][index]
    if dense["remaining_after_policy_s"] < 2.735 or any(
        arm["recalled"] < arm["possible"]/2
        or arm["recalled"]-max(arm["uniform"], arm["expected"]) < arm["possible"]*.10
        for arm in dense["owner"].values()
    ):
        return False
    return all(all(arm["recalled"] > 0 and arm["recalled"] >= max(arm["uniform"], arm["expected"])
                   for arm in measurements[case]["rows"][index]["owner"].values()) for case in ("DS30-0016", "south"))


def score(output):
    plan_path = output / "plans.json"
    plans = read(plan_path)
    if plans["source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Plan code changed before scoring")
    measurements = {}
    for case, row in plans["cases"].items():
        omitted, positives, oracle, rate = observe_cases(case)
        rows = [compare(p, omitted, positives, oracle, rate) for p in row["schedules"]]
        measurements[case] = dict(rows=rows, omitted=len(omitted), positives=len(positives),
                                  oracle={arm:len(slots) for arm, slots in oracle.items()}, unit_short_cpu_s=rate,
                                  parent_pins=MASK_PINS[case], original_native_sha256=ORIGINALS[case][1])
    expected_rows = len(FRACTIONS)*len(RULES)
    candidates = [i for i in range(expected_rows) if promising(measurements, i)]
    selected = min(candidates, key=lambda i: (measurements["DS30-0008"]["rows"][i]["recovered_calls"], i)) if candidates else None
    write(output / "score.json", dict(cases=measurements, selected=selected, waveform_calls=0,
          plan_sha256=sha256(plan_path.read_bytes()).hexdigest(), protocol_sha256=plans["protocol_sha256"],
          dense_acquisition_saving_gates=[4.616, 2.735]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "score"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"plan": build_plan, "score": score}[args.stage](args.output)
