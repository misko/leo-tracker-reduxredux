"""Eligibility and paid-envelope audit for retaining empty-lane verifier state."""

from collections import Counter
from dataclasses import dataclass
from gzip import decompress
from hashlib import sha256
import json
from math import fsum, isfinite, remainder
from pathlib import Path
from statistics import median
from struct import pack
import sys

from .directed_query_budget import budget
from .receiver_solver_targets import first30, held_clocks


HERE = Path(__file__).resolve().parent / "measurements"
RATE, PERIOD, NATIVE_PERIOD = 10_000_000, 40_000/3, 13_333
FIRST, LAST = 88, 88 + 64*44 - 1
PINS = {
    "first30-empty-call-roof.json.gz": "6edf7f54ff0689eb27712cad780d7539a9fa8dc7f95c3d7dd379641580225eeb",
    "empty-graph-rescue-development-plan.json.gz": "adcde673c80fd9a58a81380b90795b6e844f6f9ad236c945e83d4bdbc07354d3",
    "empty-graph-rescue-held-seal.json": "b8cafc01015ec183de6344d924cbe2eda9d49b5113f7d49d66385fdd68def722",
    "empty-graph-rescue-development-score.json": "2950527d8034121ba87a7960dd42745f31d05a5d8a467369499d30e4638d3778",
    "empty-graph-rescue-held-score.json": "77ad07ee34fe5618af6c8293ea91d1ac11d3d20c46c4c55f0a4117e855b6d6d0",
    "empty-lane-arrival-seal.json": "9971473052ea2c2d9b2f8db1a82e45f82fcd19f5c165af30dc6c351f361829f9",
    "receiver-solver-targets-next16.json": "aba4ab473fb2055a5240c3e64d66ab95c10b69dc171f15158d9600aebc48d8bf",
    "sparse8-native-profile.json": "c050491c6628b3f76a364917d388878580269a4cc70e07fd0f6b9a5ee3cb157b",
    "directed-verifier.json.gz": "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b",
}


def checked(path, expected):
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected:
        raise ValueError(f"Changed saved metadata: {path}")
    return body


def saved(name):
    body = checked(HERE/name, PINS[name])
    return json.loads(decompress(body) if name.endswith(".gz") else body)


@dataclass(frozen=True)
class Seed:
    epoch: int
    signed_hz: float
    offset: float

    def __post_init__(self):
        if (not 0 <= self.epoch < NATIVE_PERIOD or not isfinite(self.signed_hz)
                or abs(self.signed_hz) >= RATE/2 or not isfinite(self.offset) or abs(self.offset) > 2.):
            raise ValueError("Invalid native epoch/CFO operand")

    def exact_state(self):
        return self.epoch, pack(">dd", self.signed_hz, self.offset)


@dataclass(frozen=True)
class Correlation:
    opportunity_id: str
    iq_sha256: str | None
    pilot_sha256: str | None
    arithmetic: str | None
    seed: Seed

    def has_bound_input(self):
        return bool(self.iq_sha256 and self.pilot_sha256 and self.arithmetic)

    def reusable_with(self, other):
        # This is the same-signed-product predicate, not a full-verifier acceptance.
        # `arithmetic` identifies the original/unmodified signal, representation,
        # mixer, oscillator and exact/rolled reduction path, not a generic ABI version.
        return (self.has_bound_input()
                and (self.opportunity_id, self.iq_sha256, self.pilot_sha256, self.arithmetic) ==
                (other.opportunity_id, other.iq_sha256, other.pilot_sha256, other.arithmetic)
                and self.seed.exact_state() == other.seed.exact_state())


def native_seed(counter, phase, hz):
    epoch = ((phase - (3*counter % 40_000)/3) % PERIOD) % NATIVE_PERIOD
    nearest = round(epoch)
    return Seed(nearest % NATIVE_PERIOD, hz, epoch-nearest)


def query(entry):
    bracket, = entry["brackets"]
    hz, = bracket["signed_centers_hz"]
    counter = entry["counter"]
    left, right = bracket["left"], bracket["right"]
    a, b = counter-left["counter"], right["counter"]-counter
    if not (0 < a <= 2*RATE and 0 < b <= 2*RATE and a/(a+b) == bracket["right_weight"]
            and left["graph_alias_lift"] == right["graph_alias_lift"]):
        raise ValueError("Not the frozen unique signed bracket")
    p, q = left["signed_cfo_hz"], right["signed_cfo_hz"]
    if hz != p + a/(a+b)*(q-p):
        raise ValueError("Signed CFO does not match the sealed donor interpolation")
    phase = [((3*d["counter"] % 40_000)/3 + d["integer_epoch_sample"] + d["fractional_epoch_offset_samples"]) % PERIOD
             for d in (left, right)]
    center = (phase[0] + a/(a+b)*remainder(phase[1]-phase[0], PERIOD)) % PERIOD
    return b, native_seed(counter, center, hz), native_seed(counter, (center + PERIOD/4) % PERIOD, hz)


def frames(epoch, *, short):
    """Exact native sample intervals for one integer stencil center, no fractional halo."""
    extent, limit = (80_000, 5) if short else (200_000, 15)
    starts = (epoch + (n*40_000+1)//3 for n in range(limit))
    return {(start+FIRST, start+LAST) for start in starts if start+LAST < extent}


def stencil(seed, *, short):
    return set().union(*(frames((seed.epoch + delta) % NATIVE_PERIOD, short=short) for delta in range(-2, 3)))


def plan_geometry(case):
    count = Counter()
    delays = []
    visits = set()
    for oid, entry in case["opportunities"].items():
        if entry["status"] != "unique_signed_bracket":
            continue
        if oid != entry["observation_id"] or entry["radio"] not in (0, 1):
            raise ValueError("Wrong saved target identity")
        delay, primary, quarter = query(entry)
        delays.append(delay)
        visits.add(entry["visit_index"])
        # The signed query roster identifies the lane, but contains no cached waveform state.
        requested = Correlation(oid, None, None, None, primary)
        control = Correlation(oid, None, None, None, quarter)
        short, full = stencil(primary, short=True), stencil(primary, short=False)
        quarter_rows = stencil(quarter, short=False)
        if not short <= full:
            raise ValueError("The identical-query short stencil is outside the complete stencil")
        count.update(queries=1, hypothetical_identical_prefix_integer_rows=len(short),
                     full_integer_rows=len(full), required_new_identical_integer_rows=len(full-short),
                     quarter_control_shared_integer_rows=len(full & quarter_rows),
                     identical_quarter_native_seed=int(requested.seed.exact_state() == control.seed.exact_state()),
                     same_time_fusible=int(delay <= 0), exact_retained_stencil_proven=int(requested.has_bound_input()))
    return dict(count, queries=len(delays), right_wait_seconds=dict(min=min(delays)/RATE, median=median(delays)/RATE,
                                                                   max=max(delays)/RATE) if delays else None,
                same_time_fusible=count["same_time_fusible"], exact_retained_stencil_proven=count["exact_retained_stencil_proven"],
                target_stereo_visits=len(visits))


def field_rows(campaign):
    measured = {c["case"]: c for c in first30()}
    native = saved("first30-empty-call-roof.json.gz")
    first = []
    for c in native["cases"]:
        r = measured.pop(c["case"])
        if r["pins"]["result"] != c["candidate_join_sha256"] or r["pins"]["native"] != c["native_sha256"]:
            raise ValueError("Original clock and native opportunity identity differ")
        short = c["modes"]["short_primary"]
        first.append(dict(case=c["case"], installed_s=r["stock_wall_s"], candidate_s=r["actual_wall_s"],
                          native_s=r["native_detector_s"], solver_s=r["phases"]["outer"]["elapsed_s"]["solve"],
                          short_s=short["elapsed_ns"]/1e9, short_lanes=short.get("lanes", 0),
                          empty=short.get("empty_lanes", 0), candidate_native_sha256=c["native_sha256"]))
    later = held_clocks(campaign.resolve(strict=True), split_apertures=True)
    frozen = saved("receiver-solver-targets-next16.json")["cases"]
    if len(later) != 16 or any({k: actual[k] for k in old} != old for old, actual in zip(frozen, later, strict=True)):
        raise ValueError("Held clocks no longer describe the sealed independent 16")
    return first, [dict(r, empty=r["short_lanes"]-r["short_positives"]) for r in later]


def pricing(rows, count):
    price = [(r["installed_s"], r["candidate_s"], r["native_s"], r["solver_s"], count(r)) for r in rows]
    return budget(price, 1.5, 1.4)


def measurements():
    profile = saved("sparse8-native-profile.json")
    v = saved("directed-verifier.json.gz")["groups"]
    return dict(short_profile={case: dict(empty_lanes=x["summary"]["empty"]["lanes"],
                    empty_stage_cpu_ns=x["summary"]["empty"]["exclusive_per_lane_cpu_ns"],
                    empty_lanes_loaded=sum(not row["factor_hex"] and any(r["clock_on"][9] for r in row["rounds"]) for row in x["rows"]))
                for case, x in profile["cases"].items()},
                directed={case: {name: {k: report[k] for k in ("positive_cpu_ms", "negative_cpu_ms", "mean_stages_ms")}
                                 for name, report in x["checks"].items() if name in ("oracle_decode_1", "nominal_decode_1", "nominal_fixed_guard_1", "decoy_fixed_guard_1")}
                          for case, x in v.items()})


def run(campaign):
    first, later = field_rows(campaign)
    seal = saved("empty-graph-rescue-held-seal.json")
    plan = json.loads(decompress(checked(Path(seal["full_prediction_path"]), seal["full_prediction_sha256"])))
    development = saved("empty-graph-rescue-development-plan.json.gz")
    if plan["ledger_sha256"] != seal["ledger_sha256"] or set(plan["cases"]) != set(seal["cases"]):
        raise ValueError("Unexpected roster in the full held query plan")
    plans = development["cases"] | plan["cases"]
    scores = {case: r["native"]["counts"].get("selected", 0) for scope in ("development", "held")
              for case, r in saved(f"empty-graph-rescue-{scope}-score.json")["cases"].items()}
    phase_seal = saved("empty-lane-arrival-seal.json")["cases"]
    for row in first:
        case = row["case"]
        candidate = plans.pop(case)
        geometry = plan_geometry(candidate)
        if (row["candidate_native_sha256"] != candidate["candidate_native_sha256"]
                or row["empty"] != candidate["empty_short_count"] or geometry["queries"] != scores[case]):
            raise ValueError("Case clocks and bracket evidence do not share native identity and paid empties")
        if case in phase_seal and (geometry["queries"] != phase_seal[case]["queries"]
                                   or abs(geometry["right_wait_seconds"]["median"]-phase_seal[case]["right_neighbor_median_s"]) > 1e-12):
            raise ValueError("Typed geometry differs from the original sealed phase cohort")
        row.update(geometry)
        row["untimed_selected_subset_outer_bound_s"] = row["short_s"] if geometry["queries"] else 0.
    for row in later:
        row.update(queries=None, same_time_fusible=0, exact_retained_stencil_proven=None,
                   untimed_selected_subset_outer_bound_s=row["short_s"] if row["empty"] else 0.)
    if plans or set(scores) != {r["case"] for r in first}:
        raise ValueError("The sealed query lists do not cover exactly the developmental 30")
    return dict(pins=PINS, full_plan=seal["full_prediction_sha256"], first30=first, held16=later,
                first30_prices=pricing(first, lambda r: r["queries"]),
                held16_every_empty_query_stress=pricing(later, lambda r: r["empty"]),
                all46_every_held_empty_query_stress=pricing(first+later, lambda r: r["empty"] if r["queries"] is None else r["queries"]),
                note="The 16 held query plans are absent. Stress all paid empty short calls there at one query each.", **measurements())


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True, allow_nan=False))
