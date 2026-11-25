"""Prepare the saved DS30-0049 primary carrier-and-arrival intervention."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import json
from math import remainder
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from reports.ALGO08.v3 import empty_lane_arrival as arrival  # noqa: E402
from empty_recovery_0049 import restore_empty_lanes  # noqa: E402
from matched_donor_0049 import bind_derived  # noqa: E402
import matched_donor_0049_trial as trial  # noqa: E402
import signed_cfo_time_readout as signed  # noqa: E402


PLAN = "adcde673c80fd9a58a81380b90795b6e844f6f9ad236c945e83d4bdbc07354d3"
SEAL = "9971473052ea2c2d9b2f8db1a82e45f82fcd19f5c165af30dc6c351f361829f9"
RUNNER = "2aadda247333edc0b0e3b34bcd0d630e48e9ac5802337fae89c0f2efe8a42a02"


def primary_hits(predictions, installed):
    """Find complete original installed winners within the already frozen window."""
    found = {}
    limits = arrival.WINDOWS["primary"]
    for oid, query in predictions.items():
        lane = installed[oid]
        factor = lane["factor"]
        if factor is None:
            continue
        frequency = factor[arrival.HERTZ]
        phase = arrival.arrival_phase(lane["counter"], factor)
        if arrival.hits([query], frequency, phase, *limits)["interpolated"]:
            centre, = query["centers_hz"]
            found[oid] = dict(installed_minus_query_cfo_hz=frequency - centre,
                              installed_minus_query_arrival_samples=remainder(
                                  phase - query["phase"]["interpolated"], arrival.PERIOD))
    return found


def splice(stock, sparse, found, projection_sha256):
    """Apply the narrowed set using the complete tuples from the original repair."""
    _, all_empty = restore_empty_lanes(stock, sparse)
    inserted = [dict(row, **found[row["observation_id"]])
                for row in all_empty["inserted"] if row["observation_id"] in found]
    if not found or {row["observation_id"] for row in inserted} != found.keys():
        raise ValueError("Every primary hit must be an original sparse-empty short with an installed winner")
    by_oid = {row["observation_id"]: row["installed_tuple"] for row in inserted}
    original = signed.opportunities(sparse)
    probes = [dict(lane["row"], candidates=[by_oid[oid]]) if oid in by_oid else lane["row"]
              for oid, lane in original.items()]
    frequency, samples = arrival.WINDOWS["primary"]
    recipe = dict(
        schema="private-0049-primary-arrival-restoration-v1",
        scope="saved hindsight receiver simulation",
        sparse_native_sha256=all_empty["recipe"]["sparse_native_sha256"],
        installed_native_sha256=all_empty["recipe"]["installed_native_sha256"],
        original_carrier_plan_sha256=PLAN, original_arrival_seal_sha256=SEAL,
        primary_projection_sha256=projection_sha256, signed_cfo_limit_hz=frequency,
        wrapped_arrival_limit_samples=samples, unchanged_anchors=True, unchanged_opportunities=True,
        selection="actual installed winner within the pre-existing candidate-only primary query",
        insertion_sha256=signed.canonical(inserted),
    )
    packet, custody = bind_derived(sparse, probes, recipe)
    final = signed.opportunities(packet)
    signed.bind_pair(sparse, packet, original, final)
    if list(original) != list(final) or any(
            final[key]["row"] != (dict(original[key]["row"], candidates=[by_oid[key]])
                                 if key in by_oid else original[key]["row"]) for key in original
    ):
        raise ValueError("Derived packet changed original rows outside the enrolled insertions")
    return packet, dict(custody, inserted=inserted, inserted_count=len(inserted),
                        original_winners=all_empty["original_winners"], replaced=0, dropped=0,
                        all_empty_insertions=all_empty["inserted_count"],
                        derived_winners=sum(lane["factor"] is not None for lane in final.values()),
                        unchanged_lanes=len(original) - len(inserted),
                        inserted_by_receiver=dict(Counter(str(row["receiver"]) for row in inserted)))


def derive(stock, sparse):
    plan = signed.document(DATA / "empty-graph-rescue-development-plan.json.gz", PLAN)
    seal = signed.document(DATA / "empty-lane-arrival-seal.json", SEAL)
    if (plan["cohort"] != "development" or plan["ledger_sha256"] != seal["ledger_sha256"]
            or seal["prediction_inputs"]["development"] != PLAN):
        raise ValueError("The original development proposal registration differs")
    candidate, installed = map(signed.opportunities, (sparse, stock))
    signed.bind_pair(stock, sparse, installed, candidate)
    case = plan["cases"][trial.CASE]
    empty, predictions, proof = arrival.prepare(case, candidate)
    proof.update(empty_short=len(empty), candidate_sha256=signed.canonical(sparse))
    if proof != seal["cases"][trial.CASE] or proof["candidate_sha256"] != case["candidate_native_sha256"]:
        raise ValueError("The exact pre-reference carrier and arrival projections did not reproduce")
    coverage = arrival.score_group(empty, predictions, installed)
    found = primary_hits(predictions, installed)
    counts = coverage["windows"]["primary"]
    if (len(empty), len(predictions), coverage["installed_positive_denominator"],
            coverage["installed_positive_queries"], counts["carrier_only"], counts["interpolated"],
            len(found)) != (1105, 300, 104, 22, 14, 11, 11):
        raise ValueError("The primary receiver audit differs from the frozen measured scope")
    packet, audit = splice(stock, sparse, found, proof["projection_sha256"])
    if (audit["original_winners"], audit["derived_winners"], audit["unchanged_lanes"]) != (600, 611, 1853):
        raise ValueError("The intervention must retain every original winner in the full ordered stream")
    return packet, dict(audit, projection=proof, installed_positive_queries=coverage["installed_positive_queries"],
                        carrier_hits=counts["carrier_only"], joint_hits=counts["interpolated"])


EXPERIMENT = SimpleNamespace(
    stem="ds30-0049-arrival-primary", derive=derive, ledger="inserted", ledger_digest="insertion_sha256",
    label="inserted", source=Path(__file__).name, priority="idle", joint=True,
    transfer_sources=("empty_lane_arrival.py", "directed_donor.py"),
)


def comparator(plan):
    historical = signed.document(DATA / f"{trial.RESTORATION.stem}.json.gz", trial.PREVIOUS[trial.RESTORATION.stem])
    score = historical["score"]
    if score["decision"] != "complete" or any(
        score["crossover_inputs"][key] != plan[key] for key in ("sparse_native_sha256", "installed_native_sha256")
    ):
        raise ValueError("The all-104 control must use both exact original receiver packets")
    return {name: {key: row[key] for key in ("sparse_m", "counterfactual_m", "installed_m")}
            for name, row in score["arms"].items()}


def preflight(root, plan_pin):
    stream = StringIO()
    with redirect_stdout(stream):
        trial.worker(root, plan_pin, EXPERIMENT, smoke=True)
    result = json.loads(stream.getvalue())
    plan = trial.document(root / "plan.json", plan_pin)
    if (result != dict(case=trial.CASE, changed=11, refs=48, acquired=0, waveform_reads=0, solver_runs=0)
            or (root / "substituted").exists()):
        raise ValueError("Expected only a verified no-solve preflight")
    print(trial.write(root / "ready.json", dict(
        result, plan_sha256=plan_pin, payload=plan["change"]["derived_native_sha256"],
        protocol=trial.protocol(EXPERIMENT), runner_sha256=RUNNER, original_archive=plan["original_archive"],
        all_104_receipt_sha256=trial.PREVIOUS[trial.RESTORATION.stem],
        archived_error_m=comparator(plan["change"]["recipe"]), survey_reads=0, benchmark_children=0,
    )))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    args = parser.parse_args()
    if trial.identifier(Path(trial.__file__)) != RUNNER:
        raise ValueError("The existing certified saved driver changed")
    if args.action == "prepare":
        trial.prepare(args.root, EXPERIMENT)
    elif args.pin:
        preflight(args.root, args.pin)
    else:
        parser.error("Supply the prepared plan digest")
