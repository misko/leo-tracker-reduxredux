"""One fresh attribution worker through the actual six-Cairo positive publisher."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
ORIGINAL = Path("/dev/shm/leo-v3-combined-successor-cairo-01/DS30-0016")
RESULT = "b47d6753614a20feb577bb2246eabf21a94b027a46d8a928cb014874aa1960d7"
ADMISSION = "8be3319606fde59d497a445c15c4bba79a93e48cb492d314ff5e3e985db0a7f5"
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def deny_waveform(event, arguments):
    if event != "open" or not isinstance(arguments[0], (str, bytes)):
        return
    path = Path(os.path.abspath(os.fsdecode(arguments[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith(".ci16.zst"):
        raise ValueError("The source audit cannot open physical backing inputs")


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def audit(output):
    from verified_source_audit import RAW_SHA, SourceAudit, now, summarize

    if output.exists() or output.parent.resolve(strict=True) not in (Path("/dev/shm"), Path("/tmp")):
        raise ValueError("Use a fresh local tmpfs result")
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"
            or any(os.getenv(which) != "1" for which in THREADS)):
        raise ValueError("Expected the same one-core Gauss environment")
    sys.addaudithook(deny_waveform)
    trace = SourceAudit(ROOT)
    output.mkdir(mode=0o700)
    beginning = now()
    result = {"checks": {}, "scopes": {}}

    def paid(stage, start):
        cpu, wall = now()
        result["scopes"][stage] = dict(cpu_ns=cpu - start[0], wall_ns=wall - start[1])

    try:
        with trace.bind():
            started = now()
            import empty_bootstrap as boot
            from combined_successor_raw_entry import solver_ports
            from legacy_first_map_entry import parser

            expected = json.loads(boot.checked(ORIGINAL/"result.json", RESULT))
            admission = json.loads(boot.checked(ORIGINAL/"admission.json", ADMISSION))
            args = parser().parse_args(admission["command"][6:])
            args.output = output/"candidate"
            if (not expected["qualified"] or not args.cairo_six_sheets or not args.history_risk_route
                    or not args.verify_original_once or args.region.parent != args.archive.parent):
                raise ValueError("Expected the exact enrolled current six-sheet positive")
            paid("admit_saved_reference", started)

            trace.phase = "installed_startup"
            started = now()
            _, spec, sources, publication, checks = boot.load_runtime()
            boot.staged_scanner(sources)
            paid("installed_startup_and_scanner_source", started)
            result["release_source_admission"] = checks

            trace.phase = "saved_handoff"
            started = now()
            from cumulative_grid_projection import saved_inventory_port
            import exact_named_raw as raw
            import history_cairo_render
            from legacy_first_map_acceleration import checked_artifacts
            from leo.contracts.algo08_region import Algo08Region
            from leo.contracts.digests import canonical_digest
            from leo.storage.fast_scan import FastSegmentSource
            from named_constrained_research import deny_waveform as no_windows
            from unified_short_bootstrap import Handoff

            original = ORIGINAL/"candidate"
            original_receipt = expected["science"]["receipt"]
            session = original_receipt["session_id"]
            original_inventory = original/"fast-scan-inputs"/f"{session}.json"
            # This immutable saved-byte handoff substitutes only the detector.
            # All original signed evidence is still checked.
            packet, = (original/"fast-scan-automatic-work").glob("*/detections.json")
            native = json.loads(boot.checked(packet,
                                            expected["science"]["native_sha256"].removeprefix("sha256:")))
            inventory = native["source"]["input_manifest_sha256"]
            if (canonical_digest(json.loads(original_inventory.read_bytes())) != inventory
                    or args.archive_sha256 != expected["witness"]["solver_recipe"]["archive_sha256"]):
                raise ValueError("The original verified inventory changed")
            receiver = native["provenance"]["detector_sha256"].removeprefix("sha256:")
            boot.bind_native(native, session, inventory, receiver, expected=expected["science"]["native_sha256"])
            offer = Algo08Region.parse(json.loads(args.region.read_bytes())).document()
            if offer != original_receipt["region"] or native["source"]["raw_recording_authority_digest"] != expected["science"]["published"]["raw_authority"]:
                raise ValueError("The original operator offer or recording authority changed")
            libraries = checked_artifacts(args.legacy_first_map_fast, args.legacy_first_map_fast_sha256)
            renderer = history_cairo_render.binding

            @contextmanager
            def title_bound(scan, report, *, orbit_sheets):
                with renderer(scan, report, orbit_sheets=orbit_sheets):
                    render = scan.render

                    def check(packet, **options):
                        if options.get("title") != args.recording.name:
                            raise ValueError("The published title differs from the verified original")
                        answer = render(packet, **options)
                        report["original_recording_title"] = options["title"]
                        return answer

                    with patch.object(scan, "render", check):
                        yield

            solver_audit = {}
            handoff = Handoff(session, inventory, receiver, native)
            request = dict(recording=str(args.recording), saved_inventory=str(original_inventory),
                           session=session, inventory=inventory, receiver="native-20-8-held-history")
            paid("saved_handoff", started)

            trace.phase = "positive_publication"
            started = now()
            with (solver_ports(libraries, solver_audit), saved_inventory_port(request),
                  patch.object(FastSegmentSource, "windows", no_windows),
                  patch.object(history_cairo_render, "binding", title_bound)):
                terminal, detail = raw.publish_active(args, publication, spec, handoff)
            paid("actual_positive_publication", started)
            result["numerics_and_render"] = detail["timing"]
        source = expected["witness"]["evidence"]
        candidate = json.loads((args.output/"exact-named-raw-witness.json").read_bytes())["evidence"]
        checks = {key: candidate[key] == source[key] for key in ("grid", "images", "sidecars", "owner_rows", "owner_maps")}
        checks.update(
            complete=terminal["decision"] == "complete", one_saved_handoff=handoff.calls == 1,
            terminal=terminal["terminal_sha256"] == original_receipt["terminal_sha256"],
            arms=candidate["detail"]["arms"] == source["detail"]["arms"],
            cairo=all(detail["ports"]["cairo_layout"].get(k) == value for k, value in (
                ("native_orbit_figures", 4), ("native_residual_figures", 2), ("position_figures", 1), ("track_figures", 1))),
            mesh=solver_audit["grid"]["complete"] and solver_audit["grid"]["points"] == 179,
        )
        result.update(checks=checks, qualified=all(checks.values()), original_result=RESULT, original_admission=ADMISSION,
                      science={"native_sha256": expected["science"]["native_sha256"], "terminal_sha256": terminal["terminal_sha256"],
                               "decision": terminal["decision"], "owner_rows": {arm: len(rows) for arm, rows in candidate["owner_rows"].items()}},
                      raw_reference_clocks=expected["process"], ports={"grid": solver_audit["grid"], "cairo": detail["ports"]["cairo_layout"]})
        if not result["qualified"]:
            raise ValueError(f"The traced publisher differs from the exact reference: {checks}")
    except Exception as error:
        result["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        paid("before_trace_seal", beginning)
        use = resource.getrusage(resource.RUSAGE_SELF)
        result["kernel"] = dict(input_blocks=use.ru_inblock, major_faults=use.ru_majflt, max_rss_kib=use.ru_maxrss)
        result["sources"] = {name: RAW_SHA((HERE/name).read_bytes()).hexdigest() for name in (
            Path(__file__).name, "verified_source_audit.py", "verified-source-audit-protocol.md")}
        save(output/"source-audit.json", result | summarize(trace.events) | {"events": trace.events})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    audit(cli.parse_args().output)
