"""Verify the one dense mixed history-risk execution and historical comparators."""

import argparse
import gzip
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from history_risk_dense_mixed import CONTROL_PINS, COUNTS, EXACT, FINISH, NATIVE, deny_original, digest, read


ARMS = ("c0", "fitted_c")
RAW_STAGE = HERE / "measurements/dense-full-short-raw.json.gz"


def additive_budget(raw, req, clock, admission):
    """Charge the whole verified original acquisition and the new saved process."""
    from full_short_raw import RECIPE_SHA

    binding, previous = raw["binding"], raw["candidate"]
    receiver = previous["recipe"]["receiver_audit"]
    native = receiver["native"]
    if (previous["native_sha256"] != NATIVE or previous["native_file_sha256"] != NATIVE[7:]
            or receiver["detector_pin"] != RECIPE_SHA or previous["recipe"]["saved_digest"] is not None
            or previous["recipe"]["recipe"]["aperture_samples"] != [200000, 120000]
            or receiver["selected"] != 7336 or native["native_calls"] != {"full": 1696, "short_primary": 11834}
            or receiver["issued"] != req["issued"] or previous["verified"]["receipt"]["counts"] != COUNTS
            or any(binding[field] != req[field] for field in ("inventory", "session", "authority"))
            or receiver["recording_authority"] != req["authority"]
            or receiver["input_manifest"] != req["inventory"]
            or receiver["analysis_manifest"] != req["analysis_manifest"]
            or binding["archive"]["snapshots_sha256"] != req["archive"]["snapshots_sha256"]
            or binding["region_sha256"] != req["offer_sha256"]
            or not raw["comparison"]["exact_probe_metadata"] or raw["process"]["status"] != 0):
        raise ValueError("Historical acquisition is ineligible for this additive budget")
    stage = receiver["acquire"]
    cpu, wall = stage["cpu_ns"] / 1e9, stage["wall_ns"] / 1e9
    return dict(scope="historical verified raw acquire plus new saved publication and admission; two-process sum",
                measured_end_to_end=False, native_sha256=NATIVE, historical_acquire_cpu_s=cpu,
                historical_acquire_elapsed_s=wall, historical_process=raw["process"], historical_cache=raw["cache"],
                sum_cpu_s=cpu+clock["cpu_s"], sum_elapsed_s=wall+clock["elapsed_s"],
                sum_with_admission_cpu_s=cpu+clock["cpu_s"]+admission["cpu_ns"]/1e9,
                sum_with_admission_elapsed_s=wall+clock["elapsed_s"]+admission["elapsed_ns"]/1e9)


def compare_media(control, current):
    if set(control) != set(current) or len(current) != 8:
        raise ValueError("Compare the eight verified names in the same complete publication")
    return {name: {key: control[name][key] == row[key] for key in ("size", "sha256", "rgba_sha256")}
            for name, row in current.items()}


def compare_science(directory, record, run_id, candidate, candidate_documents):
    from causal_pre_refit_0155 import compare_grid
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta

    store = FastStandardAnalysisStore(directory)
    control = {name: getattr(store, "position_" + name)(run_id) for name in ("grid", "path")}
    for name, value in control.items():
        if (canonical_digest(value) != record["media"][f"{name}_sha256"]
                or value["binding"]["position_png_sha256"] != record["figures"]["position"]["sha256"]):
            raise ValueError("The archived full grid or path changed")
    owners = read(directory / "joint-research-receipt.json")["selected_rows"]
    if set(owners) != set(ARMS) or any(canonical_digest(owners[arm]) != record["ordered_owner_sha256"][arm]
                                     for arm in ARMS):
        raise ValueError("The archived ordered ownership changed")
    paths = dict(same_stages=control["path"]["stages"] == candidate_documents["path"]["stages"],
                 control_stages=control["path"]["stages"], current_stages=candidate_documents["path"]["stages"])
    return dict(grid=compare_grid(control["grid"], candidate_documents["grid"]),
                same_ordered_grid=control["grid"]["points"] == candidate_documents["grid"]["points"], path=paths,
                figures=compare_media(record["figures"], candidate["images"]),
                owners={arm: owner_delta(owners[arm], candidate["owner_rows"][arm]) for arm in ARMS})


def score(root):
    from aperture_trial import write
    from empty_bootstrap import checked
    from exact_named_raw import evidence
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from mixed_named_finish_0008 import ORIGINAL_V3_PIN
    from triage_bounds import calibration_comparison

    sys.addaudithook(deny_original)
    bound, clock, handoff = (read(root / name) for name in ("binding.json", "clock.json", "publication.json"))
    output = root / "candidate"
    witness = read(output / "exact-named-raw-witness.json")
    terminal_path, = output.glob("fast-scan-automatic-work/*/terminal.json")
    terminal, receipt, req = read(terminal_path), handoff["receipt"], bound["request"]
    packet = read(Path(req["packet"]))
    req = dict(req, analysis_manifest=packet["source"]["analysis_manifest_sha256"])
    raw = json.loads(gzip.decompress(checked(RAW_STAGE, ORIGINAL_V3_PIN)))
    stock = raw["baseline"]
    if (clock["exit_code"] or handoff["verified_handoffs"] != 1 or handoff["waveform_acquisitions"] != 0
            or digest(Path(req["packet"])) != NATIVE[7:] or terminal["native_sha256"] != NATIVE
            or receipt["session_id"] != req["session"] or receipt["window_count"] != req["issued"]
            or receipt["counts"] != COUNTS or terminal["region"] != stock["receipt"]["region"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]):
        raise ValueError("The publication must preserve the original input, raw authority and geographic offer")
    seen = witness["evidence"]
    verified = evidence(output, receipt, NATIVE, [seen["owner_rows"]] if seen["owner_rows"] else [])
    if canonical_digest(verified) != canonical_digest(seen):
        raise ValueError("Independent product verification differs from the measured publication")
    history, route = (witness["ports"][key] for key in ("history", "history_risk"))
    if history["solves"] != 1 or len(history["prepare"]) != 1 or route.get("inference_calls") != 1:
        raise ValueError("The saved experiment requires the current checked route through one original preparation")
    if "census" in route["choice"] and route["choice"]["census"]["cutoff_utc_ns"] != req["cutoff_utc_ns"]:
        raise ValueError("The history evidence came from another cutoff")
    original_budget = additive_budget(raw, req, clock, bound["admission"])
    controls = {}
    for label, original in (("exact", EXACT), ("finish", FINISH)):
        data = json.loads(checked(original / "result.json", CONTROL_PINS[label]))
        joint = original / "candidate/joint-research-receipt.json"
        historical = data["actual"] if label == "exact" else data["worker"]
        original_req = data["input"] if label == "exact" else data["inputs"]
        if (any(original_req[key] != req[key] for key in ("inventory", "authority", "native", "offer_sha256", "archive"))
                or historical["receipt"]["decision"] != "complete"):
            raise ValueError("Historical comparator does not bind the same packet and original offer")
        terminal_control, = (original / "candidate").glob("fast-scan-automatic-work/*/terminal.json")
        before = read(terminal_control)
        if canonical_digest(before) != historical["receipt"]["terminal_sha256"]:
            raise ValueError("Archived comparator terminal changed")
        owners = read(joint)["selected_rows"]
        if label == "exact" and canonical_digest(owners) != data["ranked_owner_sha256"]:
            raise ValueError("The sealed exact ownership changed")
        owner_proof = ({arm: canonical_digest(owners[arm]) for arm in ARMS} if label == "exact" else
                       {arm: data["ownership"][arm]["ordered_sha256"] for arm in ARMS})
        detail = FastStandardAnalysisStore(original / "candidate").detail(historical["receipt"]["run_id"])
        for arm in ARMS:
            if canonical_digest({row[0]: row[1] for row in owners[arm]}) != detail["arms"][arm]["owner_sha256"]:
                raise ValueError("Archived comparator owners mismatch the sealed owner map")
        controls[label] = dict(arms=before["arms"], clock=(data["timing"] if label == "exact" else
                                data["launch"]["timing"]), receipt=historical["receipt"], media=data["media"],
                               figures=data["figures"], ordered_owner_sha256=owner_proof)
    complete = receipt["decision"] == "complete"
    if complete and (seen["grid"] != 179 or len(seen["images"]) != 8 or set(terminal["arms"]) != set(ARMS)):
        raise ValueError("A fix requires both arms, a full grid, path and all eight figures")
    comparisons, geography, screen = {}, None, False
    if complete:
        store = FastStandardAnalysisStore(output)
        documents = {name: getattr(store, "position_" + name)(receipt["run_id"]) for name in ("grid", "path")}
        comparisons = {name: compare_science(original / "candidate", controls[name],
                                            controls[name]["receipt"]["run_id"], seen, documents)
                       for name, original in (("exact", EXACT), ("finish", FINISH))}
        geography = calibration_comparison({name: {"arms": arms} for name, arms in
            {"candidate": terminal["arms"], "installed_v3": stock["arms"],
             **{name: control["arms"] for name, control in controls.items()}}.items()}, "DS30-0008")
        runs = geography["runs"]
        screen = all(runs["candidate"]["horizontal_error_km"][arm] <=
                     runs["installed_v3"]["horizontal_error_km"][arm] + 0.25 for arm in ARMS)
    write(root / "result.json", dict(case="DS30-0008", verified=True, complete=complete, passes_250m=screen,
        binding=bound, clock=clock, publication=handoff, terminal=terminal, routed=witness, geography=geography,
        comparisons=comparisons, controls=controls, installed_v3=dict(arms=stock["arms"], clock=stock["clocks"],
            receipt=stock["receipt"], owners=stock["owners"]), additive_budget=original_budget))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    score(parser.parse_args().root)
