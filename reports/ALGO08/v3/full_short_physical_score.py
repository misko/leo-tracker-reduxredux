"""Verify the sealed DS30-0016 raw pair without traversing the waveform again."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import ARMS, archive_identity, read, write
from full_short_physical import ADMITTED, ISSUED, ORDER, PAIR, PAIR_SHA, authorize_gate, checked
from full_short_raw import GRAPH, RECIPE_SHA, mixed, recipe


def classified(probes):
    """Reconstruct the stereo schedule from original probe metadata."""
    visits, factors, streams = Counter(), Counter(), Counter()
    keys = ("visit_index", "valid_start_counter", "edge", "channel", "actual_rf_hz")
    for left, right in zip(probes[::2], probes[1::2], strict=True):
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1) or any(left[k] != right[k] for k in keys)):
            raise ValueError("Expected one original stereo pair per admitted visit")
        stream = tuple(left[key] for key in keys[2:])
        anchor = streams[stream] % 8 == 0
        streams[stream] += 1
        mode = "full" if anchor else "short_primary"
        visits[mode] += 1
        for lane in (left, right):
            positive = lane["candidates"]
            if len(positive) > 1 or any(not c["passed_fractional_margin_gate"] for c in positive):
                raise ValueError("Receiver exported an unverified or nonselected factor")
            if not anchor and any(c["candidate_rank"] != 0 for c in positive):
                raise ValueError("A 12 ms primary slot emitted a residual factor")
            factors[mode] += len(positive)
    return dict(visits=dict(visits), native_calls={k: 2*v for k, v in visits.items()}, factors=dict(factors))


def read_arm(output, arm, request):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import evidence

    work = output / arm
    proof, receiver = map(read, (work / "joint-research-receipt.json", work / "receiver-audit.json"))
    clock = read(output / f"{arm}-process.json")
    detected, = (work / "fast-scan-automatic-work").glob("*/detections.json")
    result = proof["receipt"]
    terminal = work / "fast-scan-automatic-work" / result["run_id"] / "terminal.json"
    native = read(detected)
    source, prov = native["source"], native["provenance"]
    pin = RECIPE_SHA if arm == "candidate" else mixed.INSTALLED_SHA
    verified = evidence(work, result, 0, read_only=True)
    verified.pop("terminal_file_s")
    independent = json.loads(json.dumps(artifacts(work, result)))
    probes = source["probes"]
    actual = dict(processed=ADMITTED, invalid_capture=ISSUED-ADMITTED, skipped_fast_score=0)
    analysis = canonical_digest(["cancellation", request["raw_authority"], pin, probes])
    if (clock["exit_code"] or proof["saved_digest"] is not None or proof["saved_handoff_manifest"] is not None
            or result["region"] != request["offered_region"] or result["session_id"] != request["session"]
            or result["counts"] != actual or result["window_count"] != ISSUED
            or source["raw_recording_authority_digest"] != request["raw_authority"]
            or verified["raw_authority"] != request["raw_authority"] or not source["qualified"]
            or source["input_manifest_sha256"] != request["inventory_sha256"]
            or receiver["recording_authority"] != request["raw_authority"]
            or receiver["input_manifest"] != request["inventory_sha256"]
            or not (source["analysis_manifest_sha256"] == receiver["analysis_manifest"] == analysis)
            or receiver["detector_pin"] != pin or prov["detector_sha256"] != "sha256:" + pin
            or len(probes) != 2 * ADMITTED or receiver["issued"] != ISSUED
            or receiver["selected"] != sum(bool(p["candidates"]) for p in probes)
            or sum(receiver["native"]["native_calls"].values()) != 2 * ADMITTED
            or read(terminal)["native_sha256"] != canonical_digest(native)
            or independent != proof["evidence"]):
        raise ValueError(f"{arm} failed independent raw, detector, or publication evidence validation")
    if arm == "candidate":
        expected = classified(probes)
        if (any(receiver["native"].get(k) != v for k, v in expected.items()) or receiver["graph"] != GRAPH
                or receiver["recipe"] != recipe() or not proof["optimized_full_catalogue"]
                or len(proof["early_regional"]) != 1):
            raise ValueError("The candidate did not run the frozen full-coverage schedule, graph and regional rule")
    elif not proof["stock_control"] or receiver["recipe"] is not None or receiver["graph"] != "installed":
        raise ValueError("The control did not run the installed path")
    cache = {phase: read(output / f"{arm}-cache-{phase}.json") for phase in ("before", "after")}
    return dict(publication=proof, verified=verified, acquire=receiver, process=clock, cache=cache,
                detection=dict(path=str(detected.relative_to(output)), bytes_sha256=sha256(detected.read_bytes()).hexdigest(),
                               native_sha256=canonical_digest(native)),
                terminal=dict(path=str(terminal.relative_to(output)), sha256=result["terminal_sha256"])), native


def score(output, gate, destination):
    from aperture_score import PHYSICAL, distance_km
    from optimized_full_catalogue_trial import figures
    from signed_0374_transfer import owner_changes

    authorize_gate(gate)
    request = read(output / "request.json")
    if (request["gate_sha256"] != sha256(gate.read_bytes()).hexdigest()
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("The fixed offer archive or gate changed before scoring")
    loaded = {arm: read_arm(output, arm, request) for arm in ORDER}
    runs = {a: row for a, (row, _) in loaded.items()}
    s, c = [runs[a]["publication"] for a in ORDER]
    s_probes, c_probes = [loaded[a][1]["source"]["probes"] for a in ORDER]
    original, compared = [[{k: v for k, v in p.items() if k != "candidates"} for p in probes]
                          for probes in (s_probes, c_probes)]
    if original != compared:
        raise ValueError("Acquisition opportunity or chronological stereo support differs")
    expected = read(checked(PAIR, PAIR_SHA))["runs"]["baseline"]
    survey, = [row["reference"] for row in read(PHYSICAL)["cases"] if row["dataset_label"] == "DS30-0016"
               and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    errors = {arm: {a: None if v["latlon"] is None else distance_km(v["latlon"], truth)
                    for a, v in row["verified"]["arms"].items()} for arm, row in runs.items()}
    delta = {a: None if any(errors[arm][a] is None for arm in ORDER) else errors["candidate"][a]-errors["stock"][a]
             for a in ARMS}
    plots = figures(s["evidence"]["images"], c["evidence"]["images"])
    complete = all(row["receipt"]["decision"] == "complete" and row["solve"]["grid_complete"]
                   and len(row["evidence"]["images"]) == 8 for row in (s, c))
    elapsed = {arm: row["process"]["clocks"]["elapsed_s"] for arm, row in runs.items()}
    cpu = {arm: row["process"]["clocks"]["cpu_s"] for arm, row in runs.items()}
    write(destination, dict(request=request, runs=runs, order=list(ORDER), exact_probe_metadata=True,
                            comparison=dict(horizontal_error_km=errors, position_delta_km=delta,
                              pngs=plots, owners=owner_changes(s, c),
                              both_complete=complete, passes_position=complete and all(d is not None and d <= .25 for d in delta.values()),
                              elapsed_ratio=elapsed["candidate"]/elapsed["stock"], cpu_ratio=cpu["candidate"]/cpu["stock"],
                              prior_stock_arms_match=runs["stock"]["verified"]["arms"] == expected["arms"],
                              colocated_factors=sum(bool(a["candidates"] and b["candidates"])
                                                    for a, b in zip(s_probes, c_probes, strict=True))),
                            survey_source_sha256=sha256(PHYSICAL.read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "gate", "destination"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
