"""Verify both new recording identities and compare physical science across encodings."""

from collections import Counter
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from visit_frame_raw_0016 import ORDER, REFERENCE, digest, read, references, source_pins


def native_science(native):
    source = {key: value for key, value in native["source"].items() if key not in (
        "session_id", "input_manifest_sha256", "analysis_manifest_sha256", "raw_recording_authority_digest")}
    provenance = {key: value for key, value in native["provenance"].items() if key != "run_id"}
    return dict(native, source=source, provenance=provenance)


def branch_science(value):
    if isinstance(value, dict):
        return {k: branch_science(v) for k, v in value.items()
                if k not in ("cpu_s", "elapsed_s", "cpu_ns", "wall_ns", "elapsed_ns", "input_blocks")}
    if isinstance(value, list):
        return [branch_science(v) for v in value]
    return value


def physical_owner_rows(native, owners):
    # The released frequency adapter feeds precisely this identity to Graph.
    source = native["source"]
    observations = {}
    for probe in source["probes"]:
        receiver, counter = probe["receiver_id"], probe["valid_start_counter"]
        ident = "sha256:"+sha256(f"{source['session_id']}:{receiver}:{counter}".encode()).hexdigest()
        if ident in observations:
            raise ValueError("Physical observation identity is not bijective")
        observations[ident] = (receiver, counter, probe["visit_index"], probe["channel"], probe["actual_rf_hz"])
    return {arm: [(*observations[ident], label, role) for ident, label, role in rows] for arm, rows in owners.items()}


def image_labels(before, before_run, old, following, following_run, new):
    import numpy as np
    from PIL import Image
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    changes = {}
    old_store, new_store = FastStandardAnalysisStore(before), FastStandardAnalysisStore(following)
    for name, new_image in new.items():
        older = old[name]
        with (Image.open(BytesIO(old_store.artifact(before_run, name, older["sha256"]))) as first,
              Image.open(BytesIO(new_store.artifact(following_run, name, new_image["sha256"]))) as second):
            a, b = np.asarray(first.convert("RGBA")), np.asarray(second.convert("RGBA"))
        if a.shape != b.shape or sha256(a.tobytes()).hexdigest() != older["rgba_sha256"] or sha256(
                b.tobytes()).hexdigest() != new_image["rgba_sha256"]:
            raise ValueError("Readback figure differs from its independently sealed size or pixels")
        y, x = np.where(np.any(a != b, axis=-1))
        # Title rows of the four original Cairo/Matplotlib sheet layouts.
        top, bottom = ((18, 50) if name == "position" else (65, 100) if name == "track-rms"
                       else (24, 52) if name.endswith("residuals") else (30, 76))
        changes[name] = dict(old_sha256=older["sha256"], new_sha256=new_image["sha256"],
                             rgba_exact=not len(x), encoded_exact=older["sha256"] == new_image["sha256"],
                             differing_pixels=len(x), examined_title_y=[top, bottom],
                             bbox_xyxy=None if not len(x) else [int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)],
                             exact_outside_title=not np.any((y < top) | (y >= bottom)))
    return changes


def publication(folder, log, plan, historical):
    from empty_bootstrap import bind_native
    from reports.ALGO08.v3.history_risk_0016_cairo import active_renderer
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.qualification import paired_publication

    raw = read(folder/"unified-short-bootstrap.json")
    witness = read(folder/"exact-named-raw-witness.json")
    receipt = raw["receipt"]
    published = paired_publication.evidence(folder, receipt, log["clock"]["started_unix_ns"], read_only=True)
    packet, = (folder/"fast-scan-automatic-work").glob("*/detections.json")
    native = read(packet)
    bind_native(native, plan["session_id"], plan["inventory_sha256"], historical["detector"][7:])
    if (digest(packet) != raw["native_sha256"] or native["source"]["raw_recording_authority_digest"] != plan["raw_authority"]
            or receipt["session_id"] != plan["session_id"] or published["raw_authority"] != plan["raw_authority"]
            or raw["archive_root"] != historical["archive"]["root"] or raw["causal_cutoff_utc_ns"] != historical["cutoff_utc_ns"]
            or raw["requested_offer_sha256"] != historical["offer_sha256"]
            or receipt["window_count"] != 808 or receipt["counts"] != dict(processed=713, invalid_capture=95, skipped_fast_score=0)
            or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or raw["scientific_imports_before"]
            or raw.get("packed_ci16_input") is not None):
        raise ValueError("Raw publication changed its recording, authentic scope or original offer")
    media = artifacts(folder, receipt)
    terminal_complete = receipt["decision"] == "complete"
    sides, owners = None, {}
    if terminal_complete:
        store = FastStandardAnalysisStore(folder)
        sides = position_sides(store, receipt, media)
        owners = witness["evidence"]["owner_rows"]
        if (set(owners) != {"c0", "fitted_c"} or len(media["images"]) != 8
                or any(canonical_digest({oid: label for oid, label, _ in rows}) != published["owners"][arm]
                       or len({row[0] for row in rows}) != len(rows) for arm, rows in owners.items())
                or not active_renderer(witness["ports"])):
            raise ValueError("The issued fix must verify ordered ownership and all active standard Cairo products")
    return dict(native=native, raw=raw, witness=witness, published=published, figs=media["images"],
                sides=sides, owners=owners, detector_file_s=(packet.stat().st_mtime_ns-log["clock"]["started_unix_ns"])/1e9)


def read_mode(root, mode, scores, plan, reference):
    from leo.contracts.digests import canonical_digest

    log = scores[mode]
    record = publication(root/mode, log, plan, reference)
    if not (root/mode/"visit-frame-acquisition.json").exists():
        if mode != "ordinary":
            raise ValueError("The frame reader did not prove its real input path")
        return dict(record, selective=None)
    audit = read(root/mode/"visit-frame-acquisition.json")
    if mode != "frames" or any(audit[name] != plan[name] for name in ("session_id", "raw_authority", "inventory_sha256")):
        raise ValueError("Unexpected selective scope, or new custody not observed")
    expected = [(s["manifest_sha256"], m["chunk_index"], m["compressed_sha256"], m["side_sha256"])
                for s in plan["segments"] for m in s["members"]]
    actual = [(m["manifest_sha256"], m["chunk_index"], m["payload_sha256"], m["side_sha256"])
              for m in audit["members"]]
    if actual != expected:
        raise ValueError("Selective traversal did not cover all 13 original-order encoded members")
    totals = Counter()
    for member in audit["members"]:
        totals.update(member["counts"])
    visits = record["raw"]["receiver_audit"]["native"]["visits"]
    encoded = sum(m["compressed_bytes"] for s in plan["segments"] for m in s["members"])
    if (totals["authenticated_encoded_bytes"] != encoded or totals["full_checks"] != visits["full"]
            or totals["prefix_checks"] != visits["short_primary"]
            or totals["decoded_bytes"] != visits["full"]*1_600_000+visits["short_primary"]*640_000):
        raise ValueError("Selective path did not authenticate and decode the scheduled original apertures")
    result = dict(audit, totals=dict(totals), signed_ordered_members_sha256=canonical_digest(expected))
    return dict(record, selective=result)


def writer_times(writer):
    clocks = writer["clocks"]
    readback = writer["readback"]
    groups = dict(original_hydration=[member["clock"] for segment in clocks for member in segment["hydrate"]],
                  encoded_writer=[s["writer"] for s in clocks], seek_tables=[s["seek"] for s in clocks],
                  detached_custody=[writer["custody_write_clock"]], independent_full_readback=[readback["stock_clock"]],
                  independent_prefix_readback=[m["clock"] for m in readback["seek_checks"]])
    return {name: {field.replace("_ns", "_s"): sum(item[field] for item in events)/1e9 for field in ("cpu_ns", "wall_ns")}
            for name, events in groups.items()}


def score(root):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import image_comparison_fields, verify_position_sidecars

    base = references()
    reference, previous = base["admission"]["request"], base["native"]
    admission = read(root/"admission.json")
    if source_pins() != admission["sources"] or any(digest(root/name) != recorded
                                                    for name, recorded in read(root/"sealed.json").items()):
        raise ValueError("The controller's paid clocks or inputs changed after sealing")
    logs = {mode: read(root/(mode+"-clock.json")) for mode in ORDER}
    result = dict(case="DS30-0016", admission=admission, measured_children=logs, qualified=False,
                  writer_costs=writer_times(admission["writer_receipt"]), historical_named=base["reused_stock"],
                  historical_ordinary_cairo=base["optional_process"]["clock"], original_waveform_replays=2)
    if any(log["clock"]["exit_code"] for log in logs.values()):
        write(root/"score-qualified.json", result)
        return
    records = {mode: read_mode(root, mode, logs, admission["source"], reference) for mode in ORDER}
    old_packet, = (REFERENCE/"candidate/fast-scan-automatic-work").glob("*/detections.json")
    if digest(old_packet) != reference["native"]:
        raise ValueError("The original-format history-risk control changed")
    old = read(old_packet)
    a, b = (records[mode] for mode in ORDER)
    inline = {mode: record["published"] for mode, record in records.items()}
    within_new = dict(same_new_signed_native=a["native"] == b["native"],
                  new_terminal=a["published"]["receipt"]["terminal_sha256"] == b["published"]["receipt"]["terminal_sha256"],
                  positions_and_rf=a["published"]["arms"] == b["published"]["arms"], owners=a["owners"] == b["owners"],
                  path_grid=a["published"]["scientific_digests"] == b["published"]["scientific_digests"],
                  full_png_pairs=image_comparison_fields(a["figs"]) == image_comparison_fields(b["figs"]),
                  both_completed=all(record["published"]["receipt"]["decision"] == "complete" for record in records.values()),
                  history_risk_branch=branch_science(a["witness"]["solver_recipe"]) == branch_science(b["witness"]["solver_recipe"]),
                  verified_source_and_port=b["selective"]["custody_sha256"] == admission["authority_sha256"] and
                       b["selective"]["reader_sha256"] == admission["sources"]["visit_frame_reader.py"] and
                       b["selective"]["port_sha256"] == admission["sources"]["visit_frame_input.py"])
    within_new["phase_split"] = all(log["command"] == admission["commands"][mode] for mode, log in logs.items())
    sidecars = None
    cross, labels = {}, {}
    if all(within_new[key] for key in ("full_png_pairs", "both_completed", "new_terminal")):
        run = a["published"]["receipt"]["run_id"]
        sidecars = verify_position_sidecars(root/"ordinary", root/"frames", run, a["figs"], b["figs"])
        labels = image_labels(REFERENCE/"candidate", previous["science"]["receipt"]["run_id"], previous["figures"],
                              root/"frames", run, b["figs"])
        old_owners = physical_owner_rows(old, previous["owners"])
        cross = dict(same_physical_waveform_and_observations=all(native_science(r["native"]) == native_science(old)
                                                               for r in records.values()),
                     positions_rf=b["published"]["arms"] == previous["science"]["arms"],
                     path_grid=b["published"]["scientific_digests"] == previous["science"]["scientific_digests"],
                     owners_with_signed_measurement_bijection=physical_owner_rows(b["native"], b["owners"]) == old_owners,
                     exact_png_pixels_outside_recording_title=len(labels) == 8 and all(
                         item["exact_outside_title"] for item in labels.values()),
                     new_session_and_provenance=a["native"]["source"]["session_id"] != old["source"]["session_id"] and
                         a["raw"]["native_sha256"] != reference["native"])
    result.update(qualified=all(within_new.values()) and bool(cross) and all(cross.values()), within_new=within_new,
                  cross_manifest=cross, cross_manifest_png_pixel_changes=labels, media_binding=sidecars, science=inline,
                  raw_owner_ids_equal_across_manifests=b["owners"] == previous["owners"],
                  full_pngs_equal_across_manifests=bool(labels) and all(item["encoded_exact"] for item in labels.values()),
                  original_literal_score_sha256=digest(root/"result.json") if (root/"result.json").exists() else None,
                  ordered_owner_sha256={mode: canonical_digest(record["owners"]) for mode, record in records.items()},
                  figures={mode: record["figs"] for mode, record in records.items()}, selective=b["selective"],
                  acquired={mode: {key: record["raw"][key] for key in ("native_sha256", "receiver_audit", "prefetch", "phases")}
                            for mode, record in records.items()},
                  output_identities={mode: {"session": record["raw"]["receipt"]["session_id"],
                                           "run": record["raw"]["receipt"]["run_id"],
                                           "terminal": record["raw"]["receipt"]["terminal_sha256"]}
                                     for mode, record in records.items()})
    write(Path(root)/"score-qualified.json", result)
