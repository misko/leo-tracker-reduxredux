"""Keep the named v3 scanner and solver with scoped exact preparation and rendering."""

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __package__:
    from .empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE, bind_native, checked, clock, now
else:
    sys.path.insert(0, str(HERE))
    from empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE, bind_native, checked, clock, now


PRIOR = Path("/dev/shm/leo-v3-combined-frontier-weak-01")
PRIOR_BINDING_PIN = "afeb71af78edb21f3460d64712fc710eff22bcb257bdba3bfd7135b26bd3510d"
REFERENCE_PIN = "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"
REFERENCE = HERE / "measurements/weak-combined-raw.json"
MODES = ("control", "candidate")


def acquire_once(original, digest, audit, *, saved=None, expected=None):
    def acquire(session, inventory_digest, inventory, assets):
        if audit:
            raise ValueError("Expected one fresh named-v3 acquisition")
        started = now()
        if saved is None:
            native = original(session, inventory_digest, inventory, assets)
        else:
            native = json.loads(checked(saved, expected.removeprefix("sha256:")))
            bind_native(native, session, inventory_digest, digest, expected=expected)
        audit.update(mode="original" if saved is None else "saved", **clock(started))
        return native

    return acquire


def run(args, *, optimized, saved=None, expected=None):
    if (saved is None) != (expected is None):
        raise ValueError("Provide both the saved detector file and its sealed digest")
    started = now()
    checked(BASELINE, BASELINE_PIN)
    launcher = runpy.run_path(str(BASELINE))
    spec = launcher["checked_spec"](PAYLOAD)
    imports = [str(PAYLOAD), str(RELEASE / "src"), str(RELEASE)]
    sys.path[:0] = imports
    os.environ["PYTHONPATH"] = os.pathsep.join(imports)
    for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        os.environ[name] = "1"
    from tools.pipeline_eval.qualification import experimental_publication
    from tools.pipeline_eval.variants.experimental.lean_startup import install

    if Path(experimental_publication.__file__).resolve() != PAYLOAD / "tools/pipeline_eval/qualification/experimental_publication.py":
        raise ValueError("Expected the pinned named-v3 publication entry point")
    if spec["startup"] != "lazy-exports":
        raise ValueError("Expected the named-v3 startup configuration")
    install()
    from tools import algo08_scan

    if Path(algo08_scan.__file__).resolve() != PAYLOAD / "tools/algo08_scan.py":
        raise ValueError("Expected the pinned named-v3 scanner")
    startup = clock(started)
    analyze = algo08_scan.analyze
    acquisition, numerical, rendering = {}, {}, {}
    graph, forecast = {}, {"executions": []}

    def scoped(*values, **options):
        from exact_graph_execution import graph_execution

        solve, render = algo08_scan.solve, algo08_scan.render

        def solve_scoped(*values, **options):
            timer = now()
            date_scope = nullcontext()
            if optimized:
                from exact_phase_forecast import active_forecast

                date_scope = active_forecast(forecast)
            with graph_execution(enabled=optimized, audit=graph), date_scope:
                result = solve(*values, **options)
            numerical.update(clock(timer))
            return result

        def render_timed(*values, **options):
            timer = now()
            images = render(*values, **options)
            rendering["render"] = clock(timer)
            return images

        layout = patch.object(algo08_scan, "render", render_timed)
        if optimized:
            from unified_short_bootstrap import layout_renderer

            layout = layout_renderer(algo08_scan, True, rendering, direct_residuals=True, direct_orbits=True)
        acquisition_op = acquire_once(algo08_scan.acquire, spec["detector_sha256"], acquisition,
                                      saved=saved, expected=expected)
        with patch.object(algo08_scan, "acquire", acquisition_op), patch.object(algo08_scan, "solve", solve_scoped), layout:
            return analyze(*values, **options)

    with patch.object(algo08_scan, "analyze", scoped):
        # The named startup finder is already in place for the scanner import.
        result = experimental_publication.run(args, dict(spec, startup="stock"))
    if not acquisition or not numerical:
        raise ValueError("Expected a fresh acquisition and solve")
    receipt = dict(publication=result, optimized=optimized, frozen_specification=launcher["FINGERPRINT"],
                   detector_sha256=spec["detector_sha256"], startup=startup, acquisition=acquisition,
                   numerical=numerical, rendering=rendering, graph=graph, forecast=forecast)
    with (args.bulk_root / "named-weak-exact.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, allow_nan=False))


def compare(output):
    from aperture_trial import archive_identity, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import measure
    import subprocess

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", output.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use private tmpfs outputs")
    binding = json.loads(checked(PRIOR / "binding.json", PRIOR_BINDING_PIN))
    enrolled = json.loads(checked(REFERENCE, REFERENCE_PIN))
    named = enrolled["runs"]["stock"]
    request = binding["request"]
    if (any(enrolled["binding"][key] != binding[key] for key in ("request", "inventory"))
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("Original causal archive or saved enrollment changed")
    checked(Path(request["region_file"]), request["offer_sha256"])
    packet = native_packet(PRIOR / "stock")
    checked(packet, named["native_sha256"].removeprefix("sha256:"))
    output.mkdir()
    temporary = output / "tmp"
    temporary.mkdir()
    env, python = environment(output), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(temporary)
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    for mode in MODES:
        target = output / mode
        command = [python, "-IB", __file__, "run", "--recording", request["recording"],
                   "--archive", request["archive"]["root"], "--region", request["region_file"],
                   "--bulk-root", target, "--saved", packet, "--saved-digest", named["native_sha256"]]
        if mode == "candidate":
            command.append("--optimized")
        target.mkdir()
        timing = measure(command, env, target)
        write(output / f"{mode}-clock.json", dict(command=list(map(str, command)), clock=timing))
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])
    verify(output, machine, binding, named)


def verify(output, machine, binding, named):
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    results = {}
    for mode in MODES:
        target = output / mode
        trace = read(target / "named-weak-exact.json")
        publication = trace["publication"]
        timing = read(output / f"{mode}-clock.json")
        science = pairs.evidence(target, publication, timing["clock"]["started_unix_ns"], read_only=True)
        pictures = json.loads(json.dumps(artifacts(target, publication)["images"]))
        run_id = publication["run_id"]
        store = FastStandardAnalysisStore(target)
        path, grid = store.position_path(run_id), store.position_grid(run_id)
        work = trace["rendering"].get("work", {})
        request = binding["request"]
        if (timing["clock"]["exit_code"] or trace["acquisition"]["mode"] != "saved" or len(pictures) != 8
                or publication["session_id"] != request["session"] or science["raw_authority"] != request["raw_authority"]
                or publication["region"] != request["offered_region"] or publication["decision"] != "complete"
                or publication["terminal_sha256"] != named["terminal_sha256"] or publication["counts"] != named["counts"]
                or any(science[key] != named[key] for key in ("arms", "owners", "scientific_digests"))
                or not grid["complete"] or grid["evaluated_points"] != named["grid_points"]
                or any(doc["binding"]["position_png_sha256"] != pictures["position"]["sha256"] for doc in (grid, path))):
            raise ValueError(f"{mode} changed named science or standard publication")
        checked(native_packet(target), named["native_sha256"].removeprefix("sha256:"))
        if mode == "control" and (trace["graph"]["enabled"] or pictures != named["images"]):
            raise ValueError("Saved control did not reproduce the named renderer")
        if mode == "candidate" and (
                not trace["graph"]["enabled"] or not trace["graph"]["graph"].get("calls")
                or trace["graph"]["graph"].get("edge_fallbacks")
                or not trace["forecast"]["executions"] or not all(e["used"] for e in trace["forecast"]["executions"])
                or work.get("native_residual_figures") != 2 or work.get("native_orbit_figures") != 4
                or any("fallback" in key for key in work)):
            raise ValueError(f"The expected optimized routes were bypassed: {trace!r}")
        results[mode] = dict(process=timing, trace=trace, arms=science["arms"], owners=science["owners"],
                             grid_points=grid["evaluated_points"], science=science["scientific_digests"],
                             images=pictures)
    raw = named["process"]
    saved_s = results["candidate"]["process"]["clock"]["elapsed_s"]
    control_s = results["control"]["process"]["clock"]["elapsed_s"]
    write(output / "result.json", dict(case="DS30-0016", machine=machine, order=MODES, saved_native=named["native_sha256"],
          binding_sha256=PRIOR_BINDING_PIN, reference_sha256=REFERENCE_PIN, named_raw_clock=raw,
          saved_process_gain_s=control_s-saved_s, target_raw_elapsed_s=raw["elapsed_s"]/2,
          additional_time_at_target_s=raw["elapsed_s"]/2-saved_s, runs=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("compare").add_argument("output", type=Path)
    worker = commands.add_parser("run")
    for name in ("recording", "archive", "region", "bulk-root"):
        worker.add_argument("--"+name, type=Path, required=True)
    worker.add_argument("--saved", type=Path)
    worker.add_argument("--saved-digest")
    worker.add_argument("--optimized", action="store_true")
    args = parser.parse_args()
    if args.command == "compare":
        compare(args.output)
    else:
        launch = SimpleNamespace(recording=args.recording, archive=args.archive, region=args.region, bulk_root=args.bulk_root)
        run(launch, optimized=args.optimized, saved=args.saved, expected=args.saved_digest)


if __name__ == "__main__":
    main()
