"""Replay the final repair conjunction and bound a redirect on saved traces."""

from argparse import ArgumentParser
from hashlib import sha256
import gzip
import json
from pathlib import Path

from leo.analysis.localization_v3.history_policy import ARMS, pair_passes


MEASUREMENTS = Path(__file__).with_name("measurements")
HOLDOUT = "e8c0b5cea1efa3940e8c5ca8c9301405234c48aeb645d073a22ae2908f20f280"
HANDOFF = "192ee623532d238f589737a46d0472ec6ddd11fa14aa109468236426b45278ec"
PHYSICAL_CHECK = "6922f4bb992a339fae2bc532c69618d41243dbc24e6e3ddf8952410805421b30"
NORTH = "0866d18084d5fd14466b0a3a9847fcb43c3e78d089515692dfec175f4ec442b3"
POLICY = "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1"
JOINT_REFUSAL = "repair_original_joint_pair_gate"
PREFIX = ("cold_clocks", "initial_gate_clocks", "salvage_clocks", "predictive_clocks",
          "finish_clocks", "repair_prepare_clocks", "repair_fit_clocks")


def fitted_first(fit_arm, *, include_linear, half_width_km):
    """Prototype for completed fits. The release applies the same gate to each arm."""
    fitted = fit_arm("fitted_c")
    options = dict(include_linear=include_linear, half_width_km=half_width_km)
    # Both terms of the conjunction are identical when given the same arm.
    if not pair_passes(dict.fromkeys(ARMS, fitted), **options):
        return {"fitted_c": fitted}, False
    both = {"c0": fit_arm("c0"), "fitted_c": fitted}
    return both, pair_passes(both, **options)


def gate_record(record):
    """Recover the gate inputs represented by a completed arm readout."""
    tracks = {}
    for group in ("curved", "linear"):
        total = record[f"{group}_points"]
        good = record[f"compatible_{group}_points"]
        failures = record[f"failed_{group}"]
        if not (0 <= good <= total and bool(failures) == (good < total)
                and len(failures) <= total - good):
            raise ValueError(f"Invalid {group} gate readout")
        tracks[group] = ([{"compatible": True}] if good else []) + [
            {"compatible": False} for _ in failures
        ]
    return dict(gates={"tracks": tracks["curved"]}, linear_gates=tracks["linear"],
                endpoint_east_north_km=record["east_north_km"],
                final_phase_change_s=record["final_phase_change_s"])


def compare_attempt(attempt, half_width_km):
    repair = attempt["repair"]
    before, after = attempt["finish"], repair["finish"]

    def options(arms):
        return dict(include_linear=any(arms[arm]["linear_points"] for arm in ARMS),
                    half_width_km=half_width_km)

    before_passes, after_passes = (
        pair_passes({arm: gate_record(arms[arm]) for arm in ARMS}, **options(arms))
        for arms in (before, after)
    )
    complete = repair["status"] == "complete" and repair["reason"] is None
    rejected = repair["status"] == "rejected" and repair["reason"] == JOINT_REFUSAL
    if (repair["attempted_refits"] != 1 or before_passes or attempt["pair_passes"] is not False
            or not (complete or rejected) or after_passes != complete):
        raise ValueError("The saved repair disagrees with the matched two-arm gate")
    visited = []

    def replay(arm):
        visited.append(arm)
        return gate_record(after[arm])

    records, short_passes = fitted_first(replay, **options(after))
    if short_passes != after_passes or (short_passes and tuple(records) != ARMS):
        raise ValueError("Fitted-first changed repair acceptance or published arm order")

    return dict(cold_route=attempt["cold"]["routing"], cold_gaps=attempt["cold"]["gaps"],
                curved_support={name: attempt["support"][name]
                                for name in ("full_curved", "initial_curved", "curved_restored", "rechecked_curved")},
                repair_status=repair["status"], repair_reason=repair["reason"],
                rejection_counts=repair["rejection_counts"], first=before, repaired=after,
                first_passes=before_passes, repair_passes=after_passes, fitted_first_visits=visited,
                repair_fit_clocks=attempt["repair_fit_clocks"])


def clock_bounds(attempt, named_clock, handoff_clock):
    bounds = {}
    for unit in ("cpu_s", "elapsed_s"):
        remaining = attempt["candidate_pre_evidence_clocks"][unit]
        excess = handoff_clock[unit] - named_clock[unit]
        after = {}
        for stage in PREFIX:
            charge = attempt[stage][unit]
            if not 0 <= charge <= remaining:
                raise ValueError("Expected disjoint measured lean scopes")
            remaining -= charge
            after[stage] = remaining
        bounds[unit] = dict(handoff_excess=excess, entire_lean_after=after,
                            entire_repair_refit=attempt["repair_fit_clocks"][unit],
                            minimum_after_repair_saving=excess - attempt["repair_fit_clocks"][unit],
                            remaining_named_fallback=attempt["fallback_clocks"][unit])
    return bounds


def load(path, pin):
    body = path.read_bytes()
    if path.suffix == ".gz":
        body = gzip.decompress(body)
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Unreviewed saved receipt {path}")
    return json.loads(body)


def reduce(physical_check):
    if sha256(Path(pair_passes.__code__.co_filename).read_bytes()).hexdigest() != POLICY:
        raise ValueError("Expected the reviewed release gate")
    holdout = load(MEASUREMENTS / "unseen-saved-holdout-0255.json.gz", HOLDOUT)
    handoff = load(MEASUREMENTS / "nomination-handoff-0255.json.gz", HANDOFF)
    healthy = load(physical_check, PHYSICAL_CHECK)["solves"][0]["lean_attempts"][0]
    north = load(MEASUREMENTS / "history-risk-raw.json.gz", NORTH)
    north = north["raw"]["verified-result-grid.json"]["value"]["route"]["lean_attempts"][0]
    baseline, routed = (holdout["jobs"][arm]["clock"] for arm in ("installed", "routed"))
    original = holdout["candidate_traces"]["risk-route.json"]["solves"][0]["lean_attempts"][0]
    remedied = handoff["risk"]["solves"][0]["lean_attempts"][0]
    half_width = holdout["jobs"]["installed"]["publication"]["science"]["receipt"]["region"]["width_km"] / 2
    old = compare_attempt(original, half_width)
    current = compare_attempt(remedied, half_width)
    if any(old[name] != current[name] for name in ("first", "repaired", "rejection_counts", "repair_reason")):
        raise ValueError("Expected identical repair evidence before and after handoff")
    if not all(handoff["checks"].values()) or not all(holdout["checks"].values()):
        raise ValueError("Expected verified ordinary and handoff publications")
    if north["cold"]["routing"] != "ambiguous_gap" or north["decision"] != "complete" or not north["pair_passes"]:
        raise ValueError("Expected an accepted ambiguous-gap diagnostic")
    return dict(
        schema="leo.research.early-lean-refusal.v1", scope="counterfactual replay of saved gate inputs",
        input_sha256=dict(holdout=HOLDOUT, nomination_handoff=HANDOFF, physical_0169=PHYSICAL_CHECK,
                          north=NORTH, release_pair_policy=POLICY),
        fresh_saved_workers=0, fresh_arm_fits=0, original_waveform_reads=0, backing_archive_reads=0,
        cases={"DS30-0255": current, "DS30-0169": compare_attempt(healthy, 12.5)},
        archived_false_redirects={
            "initial_pair_failed": {"case": "DS30-0169", "later_repair_passes": True},
            "ambiguous_cold_gap": {"case": "North simulation", "cold_route": north["cold"]["routing"],
                                   "gaps": north["cold"]["gaps"], "original_pair_passes": north["pair_passes"]},
        },
        measured_0255_worker_clocks=dict(named=baseline, original_routed=routed, handoff=handoff["clock"]),
        measured_0255_clocks_before_evidence={
            key: remedied[key] for key in (*PREFIX, "candidate_pre_evidence_clocks", "fallback_clocks")},
        provisional_salvage_0255={key: remedied["provisional_salvage"][key] for key in (
            "seed_gate_clocks", "isolation_clocks", "fit_calls", "status", "reason")},
        earlier_0255_publication=dict(geographic=holdout["geographic"], checks=handoff["checks"],
                                       owner_counts={arm: holdout["owner_changes"][arm]["shared"] for arm in ARMS}),
        optimistic_0255_upper_bounds=clock_bounds(remedied, baseline, handoff["clock"]),
    )


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("physical_0169_risk_trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(reduce(args.physical_0169_risk_trace), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
