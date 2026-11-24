"""Verify the single combined output and rerender its authenticated scene offline."""

import argparse
from collections import Counter
from pathlib import Path

from frame_portable_0016 import PAIR, digest, eligible_pair, read, references, runtime_pins, seal


def verify_render(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from history_risk_residual_layout_0402 import ORBIT_SHEETS, render_pair

    pre = read(root/"preflight.json")
    if host() != pre["machine"] or read(root/"prediction-seal.json") != seal(root):
        raise ValueError("Require the sealed measured output and single-core renderer environment")
    candidate = root/"candidate"
    scene = candidate/"render-scene.pickle"
    witness = read(candidate/"exact-named-raw-witness.json")
    result = render_pair(scene, digest(scene)[7:])
    ordinary, residual = (result["hashes"][name] for name in ("ordinary", "residual_layout"))
    live = {name: row["sha256"] for name, row in witness["evidence"]["images"].items()}
    exact = {name: ordinary[name] == live[name] for name in ORBIT_SHEETS}
    if live != residual or not all(exact.values()):
        raise ValueError("The live candidate must reproduce all eight scene outputs and all four ordinary orbit PNGs")
    write(root/"render-verification.json", dict(result, same_scene_ordinary_orbit_pngs=exact,
               same_scene_live_eight_pngs=True, measured_render_only=True, title=read(candidate/"render-scene.json")["title"]))


def price(named, ordinary, frames, candidate, ready, custody, export):
    total = candidate+ready
    full = total+custody
    return dict(named=named, new_ordinary=ordinary, new_frames=frames, candidate=candidate, ready=ready,
                custody=custody, prepared=total, prepared_with_custody=full,
                target_1_6=named/1.6, gap_to_1_6=total-named/1.6, gap_with_custody_to_1_6=full-named/1.6,
                speedups=dict(named_ready=named/total, named_with_custody=named/full,
                              ordinary_ready=ordinary/total, frames_ready=frames/total),
                portable_export=export, first_use_portable_prepared_capture=total+export)


def score(root):
    from aperture_trial import write
    from history_risk_residual_layout_0402 import media_identity, require_active
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.qualification.paired_publication import evidence

    book = read(root/"preflight.json")
    if read(root/"prediction-seal.json") != seal(root) or runtime_pins() != book["source_pins"]:
        raise ValueError("The preflight runtime or paid results changed after sealing")
    previous = references()
    pair = eligible_pair(previous)
    plan, log = book["source"], read(root/"candidate-clock.json")
    clock = log["clock"]
    if clock["exit_code"] or book["command"] != log["command"]:
        raise ValueError(f"The one combined child did not return a qualified exit: {clock['stderr_tail']}")
    candidate, historical_frames = root/"candidate", PAIR/"frames"
    raw, witness, frame = (read(candidate/name) for name in ("unified-short-bootstrap.json", "exact-named-raw-witness.json", "visit-frame-acquisition.json"))
    old_raw, old_witness = (read(historical_frames/name) for name in ("unified-short-bootstrap.json", "exact-named-raw-witness.json"))
    receipt = raw["receipt"]
    official = evidence(candidate, receipt, clock["started_unix_ns"], read_only=True)
    inner = witness["evidence"]
    leaf, = candidate.glob("fast-scan-automatic-work/*/detections.json")
    recorded = pair["science"]["frames"]
    raw_fields = ("native_sha256", "detector_recipe_sha256", "receiver_recipe", "archive_root", "requested_offer_sha256",
                  "causal_cutoff_utc_ns", "clock_anchor", "raw_acquisitions", "verified_handoffs", "route", "graph_proof")
    receipt_fields = ("decision", "session_id", "run_id", "terminal_sha256", "region", "window_count", "counts")
    if (receipt["decision"] != "complete" or any(receipt[key] != old_raw["receipt"][key] for key in receipt_fields)
            or not all(raw[key] == old_raw[key] for key in raw_fields) or digest(leaf) != raw["native_sha256"]
            or official["raw_authority"] != plan["raw_authority"]
            or any(official[key] != recorded[key] for key in ("arms", "owners", "scientific_digests"))
            or inner["owner_rows"] != old_witness["evidence"]["owner_rows"]
            or canonical_digest(inner["owner_rows"]) != pair["ordered_owner_sha256"]["frames"]
            or witness["solver_recipe"]["history_risk"] != old_witness["solver_recipe"]["history_risk"]):
        raise ValueError("The altered reader, index and renderer must preserve the new identity and exact science")

    totals = Counter()
    for row in frame["members"]:
        totals.update(row["counts"])
    frozen_frame = pair["selective"]
    frame_ids = ("raw_authority", "session_id", "inventory_sha256", "custody_sha256", "reader_sha256", "port_sha256")
    member_ids = ("manifest_sha256", "chunk_index", "payload_sha256", "side_sha256", "counts")
    if (not all(frame[key] == frozen_frame[key] for key in frame_ids)
            or any(any(a[key] != b[key] for key in member_ids) for a, b in zip(frame["members"], frozen_frame["members"], strict=True))
            or dict(totals) != frozen_frame["totals"]):
        raise ValueError("Every encoded member and exact native aperture must remain authenticated")

    orbit_audit = witness["ports"]["portable"]
    attempt, = orbit_audit["attempts"]
    transfer, = orbit_audit["transfers"]
    producer = book["producer"]
    if (not attempt["guard"] or attempt["fallback"] or transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or transfer["sha256"] != producer["artifact_sha256"] or transfer["producer_sha256"] != producer["producer_sha256"]
            or transfer["producer_cutoff_utc_ns"] != producer["producer_cutoff_utc_ns"]
            or transfer["counts"]["sidecar_hit_bodies"] != producer["overlapping_bodies"]):
        raise ValueError("Require observed use of the earlier portable orbit index with original cold completion")
    require_active(witness["ports"]["cairo_layout"])
    media = artifacts(candidate, receipt)
    position = position_sides(FastStandardAnalysisStore(candidate), receipt, media)
    verified_media = read(root/"render-verification.json")
    scene = read(candidate/"render-scene.json")
    if (media_identity(media["images"]) != media_identity(inner["images"])
            or {name: row["sha256"] for name, row in media["images"].items()} != verified_media["hashes"]["residual_layout"]
            or any(media[name] != inner["sidecars"][name] for name in ("grid", "path"))
            or not all(verified_media["same_scene_ordinary_orbit_pngs"].values())
            or verified_media["title"] != scene["title"] or scene["title"] != Path(plan["recording"]).name):
        raise ValueError("Published, reopened and independently rendered artifacts must bind the same titled scene")

    comparison = {metric: price(pair["historical_named"][metric], pair["measured_children"]["ordinary"]["clock"][metric],
                   pair["measured_children"]["frames"]["clock"][metric], clock[metric], book["candidate_ready"][metric],
                   book["custody"][metric], book["producer_clock"][metric]) for metric in ("elapsed_s", "cpu_s")}
    write(root/"result.json", dict(qualified=True, case="DS30-0016", one_candidate=True, preflight=book,
          clocks=comparison, process=clock, phases=raw["phases"], acquisition=dict(totals=totals, setup=frame["setup"]),
          control_frames=dict(phases=old_raw["phases"], timing=old_witness["timing"], portable=old_witness["ports"]["portable"]),
          solver=witness["solver_recipe"], timing=witness["timing"], portable=orbit_audit,
          scientific=dict(science=official, evidence=inner, media=media, position=position, scene=scene,
                          original_geographical_and_rf=previous["reference_geographical_and_rf"]),
          render=verified_media, inherited_writer_costs=pair["writer_costs"],
          previous_title_only_differences=pair["cross_manifest_png_pixel_changes"],
          prediction_seal_sha256=digest(root/"prediction-seal.json")))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("render", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"render": verify_render, "score": score}[args.mode](args.root)
