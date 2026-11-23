"""Score directed donor backtests and charge both actual saved fit passes."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from aperture_score import PHYSICAL, SIMULATED, references
from aperture_trial import read, write
from directed_donor import LOOSE, TIGHT, matching
from directed_donor_trial import CASES, HERE, SLOTS_SHA, VERIFIER_SHA, baseline, indices, pinned
from mixture_score import section
from quadratic_support import FACTOR_FIELDS


OWNER_SHA = "00a5936a72e5697a3209acece4dc5492414c4840aabbc980e78ee3477ab54339"
WITNESS_SHA = "09ccc94a33cbe813a82333aaa26a3e1c8efdf86c04d264d4ffdfee1e6a7b0658"


def withheld(rows, stock, paid, replay):
    proposed = set(replay["proposals"])
    known = {row["norad"] for row in paid.values()}
    missed = {oid: owner for oid, owner in stock.items() if oid not in rows["paid_selected"]}
    return dict(missing_original=len(missed), missing_outside_slots=len(missed.keys() - proposed),
                missing_on_slots=len(missed.keys() & proposed),
                unseeded_family_rows=sum(owner["norad"] not in known for owner in missed.values()),
                unseeded_families=sorted({owner["norad"] for owner in missed.values() if owner["norad"] not in known}))


def owner_deltas(before, after):
    common = before.keys() & after.keys()
    return dict(shared=len(common), same_norad=sum(before[oid]["norad"] == after[oid] for oid in common),
                changed_norad=sum(before[oid]["norad"] != after[oid] for oid in common),
                lost_old=len(before.keys() - after.keys()), newly_owned=len(after.keys() - before.keys()))


def regional_sensitivity(queries):
    corners = [offset for row in queries.values() for offset in row["corner_offsets"]]
    if not corners:
        return None
    return {name: dict(p50=float(np.percentile([r[name] for r in corners], 50)),
                       p95=float(np.percentile([r[name] for r in corners], 95)),
                       maximum=max(r[name] for r in corners)) for name in ("doppler_hz", "arrival_samples")}


def individual_queries(ledger, forecast):
    output = {}
    for method in ("two_paid_anchors", "causal_center_residual"):
        counts = {"queries": 0, "tight": 0, "loose": 0}
        for oid, row in forecast.items():
            lane = ledger[oid]
            queries = [entry for entry in row["queries"] if entry["method"] == method]
            counts["queries"] += len(queries)
            for name, tolerance in (("tight", TIGHT), ("loose", LOOSE)):
                counts[name] += len(matching(lane["valid_start_counter"], lane["candidates"], queries, tolerance))
        output[method] = counts
    return output


def score(directory, output, *, owners_dir=None, physical_storage=None):
    from sparse_consensus import paid_visits
    from sparse_consensus_trial import bound_inputs

    owner_ref = pinned("quadratic-support.json", OWNER_SHA)
    files = {f"{case}-{mode}": (directory / f"{case}-{mode}.json").read_bytes()
             for case in CASES for mode in ("forecast", "replay")}
    trials = {key: json.loads(blob) for key, blob in files.items()}
    bundled = pinned("directed-donor-owner-witness.json.gz", WITNESS_SHA) if owners_dir is None else None
    witnesses = {}
    timelines = {}
    for case in CASES:
        blob = bundled[case].encode() if bundled is not None else (owners_dir / f"{case}.json").read_bytes()
        if sha256(blob).hexdigest() != owner_ref["source_receipts"][case]:
            raise ValueError("The postfit owner witness differs from the archived study")
        witnesses[case] = json.loads(blob)
        native, ledger, _, _, _, _, binding = bound_inputs(case)
        forecasts = trials[f"{case}-forecast"]
        receipt = trials[f"{case}-replay"]
        if (receipt["source_forecasts_sha256"] != sha256(files[f"{case}-forecast"]).hexdigest()
                or any(binding[key] != forecasts["identity"][key] for key in ("archive", "source", "offer", "ledger"))
                or receipt["identity"]["native_sha256"] != forecasts["identity"]["native_sha256"]):
            raise ValueError("Saved factors and proposals do not share the original causal scope")
        original = indices(native["source"]["probes"], native["source"]["session_id"])
        paid = paid_visits(ledger)
        timelines[case] = dict(original=original,
                               ledger=indices(ledger, native["source"]["session_id"]),
                               paid_selected={oid for oid, row in original.items() if row["visit_index"] in paid})
    sites = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    sites[CASES[0]] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    all_results = {}
    for case in CASES:
        earlier = witnesses[case]["captures"]
        stock, paid = (earlier[key]["witness"]["labels"] for key in ("complete", "quadratic"))
        first_arms = earlier["quadratic"]["terminal"]["arms"]
        stock_arms = earlier["complete"]["terminal"]["arms"]
        forecast = trials[f"{case}-forecast"]
        result = trials[f"{case}-replay"]
        rows = timelines[case]
        acquisition = withheld(rows, stock, paid, forecast)
        full_added = result["solves"]["full_search"]["added"]
        direct_charges = {
            slice_name: {str(cap): sum(
                rates[str(min(cap, len(row["queries"])))]["positive" if oid in full_added else "negative"]
                for oid, row in forecast["proposals"].items() if row["queries"]
            ) / 1000. for cap in (1, 2)}
            for slice_name, rates in result["archived_direct_native_unit_ms"].items()
        }
        scores = {}
        for mode, solve in result["solves"].items():
            acquired = solve["added"]
            owned_slots = {}
            for oid, factor in acquired.items():
                original = rows["original"][oid]["candidates"]
                if oid in stock and any(tuple(record[key] for key in FACTOR_FIELDS) == tuple(factor[key] for key in FACTOR_FIELDS)
                                        for record in original):
                    owned_slots[oid] = stock[oid]
            candidate = solve["result"]
            before = earlier["quadratic"]["terminal"]["associated"]
            original_rf = section(candidate["arms"], sites[case], stock_arms)
            owner_comparison = {}
            received = {}
            for arm, owners in solve["owners"].items():
                owner_comparison[arm] = owner_deltas(paid, owners)
                received[arm] = sum(owners.get(oid) == row["norad"] for oid, row in owned_slots.items())
            scores[mode] = dict(added_factors=len(acquired), added_ranks={
                str(rank): sum(f["candidate_rank"] == rank for f in acquired.values()) for rank in (0, 1)
            }, printed_complete_owners_available=len(owned_slots),
                original_complete_owners_recovered=received, first_associated=before,
                new_associated=candidate.get("associated"), first_owner_comparison=owner_comparison,
                postfit=original_rf, versus_first=section(candidate["arms"], sites[case], first_arms),
                status=candidate["status"], reason=candidate["reason"], passes=candidate["status"] == "ok" and all(
                    arm["delta_error_km"] <= .25 for arm in original_rf["arms"].values()),
                fallback_cpu_s=solve["fallback_cpu_s"], charged=solve["charged"], routes=solve.get("routes"),
                reused_first_pass=solve.get("reused_first_pass", False), input_sha256=solve["input_sha256"])
        counts = {str(rank): sum(
            factor["candidate_rank"] == rank for oid in forecast["proposals"] for factor in rows["ledger"][oid]["candidates"]
        ) for rank in (0, 1)}
        paid_cpu = owner_ref["cases"][case]["acquisition"]["paid_native_cpu_s"]
        archived_first = baseline(case, "quadratic")["charged"]
        total_first = paid_cpu + archived_first["cpu_s"]
        stages = dict(first_paid_native=paid_cpu, first_solver=archived_first["cpu_s"],
                      first_plus_full_search_plus_second_fit=total_first + result["extra_original_native_cpu_s"]
                      + scores["full_search"]["charged"]["cpu_s"],
                      first_plus_forecast_directed_and_second_fit=total_first + forecast["forecast_clocks"]["cpu_s"]
                      + direct_charges["dense"]["2"] + scores["directed"]["charged"]["cpu_s"])
        storage = result["member_read_footprint"]
        if case == CASES[0] and physical_storage is not None:
            supplement = read(physical_storage)
            if supplement["case"] != case or supplement["slot_sha256"] != forecast["slots_sha256"]:
                raise ValueError("The later signed archive index belongs to different query slots")
            storage = dict(supplement["footprint"], separate_receipt_sha256=sha256(physical_storage.read_bytes()).hexdigest())
        all_results[case] = dict(
            first=section(first_arms, sites[case], stock_arms), complete=section(stock_arms, sites[case], stock_arms),
            first_paid_cpu_s=paid_cpu, first_saved_solver=archived_first,
            original_complete_solver=baseline(case, "complete")["charged"], charged_cpu_s_excluding_raw_io=stages,
            coverage=result["coverage"], available_ranks=counts,
            individual_queries=individual_queries(rows["ledger"], forecast["proposals"]),
            orbit=result["orbit"], corner_sensitivity=regional_sensitivity(forecast["proposals"]),
            forecast_clocks=forecast["forecast_clocks"], acquisition=acquisition, fits=scores,
            archived_direct_native_unit_ms=result["archived_direct_native_unit_ms"],
            transferred_direct_cost_cpu_s=direct_charges, extra_full_search_native_cpu_s=result["extra_original_native_cpu_s"],
            projected_stereo_visits=result["projected_stereo_visits"], buffer_iq_bytes=result["buffer_iq_bytes"],
            member_read_footprint=storage,
            forecast_sha256=forecast["proposals_sha256"], slots_sha256=forecast["slots_sha256"])
    write(output, dict(cases=all_results, sealed_rows={key: sha256(blob).hexdigest() for key, blob in files.items()},
                       pins=dict(verified_slot_file=SLOTS_SHA, verifier_cost=VERIFIER_SHA,
                                 original_owners=OWNER_SHA, owner_witness=WITNESS_SHA)))


if __name__ == "__main__":
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("directory", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--owners-dir", type=Path)
    cli.add_argument("--physical-storage", type=Path)
    score(**vars(cli.parse_args()))
