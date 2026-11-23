"""Score sealed sparse geometry and fixed-owner fits against installed ALGO08v3."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import inputs, write
from arc_design_trial import CASES, HERE
from mixture_score import section


LIMIT_KM = .25


def outcome(candidate, stock, truth):
    positions = section(candidate.get("arms", {}), truth, stock["arms"])
    control = section(stock["arms"], truth, stock["arms"])
    comparable = candidate["status"] == stock["status"] and candidate.get("reason") == stock["reason"]
    if candidate["status"] == "frontier_only":
        passes = None
    elif stock["status"] == "ok":
        passes = comparable and all(arm["delta_error_km"] is not None and arm["delta_error_km"] <= LIMIT_KM
                                    for arm in positions["arms"].values())
    else:
        passes = comparable and stock["reason"] == "both_receivers_support_far_exterior"
    return dict(accuracy_screen=passes, sparse=positions, stock=control,
                sparse_status=candidate["status"], sparse_reason=candidate.get("reason"),
                stock_status=stock["status"], stock_reason=stock["reason"],
                evidence=candidate.get("evidence"), exact_stock_owner_sha256=stock.get("owners"))


def design_summary(design):
    saved = {key: design[key] for key in ("nominal", "fully_witnessed", "selected_norads", "unresolved")}
    saved.update(selected_lanes=len(design["selected_indices"]), paid_lanes=len(design["paid_indices"]))
    if "populations" in design:
        saved["populations"] = {norad: {**row, "missing_witnesses": sorted({
            issue for arc in row["missing_witnesses"] for issue in arc["issues"]
        })} for norad, row in design["populations"].items()}
    return saved


def visits(probes, indices):
    original = [probes[i] for i in indices]
    fields = ("receiver_id", "channel", "actual_rf_hz")
    lanes = Counter(tuple(probe[field] for field in fields) for probe in original)
    return dict(lanes=len(original), stereo_visits=len({probe["visit_index"] for probe in original}),
                receiver_channel_rf=[[*key, count] for key, count in sorted(lanes.items())])


def score(directory, output):
    data = {case: (directory / f"{case}.json").read_bytes() for case in CASES}
    rows = {case: json.loads(value) for case, value in data.items()}
    trial, selector = (sha256((HERE / path).read_bytes()).hexdigest() for path in ("arc_design_trial.py", "arc_design.py"))
    if any(row["source_sha256"] != trial or row["selector_sha256"] != selector for row in rows.values()):
        raise ValueError("The split-offer receipts use different designs")
    inside, outside = (rows[case] for case in ("south-containing", "south-far"))
    if (outside["containing_receipt_sha256"] != sha256(data["south-containing"]).hexdigest()
            or outside["selected_lanes_sha256"] != inside["selected_lanes_sha256"]
            or outside["paid_lanes_sha256"] != inside["paid_lanes_sha256"]
            or outside["support_authority"] != inside["identity"]):
        raise ValueError("The omitted offer changed the paid waveform or exact owners")
    truth = references()
    results = {}
    for case, row in rows.items():
        native, _, _, expected, identity = inputs(case)
        if row["identity"] != identity:
            raise ValueError("Causal archive or region identity differs from the installed run")
        results[case] = dict(identity=identity, truth_clearance_km=face_clearance_km(identity["offer"], truth[case]),
                             scientific=outcome(row, expected, truth[case]),
                             full_support_summary=row["full_support_summary"],
                             timings={key: value for key, value in row.items() if key.endswith("_clocks")},
                             selected_lanes_sha256=row["selected_lanes_sha256"],
                             paid_lanes_sha256=row["paid_lanes_sha256"])
        if case != "south-far":
            results[case]["design"] = design_summary(row["design"])
            probes = native["source"]["probes"]
            results[case]["acquisition"] = dict(
                original=visits(probes, range(len(probes))),
                selected=visits(probes, row["design"]["selected_indices"]),
                paid=visits(probes, row["design"]["paid_indices"]),
            )
        if "signed" in row:
            results[case]["signed_status"] = row["signed"]["status"]
        if "exterior" in row:
            results[case]["exterior"] = row["exterior"]
        if "ordinary" in row:
            results[case]["fixed_owner_ordinary"] = {
                arm: {key: value[key] for key in ("east_north_km", "rf_rms_hz", "failed_curved", "failed_linear")}
                for arm, value in row["ordinary"].items()
            }
    files = {str(path.relative_to(HERE.parents[2])): sha256(path.read_bytes()).hexdigest()
             for path in (PHYSICAL, SIMULATED)}
    write(output, dict(cases=results, pins=files, candidate_receipts_sha256={key: sha256(value).hexdigest()
                                                                          for key, value in data.items()},
                       accuracy_limit_km=LIMIT_KM, trial_sha256=trial, selector_sha256=selector,
                       worker=inside["worker"], stock_witness_sha256=inside["stock_witness_sha256"],
                       alias_witness_sha256=inside["alias_witness_sha256"]))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    score(**vars(parser.parse_args()))
