"""Score fixed-support likelihood decomposition and the paid-anchor opportunity census."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from aperture_score import PHYSICAL, SIMULATED, references
from aperture_trial import read, write
from mixture_score import section
from quadratic_support import native_rows, proposals
from quadratic_support_trial import CASES, HERE, PINS


def geometry_attribution(row):
    if "calibration_hz_per_ghz" not in row:
        return None
    slope = np.asarray(row["uncertainty"]["fitted_c"]["position_km_per_1000_hz_per_ghz"])
    predicted = slope * row["calibration_hz_per_ghz"] / 1000.
    actual = np.subtract(row["east_north_km"]["fitted_c"], row["east_north_km"]["c0"])
    return dict(predicted_local_displacement_km=predicted, measured_displacement_km=actual,
                disagreement_km=float(np.linalg.norm(actual-predicted)))


def acquisition(case, row):
    from leo.contracts.digests import canonical_digest
    from sparse_consensus import paid_visits
    from sparse_consensus_trial import bound_inputs

    native, ledger, _, clocks, _, _, binding = bound_inputs(case)
    captured = row["captures"]["complete"]["identity"]
    if any(binding[key] != captured[key] for key in ("source", "archive", "offer", "ledger")):
        raise ValueError("The paid-anchor score uses a different sealed ledger")
    paid = paid_visits(ledger)
    if len(paid) != row["paid_visits"]:
        raise ValueError("The original paid mask changed")
    original = native_rows(native)
    complete = row["captures"]["complete"]["witness"]["labels"]
    sparse = row["captures"]["quadratic"]["witness"]["labels"]
    metadata = {oid: {key: value for key, value in item.items() if key != "signal"}
                for oid, item in original.items()}
    nominations = {oid: {"norad": owner["norad"]} for oid, owner in sparse.items()}
    available = proposals(nominations, metadata, paid)
    slots = []
    for oid in sorted(available, key=lambda oid: (metadata[oid]["visit"], metadata[oid]["receiver"])):
        item = metadata[oid]
        slots.append(dict(observation_id=oid, visit_index=item["visit"], receiver_id=item["receiver"],
                          valid_start_counter=item["counter"], channel=item["channel"], actual_rf_hz=item["rf_hz"],
                          families=[dict(norad=norad, anchor_observations=[
                              dict(observation_id=aid, visit_index=metadata[aid]["visit"],
                                   valid_start_counter=metadata[aid]["counter"])
                              for aid in anchors])
                                    for norad, anchors in available[oid].items()]))
    slot_receipt = dict(slots=slots, slots_sha256=canonical_digest(slots),
                        paid_visit_sha256=canonical_digest(sorted(paid)),
                        paid_owner_sha256=row["captures"]["quadratic"]["terminal"]["owners"],
                        paid_packet_sha256=row["captures"]["quadratic"]["identity"]["native_sha256"],
                        ownership_provenance="blind quadratic signed terminal on original paid factor rows")
    missed = {oid: owner for oid, owner in complete.items() if original[oid]["visit"] not in paid}
    hit = {oid for oid, owner in missed.items() if owner["norad"] in available.get(oid, ())}
    if len(hit) != sum(r["past_anchor_supported"] for r in row["acquisition_ceiling"]):
        raise ValueError("Metadata-only nomination and withheld ownership census disagree")
    query_visits = sorted({original[oid]["visit"] for oid in available})
    witnessed_families = {owner["norad"] for owner in sparse.values()}
    paid_cpu = sum(t for r, t in zip(ledger, clocks, strict=True) if r["visit_index"] in paid) / 1e9
    total_cpu = sum(clocks) / 1e9
    clocks_by_lane = {(p["receiver_id"], p["valid_start_counter"]): elapsed
                      for p, elapsed in zip(ledger, clocks, strict=True)}
    callback_cost = 0.
    for p in native["source"]["probes"]:
        key = (p["receiver_id"], p["valid_start_counter"])
        oid = "sha256:" + sha256(f"{native['source']['session_id']}:{key[0]}:{key[1]}".encode()).hexdigest()
        if oid in available:
            callback_cost += clocks_by_lane[key] / 1e9
    return dict(unpaid_owner_rows=len(missed), correct_family_opportunity=len(hit),
                missing_by_norad=Counter(str(v["norad"]) for v in missed.values()),
                no_sparse_owner_family=sum(v["norad"] not in witnessed_families for v in missed.values()),
                proposed_observations=len(available), proposed_family_lane_pairs=sum(map(len, available.values())),
                proposed_stereo_visits=len(query_visits), proposed_visit_ids=query_visits,
                proposed_slots_sha256=slot_receipt["slots_sha256"],
                archived_all_lane_native_cpu_s=total_cpu, paid_native_cpu_s=paid_cpu,
                original_native_cpu_for_proposed_lanes_s=callback_cost,
                groups=row["acquisition_ceiling"]), slot_receipt


def score(directory, output, *, slots_out=None):
    files = {case: (directory / f"{case}.json").read_bytes() for case in CASES}
    rows = {case: json.loads(blob) for case, blob in files.items()}
    names = ("quadratic_support_trial.py", "quadratic_support.py", "quadratic_support_score.py", "paid_graph_trial.py")
    implementations = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in names}
    if any(row["source_sha256"] != implementations[names[0]] for row in rows.values()):
        raise ValueError("The saved capture uses a different frozen diagnostic")
    accounts = {case: acquisition(case, row) for case, row in rows.items()}
    if slots_out is not None:
        write(slots_out, dict(cases={case: value[1] for case, value in accounts.items()},
                              proposal_source_sha256=implementations[names[1]]))
    targets = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    targets[CASES[0]] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    results = {}
    for case, row in rows.items():
        arms = row["captures"]["complete"]["terminal"]["arms"]
        capture = {mode: dict(arms=section(run["terminal"]["arms"], targets[case], arms),
                              owner_count=run["terminal"]["associated"], owner_sha256=run["terminal"]["owners"],
                              calibration=run["witness"]["calibration_hz_per_ghz"], timings=run["clocks"])
                   for mode, run in row["captures"].items()}
        fixed = {}
        for name, variant in row["fixed"].items():
            compact = {key: val for key, val in variant.items() if key not in
                       ("ordinary", "signed", "exterior", "arms")}
            compact.update(position=section(variant.get("arms", {}), targets[case], arms),
                           calibration_displacement=geometry_attribution(variant))
            fixed[name] = compact
        results[case] = dict(overlap=row["comparison"], captured=capture, fixed=fixed,
                             acquisition=accounts[case][0], identity=row["captures"]["complete"]["identity"])
    write(output, dict(cases=results, source_receipts={case: sha256(blob).hexdigest() for case, blob in files.items()},
                       worker=rows[CASES[0]]["worker"], archived_pins=PINS, implementations=implementations,
                       references={str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
                                   for path in (PHYSICAL, SIMULATED)}))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--slots-out", type=Path)
    score(**vars(parser.parse_args()))
