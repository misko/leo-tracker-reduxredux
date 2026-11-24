"""Publish a raw 20/8 ms acquisition through the exact named ALGO08v3 route."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
MODIFIED_PORTS = "20/8 ms all visits, held history; original named solve and layout with exact reuse"
ARM_NAMES = ("c0", "fitted_c")
RISK_SOURCES = ("history_risk_route.py", "early_causal_history.py", "prepared_exterior.py",
                "cold_finalist_race.py", "certified_salvage.py", "isolated_salvage.py",
                "named_survivor_fit.py", "blind_joint_route.py", "blind_joint_finish.py",
                "blind_joint_repair.py", "blind_joint_signed.py", "lighter_joint_estimator.py")


def staged_path(path, *, root=None):
    """Require direct paths on the same tmpfs device as their enrolled root."""
    if path.resolve(strict=True) != path:
        raise ValueError(f"Expected a direct staged path: {path}")
    if root is None:
        filesystem = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", path], text=True)
        if filesystem.strip() != "tmpfs":
            raise ValueError(f"Expected an already staged tmpfs input: {path}")
    elif not path.is_relative_to(root) or path.stat().st_dev != root.stat().st_dev:
        raise ValueError(f"Staged input escapes its pinned tmpfs root: {path}")
    return path


def deny_backing(recording):
    """Disallow archive backing paths, except an enrolled private tmpfs bind."""
    def guard(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes)):
            return
        path = Path(os.fsdecode(args[0]))
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.is_relative_to("/mnt/qnap01"):
            raise ValueError("The paired research route cannot open QNAP")
        if path.is_relative_to("/srv/bulk"):
            staged_path(path, root=recording)

    return guard


def portable_binding(args, cutoff):
    import empty_bootstrap as boot

    file = args.portable_orbit_index
    body = args.portable_orbit_index_sha256
    manifest = args.portable_orbit_producer_sha256
    if file is None:
        if body is not None or manifest is not None:
            raise ValueError("An index pin requires an index file")
        return None
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", body or "") or not re.fullmatch(r"[0-9a-f]{64}", manifest or ""):
        raise ValueError("Supply both trusted index and producer digests")
    staged_path(file)
    producer_path = staged_path(file.parent / "artifact-bind.json", root=file.parent)
    producer = json.loads(boot.checked(producer_path, manifest))
    if (producer["portable_sha256"] != body
            or not 0 < producer["source"]["cutoff_utc_ns"] < cutoff):
        raise ValueError("The portable producer must precede this recording's signed cutoff")
    return [str(file), body, manifest]


def request_from_handoff(args, handoff):
    from leo.operations.tle_archive import TleArchiveReader

    archive = args.archive
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    cutoff = handoff.native["clock_anchor"]["before"]["realtime_ns"]
    return (dict(archive=str(archive), portable=portable_binding(args, cutoff)),
            dict(local_archive=dict(snapshots=len(refs), bytes=sum(ref.byte_size for ref in refs)),
                 original_archive=dict(snapshots_sha256=args.archive_sha256), causal_cutoff_utc_ns=cutoff))


def observe(scan, position, stack, timings, owners, *, active=None, timed_acquire=True):
    """Observe one installed scan inside the actual release publication."""
    from empty_bootstrap import clock, now

    def timed(operation, name):
        def wrapped(*args, **kwargs):
            started = now()
            try:
                return operation(*args, **kwargs)
            finally:
                timings[name].append(clock(started))

        return wrapped

    selected, ordinary = position.selected_packet, scan.analyze

    def packet(*args, **kwargs):
        result = selected(*args, **kwargs)
        owners.append({arm: [[row["observation_id"], row["norad"], row["role"]] for row in rows]
                       for arm, rows in result["rows"].items()})
        return result

    def analyze(*args, **kwargs):
        with ExitStack() as scope:
            if active is not None:
                scope.enter_context(active())
            for name in (("acquire", "solve", "render") if timed_acquire else ("solve", "render")):
                scope.enter_context(patch.object(scan, name, timed(getattr(scan, name), name)))
            return timed(ordinary, "analyze")(*args, **kwargs)

    stack.enter_context(patch.object(position, "selected_packet", packet))
    stack.enter_context(patch.object(scan, "analyze", analyze))


def evidence(output, receipt, packet, owners, *, verified_read=None):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from named_hybrid_baseline import media_and_grid

    result = media_and_grid(output, receipt, packet, owners, verified_read=verified_read, expected_grid=None)
    details = FastStandardAnalysisStore(output).detail(receipt["run_id"])
    if receipt["decision"] == "withheld":
        if any(output.rglob("*.png")) or details["arms"] not in ({}, None):
            raise ValueError("A withheld standard publication has unexpected arms or figures")
    elif set(details["arms"]) != set(ARM_NAMES):
        raise ValueError("Expected both original named calibration arms")
    return dict(result, detail=details)


@contextmanager
def risk_solve(scan, cutoff, original_rank, audit):
    from history_risk_route import binding
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    ordinary, inspect = scan.solve, regional_bound_guard.inspect_boundary
    audit["boundary_checks"] = []

    def boundary(endpoints, width_km, score, *, terminal_only=False):
        result = inspect(endpoints, width_km, score, terminal_only=terminal_only)
        audit["boundary_checks"].append(dict(width_km=width_km, terminal_only=terminal_only,
            endpoints_east_north_km={arm: [float(v) for v in value] if value is not None else None
                                     for arm, value in endpoints.items()}, result=result))
        return result

    def solve(native, reader, assets, offer):
        with binding(reader, cutoff, audit, original_rank):
            return ordinary(native, reader, assets, offer)

    with (patch.object(scan, "solve", solve),
          patch.object(regional_bound_guard, "inspect_boundary", boundary)):
        yield


def publish_active(args, publication, specification, handoff, _layout=None, **_options):
    """Consume exactly one authenticated native handoff under the named specification."""
    import empty_bootstrap as boot
    # Resolve the installed entry before the research port imports expose the checkout.
    from tools import algo08_position, algo08_scan
    from cold_track_row_reuse import SHARING_PIN
    from exact_named_route import SHARING, SOURCES, digest, exact_ports
    from joint_publication import figure_evidence
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from named_history_once import named_solve
    from verified_png_reads import VerifiedPngReads
    from installed_receiver_control import required

    stock_receiver = required(args)
    if (Path(algo08_scan.__file__).resolve() != boot.PAYLOAD / boot.SCANNER
            or Path(algo08_position.__file__).resolve() != boot.PAYLOAD / "tools/algo08_position.py"
            or digest(SHARING) != SHARING_PIN
            or (specification["detector_sha256"] == handoff.receiver) != stock_receiver):
        raise ValueError("Expected the named solver and the genuine detector identity for this mode")
    bound, request = request_from_handoff(args, handoff)
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, png={}, verified_tle=Counter())
    routed = getattr(args, "history_risk_route", False)
    cairo = getattr(args, "cairo_six_sheets", False)
    residual_layout = getattr(args, "cairo_residual_layout", False)
    if cairo and residual_layout:
        raise ValueError("Select one Cairo publication option")
    cache = VerifiedPngReads(args.output, figure_evidence, audit["png"])
    times, owners = {name: [] for name in ("analyze", "solve", "render")}, []

    @contextmanager
    def active():
        with ExitStack() as ports:
            if routed:
                from tools.pipeline_eval.variants import v5_core

                original_rank = v5_core.ranked_initial_nodes
            ports.enter_context(handoff.install(algo08_scan))
            ports.enter_context(exact_ports(bound, request, audit, resident=lambda path: staged_path(path, root=args.archive)))
            ports.enter_context(cache.capture(FastStandardAnalysisStore))
            if routed:
                audit["history_risk"] = risk = {}
                ports.enter_context(risk_solve(algo08_scan, request["causal_cutoff_utc_ns"], original_rank, risk))
            if cairo or residual_layout:
                from history_cairo_render import binding

                audit["cairo_layout"] = layout = {}
                ports.enter_context(binding(algo08_scan, layout, orbit_sheets=cairo))
            yield

    args.output.mkdir()
    launch = SimpleNamespace(bulk_root=args.output, recording=args.recording, archive=args.archive, region=args.region)
    started = boot.now()
    with ExitStack() as stack:
        audit["history"] = stack.enter_context(named_solve(True, boot.RELEASE, boot.PAYLOAD))
        observe(algo08_scan, algo08_position, stack, times, owners, active=active, timed_acquire=False)
        # The shared raw bootstrap already installed this exact lazy facade.
        terminal = publication.run(launch, dict(specification, startup="stock"))
    installed = boot.clock(started)
    if handoff.calls != 1 or len(times["solve"]) != 1 or len(times["render"]) != int(terminal["decision"] == "complete"):
        raise ValueError("The measured exact route did not perform one ordinary named solve")
    started = boot.now()
    sealed = evidence(args.output, terminal, canonical_digest(handoff.native), owners, verified_read=cache.read)
    verification = boot.clock(started)
    detail = dict(raw_route="exact_named_installed", solver_recipe=dict(recipe=MODIFIED_PORTS,
        specification_solver=specification["solver"], rendering=specification["rendering"],
        orbit_index="cold" if bound["portable"] is None else "verified-portable-or-cold",
        archive_sha256=args.archive_sha256, standard_layout=True, exact_ports=True),
        evidence=sealed, timing=times, installed=installed, verification=verification, ports=audit,
        source_sha256={str(path.relative_to(HERE.parents[2])): digest(path)
                       for path in {*SOURCES, Path(__file__), HERE/"named_hybrid_baseline.py"}})
    if routed:
        decision = audit["history_risk"].get("choice", {})
        detail["raw_route"] = "history_risk_installed"
        detail["solver_recipe"]["recipe"] = ("installed 20 ms chronological detections, earlier-orbit dispatch and standard layout"
            if stock_receiver else "20/8 ms, held history, earlier-orbit dispatch and standard layout")
        detail["solver_recipe"]["history_risk"] = dict(requested=True, choice=decision.get("route"),
                                                       reason=decision.get("reason"), optional_prefit_exterior_probe=False)
        detail["source_sha256"].update({f"reports/ALGO08/v3/{name}": digest(HERE/name) for name in RISK_SOURCES})
    if getattr(args, "full_primary_nonanchors", False):
        from full_primary_nonanchor_receiver import DESCRIPTION

        detail["solver_recipe"]["recipe"] = DESCRIPTION
    if cairo or residual_layout:
        from history_cairo_render import RESIDUAL_SOURCES, SOURCES as CAIRO_SOURCES

        detail["solver_recipe"]["web_renderer"] = ("six Cairo sheets and explicit standard layout" if cairo else
            "ordinary Matplotlib orbit sheets, Cairo residuals, explicit position and track layout")
        sources = CAIRO_SOURCES if cairo else RESIDUAL_SOURCES
        detail["source_sha256"].update({f"reports/ALGO08/v3/{name}": digest(HERE/name) for name in sources})
    write(args.output/"exact-named-raw-witness.json", detail, scientific=routed)
    return terminal, detail


def write(path, document, *, scientific=False):
    if scientific:
        from aperture_trial import write as write_scientific

        write_scientific(path, document)
        return
    with path.open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")


def check_strict_input(args):
    mapping = getattr(args, "packed_ci16_map", None)
    digest = getattr(args, "packed_ci16_map_sha256", None)
    codec = getattr(args, "packed_ci16_codec", None)
    if not getattr(args, "strict_packed_eight", False):
        if any(value is not None for value in (mapping, digest, codec)):
            raise ValueError("Packed input in this entry requires --strict-packed-eight")
        return
    if mapping is None or codec is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest or ""):
        raise ValueError("Provide a staged packed map, its trusted SHA-256 and the pinned codec together")
    staged_path(mapping)
    staged_path(codec)


def visit_frame_scope(args, stack):
    path = getattr(args, "visit_frame_custody", None)
    digest = getattr(args, "visit_frame_custody_sha256", None)
    if path is None and digest is None:
        return None
    if path is None or digest is None or getattr(args, "strict_packed_eight", False):
        raise ValueError("Visit frames require their own trusted authority and exclude strict packed input")
    if not (args.eight_ms_native_history and args.held_anchor_route):
        raise ValueError("Visit frames require the signed complete 20/8 ms receiver")
    from empty_bootstrap import clock, now
    from visit_frame_input import binding, custody

    started = now()
    original = custody(staged_path(path), digest, args.recording)
    audit = dict(custody_sha256=digest, inventory_sha256=original["inventory_sha256"],
                 session_id=original["session_id"], raw_authority=original["raw_authority"])
    stack.enter_context(binding(sys.modules["empty_bootstrap"], original, audit))
    audit["setup"] = clock(started)
    return audit


def run(args):
    import unified_short_bootstrap as raw

    for path in (args.recording, args.archive, args.output.parent):
        staged_path(path)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.archive_sha256):
        raise ValueError("Supply the pinned causal archive digest")
    sys.addaudithook(deny_backing(args.recording))
    check_strict_input(args)
    with ExitStack() as stack:
        visit_frame = visit_frame_scope(args, stack)
        terminal = raw.run(args, publisher=publish_active)
    if visit_frame is not None:
        from hashlib import sha256

        visit_frame["port_sha256"] = "sha256:"+sha256((HERE/"visit_frame_input.py").read_bytes()).hexdigest()
        write(args.output/"visit-frame-acquisition.json", visit_frame)
    if not (args.output/"exact-named-raw-witness.json").exists():
        witness = json.loads((args.output/"unified-short-bootstrap.json").read_bytes())
        if terminal["decision"] != "withheld" or witness["scientific_imports_after"]:
            raise ValueError("Expected an authenticated receiver-side withhold")
        checked = evidence(args.output, terminal, witness["native_sha256"], [])
        result = dict(raw_route=witness["route"], ports=None, evidence=checked)
        if getattr(args, "history_risk_route", False):
            result["history_risk"] = dict(requested=True, reason="receiver_side_withhold")
        write(args.output/"exact-named-raw-witness.json", result)
    return terminal


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    layout = command.add_mutually_exclusive_group()
    layout.add_argument("--cairo-six-sheets", action="store_true",
                         help="Use six reviewed Cairo sheets and explicit layout in the standard publication")
    layout.add_argument("--cairo-residual-layout", action="store_true",
                        help="Keep the ordinary orbit sheets and use Cairo residuals and explicit position/track layout")
    for name in ("recording", "archive", "region", "output", "short-binary", "geographic-library",
                 "regional-track-library", "frontier-block-library", "portable-orbit-index"):
        command.add_argument("--"+name, type=Path, required=name not in ("portable-orbit-index", "short-binary"))
    command.add_argument("--archive-sha256", required=True)
    command.add_argument("--portable-orbit-index-sha256")
    command.add_argument("--portable-orbit-producer-sha256")
    command.add_argument("--history-risk-route", action="store_true",
                         help="Use the reviewed earlier-orbit health check before numerical discovery")
    command.add_argument("--installed-stock-receiver", action="store_true",
                         help="Retain the installed 20 ms two-scan detector and chronological selector")
    command.add_argument("--assert-stock-native-sha256", help="Optional saved native parity assertion before solving")
    command.add_argument("--strict-packed-eight", action="store_true",
                         help="Use the complete independently verified packed 20/8 ms input")
    command.add_argument("--packed-ci16-map", type=Path, help="Trusted all-member strict packed map")
    command.add_argument("--packed-ci16-map-sha256", help="Independently verified map SHA-256")
    command.add_argument("--packed-ci16-codec", type=Path, help="Native codec pinned by the trusted map")
    command.add_argument("--visit-frame-custody", type=Path,
                         help="Use the independently authenticated optional 20/8 ms visit-frame index")
    command.add_argument("--visit-frame-custody-sha256", help="Trusted detached visit-frame authority SHA-256")
    command.set_defaults(eight_ms_native_history=True, held_anchor_route=True, prove_empty_graph=True,
                         prove_graph_time_support=True, prove_no_active_curvature=True, one_pass_web_png=False,
                         exact_graph_reuse=False, reuse_verified_png_reads=False, lazy_scanner_detector=False)
    return command


if __name__ == "__main__":
    run(parser().parse_args())
