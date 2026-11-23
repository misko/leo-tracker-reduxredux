"""Compare the named and causal hybrid solutions on the frozen saved full packet."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from causal_pre_refit_0155 import ARMS, ENROLLED, binding as enrolled_binding, compare_grid, request
from empty_bootstrap import RELEASE, checked


CASE = "DS30-0155"
ORDER = ("stock", "hybrid")
PINS = ENROLLED[CASE]


def worker(mode, output):
    from named_weak_exact import run as publish

    req = enrolled_binding(CASE)
    trace, selection = {}, {}

    @contextmanager
    def scope():
        from leo.storage.fast_scan import FastScanStore, FastSegmentSource
        from leo.storage.short_window import ShortWindowReader
        from named_constrained_research import deny_waveform, inventory_binding
        from pre_signed_hybrid import binding
        from tools import algo08_position

        build = algo08_position.selected_packet

        def record(prepared, signed, fit):
            packet = build(prepared, signed, fit)
            selection.update(
                owners={arm: [[v["observation_id"], v["norad"], v["role"]] for v in packet["rows"][arm]]
                        for arm in ARMS},
                signed_adopted=bool(signed["signed"]["accepted"]),
                orbits_reassigned=bool(fit is not None and fit["accepted"]),
            )
            return packet

        metadata = inventory_binding(args.recording, Path(req["staged_inventory"]), req["session"], req["inventory"])
        with (patch.object(FastScanStore, "inventory", metadata),
              patch.object(FastSegmentSource, "windows", deny_waveform),
              patch.object(ShortWindowReader, "windows", deny_waveform),
              patch.object(algo08_position, "selected_packet", record),
              binding(mode == "hybrid", trace)):
            yield

    args = SimpleNamespace(recording=Path(req["recording"]), archive=Path(req["local_archive"]["root"]),
                           region=Path(req["offer_file"]), bulk_root=output)
    output.mkdir()
    publish(args, optimized=False, saved=Path(req["native_file"]), expected="sha256:"+PINS["native_sha"],
            analysis_scope=scope)
    from aperture_trial import write

    write(output / "pre-signed-hybrid.json", dict(mode=mode, trace=trace, selection=selection, waveforms_opened=0))


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh private tmpfs outputs")
    req = request(CASE)
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    names = ("pre-signed-hybrid-protocol.md", "pre_signed_hybrid.py", "pre_signed_hybrid_trial.py",
             "named_weak_exact.py", "lighter_joint_estimator.py", "causal_linear_refit.py")
    write(root / "binding.json", dict(
        case=CASE, order=ORDER, machine=machine, request=req,
        implementation={name: sha256((HERE / name).read_bytes()).hexdigest() for name in names},
    ))
    for mode in ORDER:
        out = root / mode
        command = [python, "-IB", __file__, "worker", mode, out]
        clocks = measure(command, env, out)
        write(root / f"{mode}-clock.json", dict(command=list(map(str, command)), timing=clocks))
        if clocks["exit_code"]:
            raise RuntimeError(f"{mode} exited nonzero and its original clock is sealed")


def audit_run(root, mode, req):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    out = root / mode
    process = read(root / f"{mode}-clock.json")
    named = read(out / "named-weak-exact.json")
    audit = read(out / "pre-signed-hybrid.json")
    receipt = named["publication"]
    run_id = receipt["run_id"]
    file_store = FastScanStore(out)
    workspace = file_store.automatic_workspace(run_id, create=False)
    terminal = read(workspace / "terminal.json")
    native, = workspace.parent.glob("*/detections.json")
    checked(native, PINS["native_sha"])
    captured = evidence(out, receipt, process["timing"]["started_unix_ns"], read_only=True)
    media = json.loads(json.dumps(artifacts(out, receipt)))
    if (process["timing"]["exit_code"] or audit["waveforms_opened"] or named["acquisition"]["mode"] != "saved"
            or receipt["session_id"] != req["session"] or captured["raw_authority"] != req["raw_authority"]
            or receipt["counts"]["processed"] != PINS["admitted"] or receipt["window_count"] != PINS["windows"]
            or terminal["native_sha256"] != "sha256:"+PINS["native_sha"] or named["optimized"]):
        raise ValueError(f"{mode} changed the original detector, region or input provenance")
    store = FastStandardAnalysisStore(out)
    if receipt["decision"] == "complete":
        grid, path = store.position_grid(run_id), store.position_path(run_id)
        if (not grid["complete"] or grid["evaluated_points"] != 179 or len(media["images"]) != 8
                or any(doc["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"]
                       for doc in (grid, path))):
            raise ValueError(f"{mode} did not publish the full bound scientific evidence")
    else:
        grid, path = None, None
        if media["images"] or not terminal["reason"]:
            raise ValueError("An actual withdrawal must provide its reason and publish zero plots")
    return dict(process=process, named=named, audit=audit, terminal=terminal, media=media,
                science={key: captured[key] for key in ("arms", "owners", "scientific_digests", "raw_authority")},
                grid=grid, path=path)


def score(root, destination):
    from aperture_trial import read, write
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    bind = read(root / "binding.json")
    runs = {name: audit_run(root, name, bind["request"]) for name in ORDER}
    history = json.loads(checked(PINS["prior"], PINS["prior_sha"]))["runs"]["stock"]
    base, hybrid = (runs[name] for name in ORDER)
    if (base["terminal"] != history["terminal"]
            or base["audit"]["selection"]["owners"] != history["selected_rows"]
            or base["science"]["scientific_digests"] != history["science"]["scientific_digests"]
            or base["media"]["images"] != history["figures"]):
        raise ValueError("Fresh control differed from sealed named science")
    truth, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
              if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    reference = [truth[key] for key in ("latitude_deg", "longitude_deg")]
    matched_region = base["terminal"]["region"] == hybrid["terminal"]["region"]
    if not matched_region:
        raise ValueError("The two jobs used different offers")
    locations = {name: {arm: run["terminal"]["arms"][arm]["latlon"] for arm in ARMS} for name, run in runs.items()}
    scores = {name: {arm: distance_km(reference, coordinates) if coordinates is not None else None
                     for arm, coordinates in arms.items()} for name, arms in locations.items()}
    shifts = {arm: distance_km(locations["stock"][arm], locations["hybrid"][arm])
              if all(run[arm] is not None for run in locations.values()) else None for arm in ARMS}
    owners = {arm: owner_delta(base["audit"]["selection"].get("owners", {}).get(arm, []),
                              hybrid["audit"]["selection"].get("owners", {}).get(arm, [])) for arm in ARMS}
    grid = compare_grid(base["grid"], hybrid["grid"]) if hybrid["grid"] is not None else None
    activation = any(row["route"] == "fixed_named_roster" for row in hybrid["audit"]["trace"]["signed"])
    tolerance = all(row["identical_ordered_rows"] for row in owners.values()) and all(
        point is not None and point <= .020 for point in shifts.values())
    for run in runs.values():
        # Full selected rows, grid and path remain in the authenticated run roots.
        run["audit"]["selection"].pop("owners", None)
        for key in ("grid", "path"):
            run.pop(key)
    write(destination, dict(binding=bind, runs=runs, ownership=owners, grid=grid, reference_sha256=REFERENCE_SHA256,
                            horizontal_error_km=scores, displacement_km=shifts, activated=activation,
                            same_terminal=base["terminal"] == hybrid["terminal"],
                            same_media=base["media"]["images"] == hybrid["media"]["images"],
                            activated_transfer_pass=tolerance if activation else None))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("launch").add_argument("root", type=Path)
    run = commands.add_parser("worker")
    run.add_argument("mode", choices=ORDER)
    run.add_argument("output", type=Path)
    verify = commands.add_parser("score")
    verify.add_argument("root", type=Path)
    verify.add_argument("receipt", type=Path)
    options = parser.parse_args()
    if options.action == "launch":
        launch(options.root)
    elif options.action == "worker":
        worker(options.mode, options.output)
    else:
        score(options.root, options.receipt)
