"""Replay two late chronological cutoffs on genuine short-receiver detections."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, read, write
from contiguous_third import calibration_owners, native_signature, observe_prepared
from dense_full_short_crossover import file_sha
from dense_full_short_raw import PAIR, PAIR_SHA, checked, usage
from dense_geographic_trial import elapsed, host, now
from full_short_physical import environment
from full_short_raw import RECIPE_SHA
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, geographic_projection


HERE = Path(__file__).resolve().parent
NATIVE = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-short-raw-diagnostic-pairs/native-builds")
GEOGRAPHIC, SCORES = NATIVE / "geographic.so", NATIVE / "regional-track-scores.so"
ORDER = {"north": ("half", "three-quarters"), "DS30-0008": ("three-quarters", "half")}
FRACTIONS = {"half": (1, 2), "three-quarters": (3, 4)}
DENSE = Path("/var/tmp/leo-v3-regional-dense-pair")
NORTH = Path("/var/tmp/leo-north-short-regional-nov23/containing")


def work_plan(native, cut):
    from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs
    from mixed_aperture_receiver import FULL_RULE

    inventories(native)
    prefix, suffix, streams = Counter(), Counter(), Counter()
    for visit, pair in visit_pairs(native["source"]["probes"]):
        p = pair[0]
        key = p["edge"], p["channel"], p["actual_rf_hz"]
        mode = FULL_RULE[streams[key] % len(FULL_RULE)]
        streams[key] += 1
        branch = prefix if visit < cut else suffix
        branch[mode] += len(pair)
    return prefix, suffix


def project(native, mode):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.capture_bursts import select_document

    source, provenance = native["source"], native["provenance"]
    count = provenance["window_count"]
    numerator, denominator = FRACTIONS[mode]
    cut = count*numerator//denominator
    probes = source["probes"]
    old = source["analysis_manifest_sha256"]
    detector = provenance["detector_sha256"]
    if (cut < 1 or detector != "sha256:" + RECIPE_SHA or provenance["scope"] != "cancellation"
            or source["sample_rate_hz"] != 10_000_000 or not source["qualified"]
            or native_signature(source, detector, probes) != old):
        raise ValueError("Expected sealed genuine all-visit 20/12 ms factors")
    kept_work, omitted_work = work_plan(native, cut)
    admitted = {row["visit_index"] for row in probes if row["visit_index"] < cut}
    truncated = select_document(native, admitted, old)
    retained = truncated["source"]["probes"]
    digest = native_signature(source, detector, retained)
    if digest == old:
        raise ValueError("This cut has no later candidates to remove")
    truncated["source"]["analysis_manifest_sha256"] = digest
    truncated["provenance"]["run_id"] = "blind-compact-" + digest[7:39]
    return truncated, dict(mode=mode, issued_total=count, issued_prefix=cut, pre_start_clock=canonical_digest(native["clock_anchor"]),
                           kept_native_lanes=dict(kept_work), skipped_native_lanes=dict(omitted_work),
                           opportunity_rows=len(probes), full_factors=sum(len(p["candidates"]) for p in probes),
                           prefix_factors=sum(len(p["candidates"]) for p in retained),
                           prefix_probe_sha256=canonical_digest([p for p in probes if p["visit_index"] < cut]),
                           analysis_manifest_sha256=digest, native_sha256=canonical_digest(truncated))


def original_members(publication_root, native):
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader

    source = native["source"]
    inventory = FastScanStore(publication_root).source(source["session_id"], source["input_manifest_sha256"])
    members, done = [], 0
    for item in inventory["segments"]:
        reader = ShortWindowReader(Path(item["path"]))
        manifest = reader.manifest
        if reader.manifest_sha256 != item["manifest_digest"] or manifest.window_count != item["windows"]:
            raise ValueError("Sealed capture member inventory changed")
        members.extend(dict(stop=done+chunk.first_sequence+chunk.window_count, compressed=chunk.compressed_bytes,
                            decoded=chunk.uncompressed_bytes, index=chunk.index_bytes) for chunk in manifest.chunks)
        done += manifest.window_count
    if done != native["provenance"]["window_count"]:
        raise ValueError("The original members do not cover every signed opportunity")
    return members


def source(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from joint_publication import artifacts

    if case == "DS30-0008":
        from regional_dense_pair import reference

        replay, bind = reference(), read(checked(DENSE / "binding.json",
            "2d93dd6db50e0ff697fbfc33d69ebaceb0475a2ebf3296e7368a30e8c551d3cb"))
        full, original = DENSE / "native", Path("/var/tmp/leo-full-short-dense-DS30-0008/publication")
        command = replay["raw"]["binding"]["command"]
        rec, region = (Path(command[command.index("--" + field)+1]) for field in ("recording", "region"))
        archive, offer, pin = bind["archive"], bind["offer"], bind["packet_sha256"]
        report_pin = "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"
        recipe_pin = "a86307c85d8405fd9c4a14b4bd09066f924016c82922b02b65d05557a6dc89bb"
        named = read(checked(HERE / "measurements/dense-control-clocks.json",
                             "ae947ab9906b878b9491f9c4a227f0dd4f14c0332891d46b9f0b4a61264c910a"))
        stock = read(checked(PAIR, PAIR_SHA))["runs"]["baseline"]
        if named["common"]["terminal_sha256"] != stock["receipt"]["terminal_sha256"]:
            raise ValueError("Named launcher science differs from the bound archive")
        named_arms, named_process = stock["arms"], named["controls"]["named_launcher"]
        named_pin, authority = named["common"]["terminal_sha256"], named["common"]["raw_authority"]
    elif case == "north":
        from short_stereo_trial import source_for

        rec, archive, region, _, pin, offer = source_for("north")
        full = original = NORTH
        report_pin = "3d8beaf10a6d3e9c4025627fec4a8a0f864f78e6fd4d6c6061573b1a4b7f2f13"
        recipe_pin = "1527e0760265da4888ae5037c3f9edbf49884bb61ad19e40e5e95017d2528912"
        named = read(checked(HERE / "measurements/north-combined.json",
                             "871105154ab79679308cf7455ee10c236094d8735a02c17ed11bb2412283172e"))["cases"]["stock"]
        stock, = (NORTH.parent / "stock/fast-scan-automatic-work").glob("*/terminal.json")
        terminal = read(stock)
        native_stock, = (NORTH.parent / "stock/fast-scan-automatic-work").glob("*/detections.json")
        stock_packet = read(native_stock)
        if (canonical_digest(terminal) != named["terminal_sha256"] or terminal["native_sha256"] != named["native_sha256"]
                or file_sha(native_stock) != terminal["native_sha256"].removeprefix("sha256:")
                or terminal["region"] != offer):
            raise ValueError("Northern named terminal or source changed")
        named_arms, named_process = terminal["arms"], named["process"]
        named_pin, authority = named["terminal_sha256"], stock_packet["source"]["raw_recording_authority_digest"]
    else:
        raise ValueError("Unknown frozen capture")
    report = read(checked(full / "joint-research-receipt.json", report_pin))
    audit = read(checked(original / "full-short-recipe.json", recipe_pin))["receiver_audit"]
    packet, = (full / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(packet)
    receipt = report["receipt"]
    terminal = read(full / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    if (canonical_digest(native) != pin or file_sha(packet) != pin.removeprefix("sha256:")
            or canonical_digest(terminal) != receipt["terminal_sha256"] or terminal["native_sha256"] != pin
            or terminal["region"] != offer or receipt["region"] != offer or Algo08Region.parse(read(region)).document() != offer
            or archive_identity(Path(archive["root"])) != archive
            or native["source"]["raw_recording_authority_digest"] != audit["recording_authority"]
            or authority != audit["recording_authority"] or audit["issued"] != native["provenance"]["window_count"]
            or native["source"]["analysis_manifest_sha256"] != audit["analysis_manifest"]
            or report["route"] != "complete" or not report["solve"]["grid_complete"]
            or json.loads(json.dumps(artifacts(full, receipt))) != report["evidence"]):
        raise ValueError("Same-build publication, raw audit or causal authority changed")
    controls = dict(full=dict(arms=terminal["arms"], terminal_sha256=receipt["terminal_sha256"],
                              solve=report["solve"], graph_path=receipt["graph_path"],
                              early_regional=report["early_regional"], selected_rows=report["selected_rows"],
                              images=report["evidence"]["images"], report_sha256=report_pin),
                    named=dict(arms=named_arms, process=named_process, terminal_sha256=named_pin),
                    raw_audit=audit, raw_audit_sha256=recipe_pin, members=original_members(full, native))
    binding = dict(case=case, recording=str(rec), archive=archive, region=str(region), offer=offer,
                   native_sha256=pin, raw_authority=authority)
    return native, binding, controls


def native_budget(clocks, mask):
    modes = clocks["native"]["native_calls"]
    costs = clocks["native"]["native_cpu_ns"]
    for key, total in modes.items():
        skipped = mask["skipped_native_lanes"].get(key, 0)
        if total <= 0 or mask["kept_native_lanes"].get(key, 0) + skipped != total:
            raise ValueError("Reconstructed aperture schedule differs from measured raw lanes")
    if set(mask["kept_native_lanes"]) | set(mask["skipped_native_lanes"]) != modes.keys():
        raise ValueError("Unexpected native aperture")
    estimate = sum(mask["skipped_native_lanes"].get(k, 0) * costs[k] / count for k, count in modes.items()) / 1e9
    measured_native = sum(costs.values()) / 1e9
    acquire = clocks["acquire"]["cpu_ns"] / 1e9
    return dict(estimated_omitted_native_cpu_s=estimate, measured_full_native_cpu_s=measured_native,
                remaining_native_cpu_s=measured_native-estimate, fixed_nonnative_acquisition_cpu_s=acquire-measured_native,
                modeled_total_acquisition_cpu_s=acquire-estimate)


def verification_budget(members, cut):
    keys = ("compressed", "decoded", "index")
    return dict(all_bytes={k: sum(m[k] for m in members) for k in keys},
                suffix_intersecting_members=sum(m["stop"] > cut for m in members),
                suffix_intersecting_bytes={k: sum(m[k] for m in members if m["stop"] > cut) for k in keys})


def worker(recording, archive, region, output, saved, saved_pin):
    from joint_publication import run
    from tools.pipeline_eval.qualification import experimental_publication as publication

    original = publication.run
    graph = []

    def instrument(*args, **kwargs):
        # The release's lazy facades are initialized by configuration before this port.
        from leo.application import localization_v3 as application

        prepare = application.prepare_tracks

        def measure(*values, **options):
            start = now()
            prepared = prepare(*values, **options)
            graph.append(elapsed(start))
            return prepared

        with patch.object(application, "prepare_tracks", measure):
            return original(*args, **kwargs)

    args = SimpleNamespace(recording=recording, archive=archive, region=region, output=output, saved=saved,
                           saved_digest=saved_pin, optimized_full_catalogue=True, observe_prepared=observe_prepared,
                           verify_images=True)
    with patch.object(publication, "run", instrument):
        run(args, early_regional=True, saved_receiver=RECIPE_SHA,
            geographic_projector=lambda: geographic_projection(GEOGRAPHIC, SCORES), reuse_cold_rows=True,
            reuse_grid_phase_states=True)
    write(output / "timed-graph.json", graph)


def record(directory, native, binding):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    report = read(directory / "joint-research-receipt.json")
    receipt = report["receipt"]
    complete = receipt["decision"] == "complete"
    run_id = receipt["run_id"]
    terminal = read(directory / "fast-scan-automatic-work" / run_id / "terminal.json")
    solve, output = report["solve"], report["evidence"]
    calibration_owners(native, report["selected_rows"])
    if (terminal["region"] != binding["offer"] or receipt["region"] != binding["offer"]
            or terminal["native_sha256"] != canonical_digest(native) or terminal["native_sha256"] != report["saved_digest"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or native["source"]["raw_recording_authority_digest"] != binding["raw_authority"]):
        raise ValueError("The projected packet or terminal diverged from the bound recording")
    if (complete and (not solve["grid_complete"] or set(output["images"]) != set(PLOTS))
            or not complete and (receipt["decision"] != "withheld" or output["images"])):
        raise ValueError("Incomplete or inconsistent standard numerical and figure evidence")
    detail = FastStandardAnalysisStore(directory).detail(run_id)
    if detail["terminal_sha256"] != receipt["terminal_sha256"]:
        raise ValueError("Standard output disagrees with the original terminal")
    return dict(terminal=terminal, terminal_sha256=receipt["terminal_sha256"], solve=solve, evidence=output,
                route=report["route"], route_details=report["route_details"],
                graph=read(directory / "timed-graph.json"), graph_path=receipt["graph_path"],
                early_regional=report["early_regional"], selected_rows=report["selected_rows"],
                publication_cpu_s=report["publication_cpu_s"], publication_elapsed_s=report["publication_elapsed_s"])


def run(root):
    from aperture_trial import RELEASE

    settings = host()
    for binary, pin in ((GEOGRAPHIC, GEOGRAPHIC_SHA), (SCORES, TRACK_SCORES_SHA)):
        checked(binary, pin)
    root.mkdir(exist_ok=False)
    env = environment(root)
    env["TMPDIR"] = str(root)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    for case, modes in ORDER.items():
        native, binding, controls = source(case)
        case_root = root / case
        case_root.mkdir()
        write(case_root / "binding.json", dict(binding=binding, controls=controls, machine=settings, order=modes,
                                              driver_sha256=file_sha(Path(__file__)),
                                              projector_sha256=GEOGRAPHIC_SHA, regional_sha256=TRACK_SCORES_SHA))
        plans = {mode: project(native, mode) for mode in modes}
        for mode in modes:
            projected, mask = plans[mode]
            packet, output = case_root / f"{mode}-input.json", case_root / mode
            write(packet, projected)
            command = [python, "-BPs", str(Path(__file__)), "worker", binding["recording"], binding["archive"]["root"],
                       binding["region"], str(output), str(packet), mask["native_sha256"]]
            before, started = usage(), perf_counter()
            try:
                launch = subprocess.run(command, env=env, capture_output=True, text=True, timeout=100)
                failure = launch.stderr[-5000:] if launch.returncode else None
            except subprocess.TimeoutExpired as exc:
                failure = str(exc)
            after = usage()
            process = dict(elapsed_s=perf_counter()-started, **{k: after[k]-before[k] for k in before})
            measure = dict(mask=mask, budget=native_budget(controls["raw_audit"], mask),
                           authentication=verification_budget(controls["members"], mask["issued_prefix"]),
                           process=process, failure=failure, command=command)
            if failure is None:
                measure["result"] = record(output, projected, binding)
            write(case_root / f"{mode}-sealed.json", measure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("run").add_argument("root", type=Path)
    save = modes.add_parser("worker")
    for argument in ("recording", "archive", "region", "output", "saved"):
        save.add_argument(argument, type=Path)
    save.add_argument("saved_pin")
    args = vars(parser.parse_args())
    {"run": run, "worker": worker}[args.pop("mode")](**args)
