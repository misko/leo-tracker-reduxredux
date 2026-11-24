"""Rebuild the checked 192-visit mixed-aperture intervention without waveform input."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "measurements"
BASELINE = Path("/dev/shm/leo-held-anchor-selected-dense-01")
VISITS = 192
PINS = {
    "eight-ms-primary.json.gz": "a6b67123abe0a740b2843f08cc1cde7f603e6f18dd890ad15cc3b3243fc317b3",
    "full-short-cold.json.gz": "58892accfa3da056d432031d0a476ec869239963cdc5cd40cd52002c6b2553bc",
    "dense-full-short-raw.json.gz": "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38",
    "original-detections.json": "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85",
    "route-decision.json": "393231a6a542058a7fbbd2073cb81c3397987fbe65874aba660b57cf7a1efe37",
    "request.json": "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502",
    "selected/joint-research-receipt.json": "7ae8a3e323b4d971b155c161526b43f6d8f9376e073c9a9cf447c0f5cad152d6",
}
SHORT_SHA = {
    "12ms": "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9",
    "8ms": "fe4ba7b7613654c268353f9e4a78c2bbb916904e06387ace304b0866818f0e3d",
}
CONTINUATION_SHA = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"
ORIGINAL_RECIPE_SHA = "13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"
FRACTIONAL = ("fractional_control_score", "fractional_epoch_offset_samples", "fractional_exact_score",
              "fractional_margin", "fractional_tracking_cfo_hz")


def read(path, name):
    data = path.read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"The frozen input changed: {path}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def validate_short(candidates):
    if not candidates:
        return
    if len(candidates) != 1:
        raise ValueError("A short primary may emit at most one selected factor")
    factor, = candidates
    if (set(factor) != {*FRACTIONAL, "integer_epoch_sample", "candidate_rank", "passed_fractional_margin_gate"}
            or type(factor["candidate_rank"]) is not int or factor["candidate_rank"] != 0
            or type(factor["integer_epoch_sample"]) is not int
            or factor["passed_fractional_margin_gate"] is not True
            or not all(type(factor[k]) in (float, int) and isfinite(factor[k]) for k in FRACTIONAL)):
        raise ValueError("The archived short factor lacks its original signed native fields")


def splice(original, archived12, archived8, *, limit=VISITS):
    from anchor_exposure import enroll, metadata

    before = original["source"]["probes"]
    prefix = [row for row in before if row["visit_index"] < limit]
    if len(prefix) != 2 * limit or [row["visit_index"] for row in prefix[::2]] != list(range(limit)):
        raise ValueError("The required prefix must contain every original issued stereo visit")
    if prefix != archived12 or len(archived8) != len(prefix):
        raise ValueError("The callback archive is missing a lane or differs from the full 12 ms packet")
    output, ledger = [], []
    for index, (event, row) in enumerate(zip(enroll(original), before, strict=True)):
        visit, slot, radio, _, kind, _ = event
        if visit >= limit:
            output.append(row)
            continue
        replacement = archived8[index]
        if metadata(row) != metadata(replacement):
            raise ValueError("An 8 ms callback row lost its original lane, clock or RF")
        if kind == "anchor" and row != replacement:
            raise ValueError("The archived full 20 ms anchor measurement changed")
        if kind == "short":
            for lane in (row, replacement):
                validate_short(lane["candidates"])
        final = replacement if kind == "short" else row
        output.append(final)
        ledger.append(dict(visit=visit, stream_slot=slot, radio=radio, aperture=kind, before=row, after=final))
    return output, ledger


def source_inputs(staged):
    native = read(BASELINE / "original-detections.json", "original-detections.json")
    request = read(BASELINE / "request.json", "request.json")
    held = read(BASELINE / "route-decision.json", "route-decision.json")
    study = read(ARCHIVE / "eight-ms-primary.json.gz", "eight-ms-primary.json.gz")
    earlier = read(ARCHIVE / "full-short-cold.json.gz", "full-short-cold.json.gz")
    owner = read(BASELINE / "selected/joint-research-receipt.json", "selected/joint-research-receipt.json")
    original_receipt = read(ARCHIVE / "dense-full-short-raw.json.gz", "dense-full-short-raw.json.gz")
    source = native["source"]
    original_pin = "sha256:" + PINS["original-detections.json"]
    staged.bind_native(native, request["session"], request["inventory"], ORIGINAL_RECIPE_SHA, expected=original_pin)
    if (source["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or original_receipt["candidate"]["native_sha256"] != original_pin
            or original_receipt["candidate"]["recipe"]["receiver_audit"]["selected"] != 7336
            or held["original_native_sha256"] != original_pin or owner["receipt"]["decision"] != "complete"):
        raise ValueError("The full mixed packet, acquisition recipe or held baseline changed")
    earlier_native = earlier["detection_documents"]["full-short"]
    prefix_input = study["input_sha256"]
    if (earlier_native["source"]["session_id"] != source["session_id"]
            or earlier_native["source"]["input_manifest_sha256"] != source["input_manifest_sha256"]
            or prefix_input["previous_prefix"] != PINS["full-short-cold.json.gz"]
            or study["dense"]["probes"]["12ms"] != earlier_native["source"]["probes"]
            or prefix_input["chronological_dense_iq_sha256"] != earlier["acquisition"]["repeats"][0][0]["decoded_iq_hashes"]
            or len(prefix_input["chronological_dense_iq_sha256"]) != VISITS
            or not study["dense"]["exact_historical_12ms"] or study["dense"]["tail_checks"] != 336
            or {name: row["binary_sha256"] for name, row in study["build"]["primary"].items()} != SHORT_SHA):
        raise ValueError("The prefix clocked callbacks do not bind the authentic measured 8/12 ms inputs")
    return native, study, earlier_native, request, held, owner


def compare_owners(original, selected, receipt):
    from math import remainder

    session = original["source"]["session_id"]
    after = {(row["receiver_id"], row["valid_start_counter"]): row for row in selected["source"]["probes"]}
    affected = {}
    for row in original["source"]["probes"]:
        radio, start = row["receiver_id"], row["valid_start_counter"]
        peer = after[radio, start]
        if row["candidates"] != peer["candidates"]:
            key = "sha256:" + sha256(f"{session}:{radio}:{start}".encode()).hexdigest()
            change = dict(visit=row["visit_index"], radio=radio, channel=row["channel"],
                          after_prefix=row["visit_index"] >= VISITS, missing=not peer["candidates"])
            if row["candidates"] and peer["candidates"]:
                a, = row["candidates"]
                b, = peer["candidates"]
                epoch = (b["integer_epoch_sample"] - a["integer_epoch_sample"]
                         + b["fractional_epoch_offset_samples"] - a["fractional_epoch_offset_samples"])
                change.update(wrapped_epoch_samples=remainder(epoch, 13_333),
                              signed_cfo_hz=b["fractional_tracking_cfo_hz"] - a["fractional_tracking_cfo_hz"])
            affected[key] = change
    results = {}
    for arm, rows in receipt["selected_rows"].items():
        changed = [dict(affected[key], original_id=key, original_norad=norad, original_role=role)
                   for key, norad, role in rows if key in affected]
        results[arm] = dict(owners=len(rows), changed=len(changed), empty=sum(row["missing"] for row in changed),
                            outside_tolerance=sum(not row["missing"] and (abs(row["wrapped_epoch_samples"]) > 2
                                                   or abs(row["signed_cfo_hz"]) > 250) for row in changed),
                            details=changed)
    return results


def plan(output):
    import empty_bootstrap as staged

    staged.load_runtime()
    from anchor_cycle_route import select_route
    from anchor_exposure import bind
    from anchor_holds import history_rows
    from continued_cfo_trial import rebinding
    from held_anchor_route_publication import SELECTOR_SOURCES, SETTINGS
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from tools.pipeline_eval.variants import carrier_continuation

    for name, pin in SELECTOR_SOURCES.items():
        staged.checked(HERE / name, pin)
    staged.checked(Path(carrier_continuation.__file__), CONTINUATION_SHA)
    original, study, earlier, request, held, owner = source_inputs(staged)
    if canonical_digest(held["original_recipe"]) != "sha256:" + ORIGINAL_RECIPE_SHA:
        raise ValueError("The original detector recipe changed")
    probes = study["dense"]["probes"]
    rows, ledger = splice(original, probes["12ms"], probes["8ms"])
    slots = Counter(entry["aperture"] for entry in ledger)
    if slots != {"anchor": 48, "short": 336}:
        raise ValueError("The archived primary comparison used a different full-anchor schedule")
    recipe = dict(held["original_recipe"], archived_partial_short_aperture=dict(
        issued_visit_range=[0, VISITS], short_samples=80_000, short_native_sha256=SHORT_SHA["8ms"],
        primary_archive_sha256=PINS["eight-ms-primary.json.gz"], joined_reference_sha256=PINS["original-detections.json"],
        shorter_rows_before_history=canonical_digest(probes["8ms"]), real_new_acquisition=False))
    candidate = rebinding(original, rows, recipe)
    bind(original, candidate)
    began = process_time(), perf_counter()
    baseline = select_route(original, audit=True)
    choice = select_route(candidate, audit=True)
    if (baseline["route"] != "unfiltered" or canonical_digest(original) != held["selected_native_sha256"]
            or canonical_digest({key: baseline[key] for key in held["choice"]}) != canonical_digest(held["choice"])):
        raise ValueError("Original EOF replay disagrees with the historical complete 12 ms selection")
    final = history_rows(rows) if choice["route"] == "history" else rows
    if any(after["candidates"] and after != before for before, after in zip(rows, final, strict=True)):
        raise ValueError("EOF history introduced an unmeasured candidate")
    policy = dict(settings=SETTINGS, selector_sources=SELECTOR_SOURCES, continuation_sha256=CONTINUATION_SHA,
                  choice=choice["route"], no_fixed_epoch_remeasurement=True)
    final_recipe = dict(recipe, selected_original_eof_route=policy)
    detector = canonical_digest(final_recipe)
    selected = rebinding(candidate, final, final_recipe)
    native = canonical_digest(selected)
    staged.bind_native(selected, request["session"], request["inventory"], detector[7:], expected=native)
    bind(original, selected)
    elapsed = dict(cpu_s=process_time()-began[0], elapsed_s=perf_counter()-began[1])
    scope = Counter()
    for event in ledger:
        before, after = (event[key]["candidates"] for key in ("before", "after"))
        kind = event["aperture"]
        scope.update({f"{kind}_lanes": 1, f"{kind}_before": len(before), f"{kind}_after": len(after),
                      f"{kind}_gained": int(not before and bool(after)), f"{kind}_lost": int(bool(before) and not after),
                      f"{kind}_changed_positive": int(bool(before and after) and before != after)})
    output.mkdir()
    immutable_json(output / "detections.json", selected)
    staged.checked(output / "detections.json", native[7:])
    immutable_json(output / "prefix-ledger.json", ledger)
    summary = dict(inputs=PINS, raw_authority=request["authority"], original_inventory=request["inventory"],
                   original_cutoff=request["cutoff_utc_ns"], original_offer_sha256=request["offer_sha256"],
                   archive=request["archive"], native_sha256=native, detector_sha256=detector,
                   input_scope_authority=earlier["source"]["raw_recording_authority_digest"],
                   prefix_only=True, prefix_build_sha256=study["build_sha256"],
                   prefix_iq_hashes_sha256=canonical_digest(study["input_sha256"]["chronological_dense_iq_sha256"]),
                   prefix_ledger_sha256=canonical_digest(ledger), prefix_scope=dict(scope),
                   clock_anchor_sha256=canonical_digest(original["clock_anchor"]),
                   delivery_clocks_sha256=canonical_digest(original["delivery_clocks"]),
                   original_factors=sum(len(row["candidates"]) for row in original["source"]["probes"]),
                   mixed_factors=sum(len(row["candidates"]) for row in rows),
                   selected_factors=sum(len(row["candidates"]) for row in final),
                   issued=original["provenance"]["window_count"], invalid=original["provenance"]["invalid_capture"],
                   original_later_shorts=11_834 - scope["short_lanes"], selector_clocks=elapsed,
                   owner_sensitivity=compare_owners(original, selected, owner),
                   historical_named_owners=study["dense"]["owners_vs_installed"],
                   detector_recipe=final_recipe, waveform_reads=0, fits=0)
    summary["held"] = {label: {key: result[key] for key in ("route", "log_score_gain_by_radio", "incomplete_cycles",
                       "held_before_partial_cycle_drop", "prediction_digest", "radio")}
                       for label, result in (("original", baseline), ("mixed", choice))}
    immutable_json(output / "plan.json", summary)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    plan(Path(sys.argv[1]))
