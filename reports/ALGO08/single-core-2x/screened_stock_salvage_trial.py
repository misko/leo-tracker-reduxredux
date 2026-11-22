"""Toggle the existing guarded salvage overlays behind one frozen screened solver."""

import argparse
import gzip
import json
import os
import runpy
import subprocess
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCES = Path("tools/pipeline_eval/variants")
TRIALS = HERE / "measurements"
SCREENED_SPEC = "sha256:6703ec6db43229305ce82b4987d2c0535bce9e2e2266e6173abb397494abbbf4"
PARENT_SPEC = "sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423"
INTEGRATED_SPEC = "sha256:c803a30087a9c23e00aa4fa30e6a2b87a4d682cd941a3f3d870ce9277dbc90d6"
SOURCE_PINS = {
    "algo08_salvage_statistics.py": (
        "017e7c9d400c94d2e5d824e1facd8c96ccad51d8eb24128ec7a0fc8e866c4a3c"
    ),
    "algo08_salvage_bound.py": "77db0c8b857242b9e117805158dc129cf5bb45f8fb902c273bd5121ef8bad213",
    "v5_tiled_salvage.py": "a86e62fed9eb7c286747fcf20e246010b3f06774dc9f79843ea7f8610a0fa7b4",
    "conservative_recovery.py": "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
}
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def science_digest(document):
    from leo.contracts.digests import canonical_digest

    return canonical_digest({key: value for key, value in document.items()
                             if key not in ("binding", "elapsed_seconds")})


def require_spec(folder, expected):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import verify_sources

    specification = read(folder / "spec.json")
    if canonical_digest(specification) != expected:
        raise ValueError("Unexpected screened-stock or covariance source freeze")
    entry = folder / "reports/ALGO08/single-core-2x/run-candidate"
    verify_sources(entry, specification["sources"])


def check_salvage_pins(frozen, parent, release):
    paths = {name: parent / SOURCES / name for name in
             ("algo08_salvage_statistics.py", "algo08_salvage_bound.py")}
    paths["v5_tiled_salvage.py"] = frozen / SOURCES / "v5_tiled_salvage.py"
    paths["conservative_recovery.py"] = (
        release / "src/leo/analysis/localization_v3/conservative_recovery.py"
    )
    if {key: digest(path) for key, path in paths.items()} != SOURCE_PINS:
        raise ValueError("Salvage source pins differ from the reviewed files")


@contextmanager
def trace_salvage(kernel, readout):
    original = kernel.salvage
    totals = Counter()

    def timed(function, role):
        def call(*args, **kwargs):
            label = role(*args, **kwargs)
            totals[label + "_calls"] += 1
            start = process_time_ns()
            try:
                return function(*args, **kwargs)
            finally:
                totals[label + "_cpu_ns"] += process_time_ns() - start
        return call

    def profile_kind(_observed, prediction, *_args, **_kwargs):
        return "fine_profile" if prediction.shape[0] == 121 else "coarse_profile"

    def salvage(scan, node, keep, **options):
        profile = timed(kernel.profile, profile_kind)
        noise = timed(kernel.batch_noise_screen, lambda *_a, **_kw: "noise")
        incoming = readout(scan, node, keep)
        start = process_time_ns()
        with (
            patch.object(kernel, "profile", profile),
            patch.object(kernel, "batch_noise_screen", noise),
        ):
            recovered, retained, diagnostics = original(scan, node, keep, **options)
        totals["salvage_cpu_ns"] += process_time_ns() - start
        totals["salvage_calls"] += 1
        offers.append(dict(diagnostics=diagnostics, incoming=incoming,
                           outgoing=readout(scan, recovered, retained)))
        return recovered, retained, diagnostics

    offers = []
    with patch.object(kernel, "salvage", salvage):
        yield totals, offers


def worker(site, frozen, output, parent=None, offer_name="matched-tile"):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    if not Path(publication.__file__).is_relative_to(frozen):
        raise ValueError("Expected the frozen screened publication entry point")
    specification = read(frozen / "spec.json")
    trace = runpy.run_path(str(HERE / "portable_south_solver_trace.py"))
    report = runpy.run_path(str(HERE / "screened_stock_recovery_trial.py"))["readout"]
    native = read(site / "native.json")
    offer_path = site / (offer_name + ".json")
    diagnostics = {}

    def from_saved(recording, _root, assets, archive, offer):
        from leo.analysis.localization_v3 import conservative_recovery
        from leo.application.localization_v3_engine import _json_value
        from leo.contracts.algo08_region import Algo08Region
        from leo.contracts.digests import canonical_digest
        from leo.operations.tle_archive import TleArchiveReader
        from tools import algo08_position
        from tools.pipeline_eval.variants import v5_tiled_salvage

        if recording.name != "no-recording" or archive != site / "tle" or diagnostics:
            raise ValueError("Expected one saved detector callback")
        if offer != Algo08Region.parse(read(offer_path)):
            raise ValueError("Launcher supplied a different search or screening offer")
        for module in (v5_tiled_salvage, conservative_recovery):
            name = Path(module.__file__).name
            if digest(module.__file__) != SOURCE_PINS[name]:
                raise ValueError(f"Runtime uses an unexpected salvage source for {name}")
        notes = {}
        with ExitStack() as observer:
            coarse, shortlist, gate = None, None, None
            if parent is not None:
                for name in ("algo08_salvage_statistics.py", "algo08_salvage_bound.py"):
                    if digest(parent / SOURCES / name) != SOURCE_PINS[name]:
                        raise ValueError("Optional salvage source changed before loading")
                source = parent / SOURCES
                coarse_module = runpy.run_path(str(source / "algo08_salvage_statistics.py"))
                gate_module = runpy.run_path(str(source / "algo08_salvage_bound.py"))
                coarse, shortlist = observer.enter_context(coarse_module["salvage_statistics"]())
                gate = observer.enter_context(gate_module["stable_pruning"]("gate"))
            timings, offers = observer.enter_context(
                trace_salvage(conservative_recovery, trace["identity"])
            )
            observer.enter_context(trace["traced"](notes, False))
            start_cpu, start_wall = process_time_ns(), perf_counter()
            decision, packet, policy = algo08_position.solve(
                native, TleArchiveReader(archive), assets, offer
            )
            solver_cpu = (process_time_ns() - start_cpu) / 1e9
            solver_wall = perf_counter() - start_wall
        if packet is None:
            raise ValueError(f"No packet on the known containing offer: {decision['status']}")
        evidence = {key: science_digest(packet[key])
                    for key in ("position_grid", "position_path", "objective_replay")}
        diagnostics.update(solver_offer=offer.document(), salvage_timing=timings,
                           coarse=coarse, shortlist=shortlist, gate=gate,
                           offers=offers, stage_evidence=report(notes), science=evidence,
                           published_rows=canonical_digest(notes["published_points"]),
                           grid_points=packet["position_grid"]["evaluated_points"],
                           regional_bound_guard=decision["metrics"].get("regional_bound_guard"),
                           stage_wall_s=decision["metrics"]["stage_s"],
                           solver_cpu_s=solver_cpu, solver_wall_s=solver_wall)
        # Convert saved numerical values after the complete solver clock.
        serial = json.loads(json.dumps(diagnostics, default=_json_value, allow_nan=False))
        diagnostics.update(serial)
        return dict(status=decision["status"], reason=decision.get("reason"),
                    arms=decision["arms"], orbit_policy=policy,
                    owners={arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS},
                    associated={arm: packet["arms"][arm]["associated_points"] for arm in ARMS})

    ordinary_install = lean_startup.install
    with TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)

        def install_then_adapt():
            ordinary_install()
            from tools import algo08_scan

            stack.enter_context(patch.object(algo08_scan, "analyze", from_saved))

        stack.enter_context(patch.object(lean_startup, "install", install_then_adapt))
        args = SimpleNamespace(recording=root / "no-recording", bulk_root=root,
                               archive=site / "tle", region=offer_path)
        result = publication.run(args, specification)
    with output.open("x") as stream:
        json.dump(dict(result=result, **diagnostics), stream, indent=2, allow_nan=False)


def recorded_stock_offers(calls):
    offers = []
    for call in calls:
        selected = {row["component"]: row for row in call["selected"]}
        rejected = {row["component"] for row in call["incoming"] if row["points"] == 0}
        if not selected.keys() <= rejected:
            raise ValueError("Archived salvage selected a fragment already active")
        diagnostics = [selected.get(name, dict(component=name, alternatives=[], selected=None))
                       for name in sorted(rejected)]
        offers.append(dict(
            diagnostics=diagnostics, incoming=call["incoming"], outgoing=call["curved"]
        ))
    return offers


def offered_trims(calls):
    fields = ("start_index", "stop_index", "points", "norad", "candidate_index", "alias", "phase_s")

    def trim(row):
        return {key: row[key] for key in fields} if row is not None else None

    return [[dict(component=row["component"], alternatives=list(map(trim, row["alternatives"])),
                  selected=trim(row["selected"])) for row in call["diagnostics"]]
            for call in sorted_calls(calls)]


def sorted_calls(calls):
    return [dict(call, diagnostics=sorted(call["diagnostics"], key=lambda row: row["component"]))
            for call in calls]


def selected_diagnostics(calls):
    return [[row for row in call["diagnostics"] if row["selected"] is not None]
            for call in sorted_calls(calls)]


def compare(guarded, archived, deployed):
    controls = {}
    result = guarded["result"]
    previous = archived["screened_stock_recovery"]
    for name in ("installed", "screened_stock_recovery"):
        reference = archived[name]
        expected = {arm: {key: reference["arms"][arm][key] for key in ("latlon", "rf_rms_hz")}
                    for arm in ARMS}
        controls[name] = (result["arms"] == expected and all(result[key] == reference[key]
                          for key in ("status", "reason", "owners", "associated", "orbit_policy")))
    baseline = recorded_stock_offers(deployed["salvage"]) if deployed is not None else []
    actual = guarded["offers"]
    objective_match = None
    if deployed is not None:
        objective = science_digest(deployed["objective_replay"])
        objective_match = objective == guarded["science"]["objective_replay"]
    return dict(
        prior_results=controls,
        prior_stages={key: value == guarded["stage_evidence"][key]
                      for key, value in previous["stage_evidence"].items()},
        deployed_objective_replay=objective_match,
        offered_trims=offered_trims(baseline) == offered_trims(actual),
        full_selected_diagnostics=selected_diagnostics(baseline) == selected_diagnostics(actual),
        incoming_ids=[x["incoming"] for x in baseline] == [x["incoming"] for x in actual],
        retained_ids=[x["outgoing"] for x in baseline] == [x["outgoing"] for x in actual],
    )


def run_bound_worker(transfer, site, row, frozen, path, parent=None):
    from tools.pipeline_eval.__main__ import THREAD_ENV
    from tools.pipeline_eval.scoring import distance_km

    verify_archive = runpy.run_path(str(HERE / "complete_family_cavity_trial.py"))["verify_archive"]
    if (digest(site / "native.json") != row["document_sha256"]
            or read(site / (row["mode"] + ".json")) != row["offer"]):
        raise ValueError("The detector or offer differs from its released input")
    verify_archive(transfer, row, site)
    release = transfer["RELEASE"]
    env = dict(os.environ, PYTHONPATH=f"{frozen}:{release / 'src'}:{release}", **THREAD_ENV)
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    command = [str(release / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker",
               *map(str, (site, frozen, path)), "--offer-name", row["mode"]]
    if parent is not None:
        command.extend(("--parent", str(parent)))
    subprocess.run(command, env=env, timeout=125, check=True)
    observed = read(path)
    if observed["solver_offer"] != row["offer"]:
        raise ValueError("Solver offer differs from the released development offer")
    verify_archive(transfer, row, site)
    observed["horizontal_error_km"] = {
        arm: distance_km(value["latlon"], row["reference_latlon"])
        for arm, value in observed["result"]["arms"].items()
    }
    return observed


def run(scratch, frozen, parent, output):
    transfer = runpy.run_path(str(HERE / "covariance_transfer_trial.py"))
    require_spec(frozen, SCREENED_SPEC)
    require_spec(parent, PARENT_SPEC)
    check_salvage_pins(frozen, parent, transfer["RELEASE"])
    comparison = TRIALS / "screened-stock-recovery-containing.json"
    rows = {row["case"]: row for row in read(comparison)["rows"]}
    deployed_path = TRIALS / "portable-south-solver-attribution.json.gz"
    trace = json.loads(gzip.decompress(deployed_path.read_bytes()))
    southern = rows[transfer["SOUTH"]]
    bind = ("case", "document_sha256", "history_sha256", "offer")
    if any(trace["plan"][key] != southern[key] for key in bind):
        raise ValueError("Deployed salvage trace uses a different input or offer")
    deployed = trace["results"]["installed"]["stages"]
    summary = {}
    output.mkdir(parents=True, exist_ok=False)
    for site_name, case, reference in (("southern-portable", transfer["SOUTH"], deployed),
                                       ("India", transfer["INDIA"], None)):
        site, row = scratch / case, rows[case]
        path = output / f"{site_name}-guarded.json"
        observed = run_bound_worker(transfer, site, row, frozen, path, parent)
        checks = compare(observed, row["builds"], reference)
        summary[site_name] = dict(plan={k: v for k, v in row.items() if k != "builds"},
                                  checks=checks, guarded=observed,
                                  prior={name: {key: row["builds"][name][key] for key in
                                                ("solver_cpu_s", "arms", "associated", "owners")}
                                         for name in ("installed", "screened_stock_recovery")})
    with (output / "summary.json").open("x") as stream:
        json.dump(dict(screened_specification=SCREENED_SPEC, covariance_parent=PARENT_SPEC,
                       source_pins=SOURCE_PINS, comparison_sha256=digest(comparison),
                       deployed_trace_sha256=digest(deployed_path), sites=summary),
                  stream, indent=2, sort_keys=True, allow_nan=False)


def integrated_omission(scratch, frozen, output):
    transfer = runpy.run_path(str(HERE / "covariance_transfer_trial.py"))
    require_spec(frozen, INTEGRATED_SPEC)
    check_salvage_pins(frozen, frozen, transfer["RELEASE"])
    comparison = TRIALS / "screened-stock-recovery-omitted.json"
    case = transfer["INDIA"]
    row, = [r for r in read(comparison)["rows"]
            if r["case"] == case and r["mode"] == "omitted-tile"]
    output.mkdir(parents=True, exist_ok=False)
    worker_receipt = output / "India-omitted.json"
    observed = run_bound_worker(transfer, scratch / case, row, frozen, worker_receipt)
    prior = row["builds"]["screened_stock_recovery"]
    checks = compare(observed, row["builds"], None)
    checks["regional_bound_guard"] = (
        observed["regional_bound_guard"] == prior["regional_bound_guard"]
    )
    result = dict(integrated_specification=INTEGRATED_SPEC, comparison_sha256=digest(comparison),
                  plan={k: v for k, v in row.items() if k != "builds"},
                  checks=checks, observed=observed)
    with (output / "summary.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    trial, child = actions.add_parser("run"), actions.add_parser("worker")
    omitted = actions.add_parser("integrated-omission")
    for name in ("scratch", "frozen", "parent", "output"):
        trial.add_argument(name, type=Path)
    for name in ("site", "frozen", "output"):
        child.add_argument(name, type=Path)
    child.add_argument("--parent", type=Path)
    child.add_argument("--offer-name", choices=("matched-tile", "omitted-tile"), required=True)
    for name in ("scratch", "frozen", "output"):
        omitted.add_argument(name, type=Path)
    options = vars(cli.parse_args())
    {"run": run, "worker": worker, "integrated-omission": integrated_omission}[
        options.pop("action")
    ](**options)
