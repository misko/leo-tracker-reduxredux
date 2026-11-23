"""Bind independently measured aperture factors and replay the dense saved publication."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace

from aperture_factor_union import CENTERED, highest_margin, read as read_aperture
from aperture_trial import ARMS, archive_identity, read, write
from dense_full_short_crossover import file_sha, validate_receipt
from dense_full_short_raw import usage
from dense_geographic_trial import host
from dense_protected_cost import SOURCE, UNFILTERED_PIN
from full_short_crossover import compare_owners, normalized_owners
from full_short_physical import environment
from full_short_raw import RECIPE_SHA
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection
from joint_publication import artifacts, run
from mixed_aperture_receiver import FULL_RULE
from north_factor_swap import continued, rebound

from tools.pipeline_eval.qualification.full_v5_check import factor_candidate


HERE = Path(__file__).resolve().parent
NATIVE = "sha256:ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
BINDING = "1425cca32530cf5ecf22ba9cfb99c79a8aac39dc9a0232202270552968c49ac7"
REFERENCE = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
CENTERED_DSO = "1c77b3d9ad977d9de871ff786bfac16b03fdb0a67923a721bedd284622bddb17"
VISITS = 48


def from_factors(factors):
    candidates = []
    for rank, epoch, offset, hz, exact, control in factors:
        if rank not in (0, 1) or type(epoch) is not int or not all(map(isfinite, (offset, hz, exact, control))):
            raise ValueError("Malformed complete aperture factor")
        factor = factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                                  exact=exact, control=control, margin=exact-control)
        if factor["passed_fractional_margin_gate"] is not True:
            raise ValueError("Aperture factor did not pass the original receiver gate")
        candidates.append(factor)
    return candidates


def metadata(row):
    return {key: value for key, value in row.items() if key != "candidates"}


def streams(rows):
    """Reconstruct anchor enrollment from the full saved stereo chronology."""
    counts = Counter()
    for first, second in zip(rows[::2], rows[1::2], strict=True):
        support = metadata(first)
        if first["receiver_id"] != 0 or metadata(second) != dict(support, receiver_id=1):
            raise ValueError("Expected an original ordered stereo visit")
        stream = tuple(support[k] for k in ("edge", "channel", "actual_rf_hz"))
        mode = FULL_RULE[counts[stream] % len(FULL_RULE)]
        counts[stream] += 1
        yield first, mode
        yield second, mode


def replace(rows, measured, index):
    """Replace complete nonanchor lane results on the exact signed enrollment."""
    replacement, enrollment, modes = [], [], []
    for i, (row, mode) in enumerate(streams(rows)):
        replacement.append(row)
        modes.append(mode)
        if i >= len(measured):
            continue
        sample = measured[i]
        visit, lane = row["visit_index"], row["receiver_id"]
        window = index[visit]
        if (sample["metadata"] != metadata(row) or sample["lane"] != lane
                or sample["key"] != f"DS30-0008:{visit}" or sample["mode"] != mode
                or sample["iq_sha256"] != window["iq_sha256"]
                or row["valid_start_counter"] != window["acquisition"]["sample_start"]):
            raise ValueError("Aperture lane does not match its signed stereo opportunity")
        before, after = (from_factors(sample[name]) for name in ("prefix", "centered"))
        if before != row["candidates"] or len(before) > 1 or len(after) > 1:
            raise ValueError("Aperture receipt does not reproduce the complete native prefix result")
        if mode == "full":
            installed = highest_margin(sample["installed"])
            if before != after or before != from_factors([] if installed is None else [installed]):
                raise ValueError("Measured full anchor differs from the unchanged native anchor")
            continue
        if any(candidate["candidate_rank"] != 0 for candidate in before + after):
            raise ValueError("A short primary lane must record only the native rank zero factor")
        replacement[-1] = dict(row, candidates=after)
        enrollment.append(dict(metadata=metadata(row), iq_sha256=sample["iq_sha256"],
                               prefix=sample["prefix"], centered=sample["centered"]))
    if not measured or len(measured) > len(rows) or len(measured) % 2 != 0:
        raise ValueError("Expected a complete measured stereo prefix")
    return replacement, enrollment, modes


def differences(before, after, modes, boundary):
    out = {}
    changes = []
    for index, (a, b, mode) in enumerate(zip(before, after, modes, strict=True)):
        if metadata(a) != metadata(b):
            raise ValueError("Replay changed opportunity or chronology")
        one, two = a["candidates"], b["candidates"]
        section = "anchor" if mode == "full" else "primary"
        scope = "enrolled" if index < boundary else "later"
        counts = out.setdefault(f"{scope}_{section}", Counter())
        counts.update(opportunities=1, prefix_present=int(bool(one)), centered_present=int(bool(two)))
        if one != two:
            change = "changed_factor" if one and two else "added" if two else "lost"
            counts[change] += 1
            changes.append(dict(metadata=metadata(a), mode=mode, scope=scope, change=change,
                                prefix=one, centered=two))
    return dict(counts={key: dict(value) for key, value in out.items()}, changes=changes)


def inputs(raw, centered):
    from leo.contracts.digests import canonical_digest

    publication = raw / "publication"
    native_path, = (publication / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(native_path)
    binding = read(raw / "binding.json")
    if (canonical_digest(native) != NATIVE or file_sha(raw / "binding.json") != BINDING
            or native["provenance"]["detector_sha256"] != "sha256:" + RECIPE_SHA):
        raise ValueError("The complete original signed recipe or receiver packet changed")
    source = native["source"]
    if (source["raw_recording_authority_digest"], source["input_manifest_sha256"], source["session_id"]) != (
            binding["authority"], binding["inventory"], binding["session"]):
        raise ValueError("The archived receiver differs from its acquisition binding")
    measured = read_aperture(centered, CENTERED)
    authority = measured["dense_authority"]
    manifest = binding["manifest_pins"][0]
    manifest_path = Path(manifest["path"])
    member = authority["member"]
    if (manifest["sha256"] != "sha256:" + authority["manifest_sha256"]
            or "sha256:" + file_sha(manifest_path) != manifest["sha256"]
            or member not in read(manifest_path)["chunks"]
            or len(measured["dense"]["details"]) != 2 * VISITS
            or len(source["probes"]) != 13530 or authority["stop_sequence"] != VISITS):
        raise ValueError("Measured enrollment is outside the original signed acquisition extent")
    index_path = manifest_path.with_name(member["index_relative_path"])
    index_bytes = index_path.read_bytes()
    if len(index_bytes) != member["index_bytes"] or "sha256:" + sha256(index_bytes).hexdigest() != member["index_sha256"]:
        raise ValueError("The indexed I/Q identity changed")
    index = {row["acquisition"]["global_visit"]: row for row in map(json.loads, index_bytes.splitlines())}
    if len(index) != member["window_count"] or tuple(index) != tuple(range(member["window_count"])):
        raise ValueError("The measured index is not the expected original ordered first member")
    if any(order["centered"]["native"]["short_primary_sha256"] != CENTERED_DSO
           for order in measured["dense"]["clocks"]):
        raise ValueError("The centered native recipe changed")
    return native_path, native, binding, measured, index


def build(raw, centered, output):
    from leo.contracts.digests import canonical_digest

    native_path, native, binding, measured, index = inputs(raw, centered)
    rows = native["source"]["probes"]
    alternative, enrollment, modes = replace(rows, measured["dense"]["details"], index)
    identity = dict(recipe="partial saved dense fixed-center primary replacement v1", original_native=NATIVE,
                    original_detector="sha256:" + RECIPE_SHA, centered_receipt="sha256:" + CENTERED,
                    centered_library="sha256:" + CENTERED_DSO, capture_binding="sha256:" + BINDING,
                    window_index=measured["dense_authority"]["member"]["index_sha256"],
                    selected_slots=canonical_digest(enrollment))
    candidate = rebound(native, alternative, identity)
    paths = {"prefix": native_path, "centered": output / "centered-saved-input.json"}
    write(paths["centered"], candidate)
    continued_packets = {"prefix": continued(native), "centered": continued(candidate)}
    receipt = dict(authority="signed original recording, separately bound saved counterfactual",
                   derived_recipe=identity, enrolled=enrollment, raw_differences=differences(rows, alternative, modes, 2 * VISITS),
                   continuation_differences=differences(*(p["source"]["probes"] for p in continued_packets.values()),
                                                        modes, 2 * VISITS),
                   raw_packets={name: dict(path=str(paths[name]), native=canonical_digest(packet),
                                         detector=packet["provenance"]["detector_sha256"],
                                         analysis=packet["source"]["analysis_manifest_sha256"])
                                for name, packet in (("prefix", native), ("centered", candidate))},
                   continued_packets={name: canonical_digest(packet) for name, packet in continued_packets.items()},
                   detector_clocks=measured["dense"]["clocks"], builder_sha256=file_sha(Path(__file__)))
    write(output / "counterfactual-binding.json", receipt)
    return paths, receipt, binding


def launch(raw, centered, output, regional):
    machine = host()
    output.mkdir()
    start = process_time(), perf_counter()
    paths, receipt, binding = build(raw, centered, output)
    archive, region = Path(binding["archive"]["root"]), Path(binding["region"])
    command = binding["command"]
    recording = Path(command[command.index("--recording") + 1])
    geo = Path(command[command.index("--geographic-library") + 1])
    if (archive_identity(archive) != binding["archive"] or file_sha(region) != binding["region_sha256"]
            or file_sha(geo) != GEOGRAPHIC_SHA or file_sha(regional) != TRACK_SCORES_SHA):
        raise ValueError("The original region, numerical libraries or causal archive changed")
    write(output / "build-clock.json", dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1]))
    env = environment(output)
    subprocess.run([sys.executable, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, timeout=20, env=env)
    write(output / "launch-binding.json", dict(machine=machine, causal_archive=binding["archive"],
                                               offer_sha256=binding["region_sha256"], geographic_sha256=GEOGRAPHIC_SHA,
                                               regional_sha256=TRACK_SCORES_SHA, order=list(paths)))
    for label, path in paths.items():
        packet = receipt["raw_packets"][label]
        cmd = [sys.executable, "-BPs", __file__, "worker", path, packet["native"], packet["detector"][7:],
               output / label, recording, archive, region, geo, regional]
        start, before = perf_counter(), usage()
        with (output / f"{label}.log").open("x") as log:
            result = subprocess.run(cmd, timeout=90, stdout=log, stderr=subprocess.STDOUT, env=env)
        after = usage()
        write(output / f"{label}-process.json", dict(command=list(map(str, cmd)), status=result.returncode,
              elapsed_s=perf_counter()-start, **{key: after[key]-before[key] for key in before}))
        result.check_returncode()


def evidence(folder, native):
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    research = read(folder / "joint-research-receipt.json")
    receipt = research["receipt"]
    folder_run = folder / "fast-scan-automatic-work" / receipt["run_id"]
    terminal = read(folder_run / "terminal.json")
    store = FastStandardAnalysisStore(folder)
    detail = store.detail(receipt["run_id"])
    source = native["source"]
    validate_receipt(terminal, detail, receipt, canonical_digest(native), receipt["region"],
                     source["session_id"], source["raw_recording_authority_digest"])
    solve = research["solve"]
    proof, = research["early_regional"]
    projection = solve["geographic_projector"]
    if (research["saved_digest"] != terminal["native_sha256"] or research["saved_handoff_manifest"] != source["input_manifest_sha256"]
            or not research["full_catalogue"] or not research["optimized_full_catalogue"] or not research["signed_finish"]
            or projection["track_score_native"] != proof["result"]["probes_evaluated"] or projection["track_score_fallbacks"]
            or not solve["cold_track_rows"]["reused_requests"]):
        raise ValueError("The publication did not use the original unfiltered optimized saved route")
    science = json.loads(json.dumps(artifacts(folder, receipt)))
    if science != research["evidence"]:
        raise ValueError("Reopened report artifacts differ from the sealed solver output")
    result = dict(terminal=terminal, terminal_sha256=receipt["terminal_sha256"], science=science,
                  selected_rows=research["selected_rows"], region=research["early_regional"],
                  solve=research["solve"], route=research["route"], route_details=research["route_details"],
                  selected_roles=research["selected_roles"], graph=receipt["graph_path"],
                  publication=dict(cpu_s=research["publication_cpu_s"], elapsed_s=research["publication_elapsed_s"]),
                  source_sha256=research["source_sha256"])
    if receipt["decision"] == "complete":
        grid = store.position_grid(receipt["run_id"])
        if not grid["complete"] or research["solve"]["objective_replay"] != dict.fromkeys(ARMS, 0.0):
            raise ValueError("Full grid lacks exact endpoint replay")
        for arm in ARMS:
            rows = result["selected_rows"][arm]
            owners = {oid: int(norad) for oid, norad, _role in rows}
            if owner_digest(owners) != detail["arms"][arm]["owner_sha256"] or len(owners) != len(rows):
                raise ValueError("Published owners differ from the signed solver rows")
        result["grid"] = grid
        result["arms"] = detail["arms"]
    return result


def grid_without_elapsed(grid):
    return {key: value for key, value in grid.items() if key != "elapsed_seconds"}


def compare_endpoints(prefix, centered):
    from tools.pipeline_eval.scoring import distance_km

    changes = {}
    for arm in ARMS:
        first, second = (result["terminal"]["arms"].get(arm, {}) for result in (prefix, centered))
        if first.get("latlon") and second.get("latlon"):
            changes[arm] = dict(
                shift_km=distance_km(first["latlon"], second["latlon"]),
                horizontal_error_delta_km=centered["horizontal_error_km"][arm] - prefix["horizontal_error_km"][arm],
                rf_rms_delta_hz=second["rf_rms_hz"] - first["rf_rms_hz"],
            )
    return changes


def score(output, result_path):
    from dense_full_short_crossover_score import REFERENCE as reference_path
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.scoring import distance_km

    binding = read(output / "counterfactual-binding.json")
    packets = {name: read(Path(packet["path"])) for name, packet in binding["raw_packets"].items()}
    if any(canonical_digest(packets[name]) != pin["native"] for name, pin in binding["raw_packets"].items()):
        raise ValueError("A replay packet changed after binding")
    archived = SOURCE / "native"
    if file_sha(archived / "joint-research-receipt.json") != UNFILTERED_PIN:
        raise ValueError("The original complete installed-graph comparison changed")
    original = evidence(archived, packets["prefix"])
    results = {name: evidence(output / name, packet) for name, packet in packets.items()}
    prefix = results["prefix"]
    if (prefix["terminal"] != original["terminal"] or prefix["selected_rows"] != original["selected_rows"]
            or prefix["route"] != original["route"]
            or any(prefix["science"][key] != original["science"][key] for key in ("images", "path"))
            or grid_without_elapsed(prefix["grid"]) != grid_without_elapsed(original["grid"])
            or any(row["region"][0]["result"]["snapshots"] != prefix["region"][0]["result"]["snapshots"]
                   for row in results.values())):
        raise ValueError("Saved prefix replay did not reproduce the archived complete publication")
    if file_sha(reference_path) != REFERENCE:
        raise ValueError("The survey scoring reference changed")
    survey, = [case["reference"] for case in read(reference_path)["cases"]
               if case["dataset_label"] == "DS30-0008" and case["authority_eligible"]]
    truth = [survey["latitude_deg"], survey["longitude_deg"]]
    for name, result in results.items():
        result["horizontal_error_km"] = {arm: distance_km(values["latlon"], truth)
                                         for arm, values in result["terminal"]["arms"].items() if values["latlon"]}
        result["process"] = read(output / f"{name}-process.json")
    owners = compare_owners(*(normalized_owners(packets[name], results[name]["selected_rows"])
                              for name in ("prefix", "centered")))
    write(result_path, dict(binding=binding, build_clock=read(output / "build-clock.json"),
                            launch_binding=read(output / "launch-binding.json"), original_terminal=original["terminal_sha256"],
                            receiver_owner_changes=owners, endpoint_changes=compare_endpoints(prefix, results["centered"]),
                            survey_sha256=REFERENCE,
                            results=results))


def main():
    cli = ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="mode", required=True)
    for mode, fields in (("launch", ("raw", "centered", "output", "regional")),
                         ("score", ("output", "result_path")),
                         ("worker", ("saved", "saved_digest", "pin", "output", "recording", "archive", "region", "geo", "regional"))):
        parser = modes.add_parser(mode)
        for field in fields:
            parser.add_argument(field, type=str if field in ("saved_digest", "pin") else Path)
    args = vars(cli.parse_args())
    mode = args.pop("mode")
    if mode == "worker":
        options = SimpleNamespace(**args, optimized_full_catalogue=True, verify_images=True)
        run(options, early_regional=True, keep_selected_rows=True, saved_receiver=options.pin,
            geographic_projector=lambda: geographic_projection(options.geo, options.regional),
            reuse_cold_rows=True, reuse_grid_phase_states=True)
    else:
        {"launch": launch, "score": score}[mode](**args)


if __name__ == "__main__":
    main()
