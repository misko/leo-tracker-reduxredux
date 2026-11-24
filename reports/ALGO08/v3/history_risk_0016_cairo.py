"""Run one optional Cairo raw child against the completed ordinary DS30-0016 pair."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from time import perf_counter

from . import history_risk_0016_raw as ordinary


OPTION = "--cairo-six-sheets"
ARTISTS = {"ch1-4-orbit", "ch5-8-orbit", "ch1-4-residuals", "ch5-8-residuals", "track-rms", "position"}
LAYOUT_COUNTS = {"native_orbit_figures": 4, "native_residual_figures": 2, "position_figures": 1, "track_figures": 1}
PNG_COUNTS = {"verified": 8, "reused": 8, "fallbacks": 0}
GATE = ordinary.MEASUREMENTS/"history-risk-cairo-physical.json.gz"
GATE_PIN = "4f129557c9df0cfd25a9c8a13dbdfac39f409808773aeba69026cfd92f609251"


def checked_json(path, pin):
    from empty_bootstrap import checked
    from exact_named_raw import staged_path

    return json.loads(checked(staged_path(path), pin))


def active_renderer(ports):
    return (all(ports.get("cairo_layout", {}).get(key) == value for key, value in LAYOUT_COUNTS.items())
            and all("fallback" not in key or value == 0 for key, value in ports.get("cairo_layout", {}).items())
            and all(ports.get("png", {}).get(key) == value for key, value in PNG_COUNTS.items()))


def gate_document(path):
    from empty_bootstrap import checked

    doc = json.loads(gzip.decompress(checked(path, GATE_PIN)))
    if doc["timed_source"] != "b325a5f1f":
        raise ValueError("Expected the independently sealed DS30-0016 renderer gate")
    return doc["verified"]


def saved_gate(document, request, reference, plot_names):
    runs = document["runs"]
    standard, cairo = (runs[name] for name in ("standard", "cairo"))
    if (set(document["artists"]) != ARTISTS or set(document["sidecars"]) != {"grid", "path"}
            or set(document["media"]) != set(plot_names) or not active_renderer(cairo["scientific"]["ports"])
            or any(run["clock"]["exit_code"] or run["terminal"] != reference["terminal"] for run in runs.values())
            or any(set(run["scientific"]["evidence"]["images"]) != set(plot_names)
                   or run["receipt"]["decision"] != "complete" or run["receipt"]["session_id"] != request["session"]
                   or run["scientific"]["evidence"]["owner_rows"] != reference["scientific"]["evidence"]["owner_rows"]
                   or any(run["scientific"]["ports"]["png"].get(key) != value for key, value in PNG_COUNTS.items())
                   for run in runs.values())
            or standard["scientific"]["evidence"]["images"] != reference["scientific"]["evidence"]["images"]
            or cairo["clock"]["elapsed_s"] >= standard["clock"]["elapsed_s"]):
        raise ValueError("The independently scored saved Cairo publication must pass every semantic and speed gate")
    for name, evidence in document["artists"].items():
        if not evidence["axes"] or name.endswith("-orbit") and evidence["changed_tick_sets"] != 0:
            raise ValueError("The direct renderer did not pass the original visible axis audit")
    for name, detail in document["media"].items():
        for mode, run in (("stock", standard), ("cairo", cairo)):
            if detail[f"{mode}_file_sha256"] != run["scientific"]["evidence"]["images"][name]["sha256"]:
                raise ValueError("An official PNG is absent from the independently signed comparison")
    return {mode: run["scientific"] for mode, run in runs.items()}


def measured_reference(root, scored, pin):
    result = checked_json(scored, pin)
    seal = root/"prediction-seal.json"
    if (not result["qualified"] or result["case"] != "DS30-0016"
            or set(result["measured_exits"]) != set(ordinary.ORDER)
            or any(result["measured_exits"][mode]["clock"]["exit_code"] for mode in ordinary.ORDER)
            or result["admission"] != ordinary.read(root/"admission.json")
            or result["pre_score_sha256"] != sha256(seal.read_bytes()).hexdigest()
            or ordinary.read(seal) != ordinary.roster(root)):
        raise ValueError("A qualified freshly measured ordinary pair and its unchanged exit evidence are required")
    return result


def candidate_argv(reference, output):
    from exact_named_raw import parser

    command = list(reference["admission"]["commands"]["candidate"])
    if Path(command[5]).name != "exact_named_raw.py" or OPTION in command:
        raise ValueError("The measured reference must use the ordinary raw candidate")
    command[5] = str(ordinary.HERE/"exact_named_raw.py")
    command[command.index("--output")+1] = str(output)
    ordinary.route_options(command)
    optional = command + [OPTION]
    options = parser().parse_args(optional[6:])
    if not options.cairo_six_sheets:
        raise ValueError("The installed research CLI has not enabled the verified alternative renderer")
    return optional


def renderer_pins(scientific):
    from history_cairo_render import SOURCES

    declared = scientific["source_sha256"]
    sources = {f"reports/ALGO08/v3/{path}": declared[f"reports/ALGO08/v3/{path}"] for path in SOURCES}
    ordinary.bundle_sha(ordinary.HERE.parents[2], sources)
    return sources


def launch_ready(root, stage, signed, ready, reference_root, reference_score, reference_pin):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked
    from exact_named_raw import staged_path
    from guarded_cfo_0016_stage import cache_states, fully_resident
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.operations.tle_archive import TleArchiveReader
    from raw_0016_best_trial import measure_mode
    from tools.pipeline_eval.qualification.paired_publication import archive_identity
    start = perf_counter()
    machine = host()
    staged_path(root.parent)
    staged_path(reference_root)
    verified_scope(stage/ordinary.RECORDING.name, ordinary.RECORDING)
    qualified = measured_reference(reference_root, reference_score, reference_pin)
    req, original, _, saved = ordinary.references()
    original_admission = qualified["admission"]
    custody = ordinary.require_custody(stage, signed)
    if (original_admission["machine"] != machine or original_admission["request"] != req
            or original_admission["custody_sha256"] != custody or original_admission["stage"]["files"] != ready["files"]):
        raise ValueError("The optional child must reuse the same staged input and measured host")
    ordinary.authenticate_sidecars(stage, signed)
    gate = saved_gate(gate_document(GATE), req, saved, PLOTS)
    sources = renderer_pins(gate["cairo"])
    science, adapters = ordinary.frozen_sources(ordinary.HERE.parents[2], original_admission["sources"])
    checked(Path(req["region"]), req["offer_sha256"])
    archive = staged_path(Path(req["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (archive_identity(archive) != req["archive"] or len(refs) != original["archive"]["snapshots"]
            or any(ref.collected_utc_ns >= req["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Causal archive changed from the measured reference")
    observed = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE",
                                                    *(staged_path(ref.path, root=archive) for ref in refs)]))["fincore"]
    if len(observed) != len(refs) or any(row["res"] < row["size"] for row in observed):
        raise ValueError("The same causal snapshots must remain resident")
    for item in original_admission["candidate_libraries"].values():
        checked(Path(item["path"]), item["sha256"])
    command = candidate_argv(qualified, root/"candidate")

    def resident():
        status = ordinary.readiness(stage, signed)
        verified_scope(stage/ordinary.RECORDING.name, ordinary.RECORDING)
        if not status["ready"] or status["files"] != ready["files"]:
            raise ValueError("The original signed raw scope changed")
        cache = cache_states({kind: [(Path(path), n, pin) for path, n, pin in rows]
                              for kind, rows in ordinary.stage_files(signed).items()})
        if not fully_resident(cache):
            raise ValueError("The complete staged waveform must remain resident")
        return cache["payload"] | {"index_cache": cache["index"]}

    resident()
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(Path(req["region"]).parent/"fonts", root/"fonts")
    write(root/"admission.json", dict(request=req, machine=machine, custody_sha256=custody, stage=ready,
         reference=dict(root=str(reference_root), score=str(reference_score), sha256=reference_pin),
         gate_sha256=GATE_PIN, command=command, science=science, adapters=adapters,
         renderer_sources=sources, named_children=0, prepared_wall_s=perf_counter()-start))
    try:
        measure_mode(root, "candidate", command, environment_for(root), resident, require_success=False)
    finally:
        write(root/"prediction-seal.json", ordinary.roster(root))


def launch(root, stage, reference, score, reference_pin):
    signed = ordinary.enrolled()
    ready = ordinary.readiness(stage, signed)
    if not ready["ready"]:
        raise ValueError(f"Stage blocked before any worker: {ready.get('missing_bytes')} signed bytes missing")
    from guarded_stage_checkpoint import staging_lock

    with staging_lock(ordinary.STAGING_LOCK):
        ready = ordinary.readiness(stage, signed)
        if not ready["ready"]:
            raise ValueError("Source extent changed")
        launch_ready(root, stage, signed, ready, reference, score, reference_pin)


def score(root, output):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from publication_media_checks import image_comparison_fields, verify_position_sidecars

    seal_path = root/"prediction-seal.json"
    if ordinary.read(seal_path) != ordinary.roster(root):
        raise ValueError("The optional raw output changed after exit")
    admission = ordinary.read(root/"admission.json")
    reference = admission["reference"]
    previous = measured_reference(Path(reference["root"]), Path(reference["score"]), reference["sha256"])
    req, _, stock, saved = ordinary.references()
    baseline = previous["runs"]["candidate"]
    if admission["gate_sha256"] != GATE_PIN:
        raise ValueError("Saved semantic gate lineage changed")
    expected = saved_gate(gate_document(GATE), req, saved, PLOTS)
    log = ordinary.read(root/"candidate-clock.json")
    if (log["command"] != admission["command"] or admission["command"] != candidate_argv(previous, root/"candidate")
            or admission["request"] != req or admission["renderer_sources"] != renderer_pins(expected["cairo"])
            or (root/"stock").exists() or (root/"stock-clock.json").exists()):
        raise ValueError("The executed optional renderer is outside its signed scope")
    stock_clock = previous["runs"]["stock"]["process"]["clock"]
    if log["clock"]["started_unix_ns"] <= stock_clock["started_unix_ns"] + int(stock_clock["elapsed_s"]*1e9):
        raise ValueError("The optional child must follow the completed fresh ordinary pair")
    ordinary.bundle_sha(ordinary.HERE.parents[2], admission["science"] | admission["adapters"])
    receipt = dict(command=log["command"], optional_process=log, reused_stock=stock_clock,
                   measured_ordinary=baseline["process"]["clock"], admission=admission,
                   named_children=0, pair_sha256=reference["sha256"], seal_sha256=sha256(seal_path.read_bytes()).hexdigest())
    if log["clock"]["exit_code"]:
        write(output, receipt | {"qualified": False, "failure": "candidate_process_exit"})
        return
    result = ordinary.published(root, "candidate", log, req, stock, saved, adapters=admission["adapters"])

    def images(row):
        return canonical_digest(image_comparison_fields(row))

    standard, cairo = (expected[mode]["evidence"]["images"] for mode in ("standard", "cairo"))
    terminal = result["science"]["receipt"]
    checks = dict(native=result["digest"] == baseline["digest"] and result["native_parity"],
                  opportunities=result["opportunities"] == baseline["opportunities"] and result["excluded"] == baseline["excluded"],
                  terminal=result["terminal_parity"] and terminal["terminal_sha256"] == baseline["science"]["receipt"]["terminal_sha256"],
                  cal_arms=result["science"]["arms"] == baseline["science"]["arms"],
                  conditional_and_all_owned_rf=result["all_owned_rf_rms_hz"] == baseline["all_owned_rf_rms_hz"],
                  owner_rows=result["owners"] == baseline["owners"] and result["reference_owner_parity"],
                  numerical_route=result["route_parity"],
                  numeric_sidecars=result["sidecar_science_parity"],
                  ordinary_media=images(baseline["figures"]) == images(standard),
                  actual_renderer=active_renderer(result["route"] or {}),
                  all_eight_cairo_media=images(result["figures"]) == images(cairo))
    sidecars = (verify_position_sidecars(Path(reference["root"])/"candidate", root/"candidate", terminal["run_id"],
                                       baseline["figures"], result["figures"])
                if checks["terminal"] and checks["all_eight_cairo_media"] else None)
    clocks = receipt["reused_stock"], receipt["measured_ordinary"], log["clock"]
    timings = {metric: dict(fresh_stock_to_cairo=clocks[0][metric]/clocks[2][metric],
                            same_pair_ordinary_delta=clocks[1][metric]-clocks[2][metric])
               for metric in ("cpu_s", "elapsed_s")}
    write(output, receipt | dict(qualified=all(checks.values()) and sidecars is not None, checks=checks,
          native=result, bound_sidecars=sidecars, timings=timings, reference_geographical_and_rf=previous["geographical_and_rf"]))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    measure = actions.add_parser("launch")
    measure.add_argument("root", type=Path)
    measure.add_argument("--stage", type=Path, default=ordinary.STAGE)
    for flag in ("reference", "reference-score"):
        measure.add_argument("--"+flag, type=Path, required=True)
    measure.add_argument("--reference-pin", required=True)
    compare = actions.add_parser("score")
    compare.add_argument("root", type=Path)
    compare.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root, args.stage, args.reference, args.reference_score, args.reference_pin)
    elif args.output.resolve().is_relative_to(args.root.resolve()):
        cli.error("Place the score outside its sealed source")
    else:
        score(args.root, args.output)


if __name__ == "__main__":
    main()
