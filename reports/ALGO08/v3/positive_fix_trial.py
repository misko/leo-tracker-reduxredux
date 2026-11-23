"""Measure the installed positive publication path with a saved raw handoff."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import gzip
from hashlib import sha256
import importlib._bootstrap as imports
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SEED = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
RAW = HERE / "measurements/raw-0016-best.json.gz"
RAW_PIN = "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0"
MODES = ("profile", "control", "native")


@contextmanager
def census(enabled):
    if not enabled:
        yield None
        return

    from collections import defaultdict
    from time import process_time_ns
    import saved_overhead

    ledger = saved_overhead.Ledger()
    tops = defaultdict(list)
    timed = Counter()
    ordinary = imports._find_and_load

    def observed(name, method):
        if name in sys.modules or ledger.active in {"imports", "render"}:
            return ordinary(name, method)
        parent = ledger.active
        with ledger.stage("imports"):
            cpu = process_time_ns()
            try:
                return ordinary(name, method)
            finally:
                cost = process_time_ns() - cpu
                tops[parent].append((name, cost))
                timed[parent] += cost

    with (patch.object(saved_overhead, "SHIELDED", frozenset(("render", "imports"))),
          patch.object(imports, "_find_and_load", observed)):
        yield ledger, tops, timed


def worker(job, mode, output):
    sys.path.insert(0, str(HERE))
    from empty_bootstrap import RELEASE, bind_native, checked, clock, load_runtime, now, staged_scanner
    import unified_short_bootstrap as cumulative
    from full_short_raw import RECIPE_SHA

    request = json.loads(job.read_bytes())
    _, specification, sources, publication, _ = load_runtime()
    staged_scanner(sources)
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader
    from named_constrained_research import deny_waveform, inventory_binding

    native = json.loads(checked(Path(request["packet"]), request["native"][7:]))
    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]), output=output,
                           region=Path(request["offer"]), named_survivor_finish=True, exact_graph_reuse=True,
                           reuse_verified_png_reads=True, one_pass_web_png=True,
                           direct_residual_figures=True, direct_orbit_figures=True,
                           grid_feature_projection_library=Path(request["libraries"]["projection"]),
                           geographic_library=Path(request["libraries"]["geographic"]),
                           regional_track_library=Path(request["libraries"]["regional"]),
                           frontier_block_library=Path(request["libraries"]["block"]))
    inventory = inventory_binding(args.recording, Path(request["inventory_file"]), request["session"], request["inventory"])
    bind_native(native, request["session"], request["inventory"], RECIPE_SHA, expected=request["native"])
    handoff = cumulative.Handoff(request["session"], request["inventory"], RECIPE_SHA, native)
    layout, graph, png, decode = {}, {}, {}, {}
    with census(mode == "profile") as observed, ExitStack() as scope:
        decision_started = now()
        scope.enter_context(patch.object(FastScanStore, "inventory", inventory))
        scope.enter_context(patch.object(ShortWindowReader, "__init__", deny_waveform))
        from short_graph_guard import prove

        if observed:
            ledger, tops, timed = observed
            scope.enter_context(ledger.wrap(sys.modules["short_graph_guard"], "prove", "graph_time_support"))
            prove = sys.modules["short_graph_guard"].prove
        proof = prove(native, RELEASE/"assets", use_time_support=True)
        if proof["proven"] or proof["winning_rows"] != 475:
            raise ValueError("Expected original active short packet")

        import joint_publication

        if mode == "native":
            from verified_rgba import RgbaEvidence

            evidence = RgbaEvidence(Path(request["decoder"]), request["decoder_pin"],
                                    joint_publication.figure_evidence, decode)
            scope.enter_context(patch.object(joint_publication, "figure_evidence", evidence))
        if observed:
            from leo.operations.tle_archive import TleArchiveReader
            from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

            for owner, attr, label in (
                (joint_publication, "figure_evidence", "rgba_decode_and_hash"),
                (joint_publication, "artifacts", "research_readback"),
                (FastScanStore, "publish", "scan_publication"),
                (FastStandardAnalysisStore, "publish", "standard_publication"),
                (FastStandardAnalysisStore, "artifact", "sha_verified_image_read"),
                (FastStandardAnalysisStore, "detail", "manifest_check"),
                (TleArchiveReader, "read", "signed_tle_body_read"),
                (TleArchiveReader, "list_snapshots", "signed_tle_inventory"),
                (json, "loads", "json_parsing"),
                (json, "dumps", "json_encoding"),
                (json, "dump", "json_encoding"),
                (os, "fsync", "durable_sync"),
            ):
                scope.enter_context(ledger.wrap(owner, attr, label))
            original_layout = cumulative.layout_renderer

            @contextmanager
            def measured_layout(scan, enabled, audit, **options):
                from tools import algo08_position

                with (original_layout(scan, enabled, audit, **options), ledger.wrap(scan, "render", "render"),
                      ledger.wrap(scan, "solve", "solve_other"), ledger.wrap(scan, "immutable_json", "sealed_json"),
                      ledger.wrap(algo08_position, "prepare_native_scan", "native_and_orbit_preparation")):
                    yield

            scope.enter_context(patch.object(cumulative, "layout_renderer", measured_layout))

        receipt, detail = cumulative.publish_active(args, publication, specification, handoff, layout, graph_audit=graph,
                                                     png_read_audit=png)
        decision = clock(decision_started)
        stages = observed[0].finish() if observed else None
    if handoff.calls != 1 or receipt["decision"] != "complete" or png["verified"] != 8 or png["reused"] != 8:
        raise ValueError("Expected the original complete verified saved handoff")
    from aperture_trial import write

    write(output/"positive-fix.json", dict(decision=decision, stages=stages, receipt=receipt, png=png, decode=decode,
          first_imports=({k: sorted(v, key=lambda x: -x[1]) for k,v in tops.items()} if observed else None),
          import_ns=dict(timed) if observed else None, render=layout, graph=graph, solve=detail["solve"],
          installed={"launcher": specification["detector_sha256"], "sources": detail["source_sha256"]},
          projection=detail["grid_feature_projection"], finish=detail["named_survivor_finish"], waveform_calls=0))


def run(root):
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import verify_position_sidecars
    from short_raw_diagnostic import measure, pairs

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use new private tmpfs for the saved publications")
    reference = json.loads(gzip.decompress(checked(RAW, RAW_PIN)))
    expected = reference["original"]["candidate"]
    admission = reference["admission"]
    archive, offer = SEED/"tle", SEED/"offer.json"
    checked(offer, admission["offer_sha256"])
    if pairs.archive_identity(archive)["snapshots_sha256"] != admission["archive"]["sha256"]:
        raise ValueError("Saved causal archive differs from the raw run")
    packet, = (SEED/"candidate").glob("fast-scan-automatic-work/*/detections.json")
    inventory = SEED/"candidate/fast-scan-inputs"/(admission["session"]+".json")
    checked(packet, expected["native_file_sha256"])
    checked(inventory, admission["inventory"][7:])
    libraries = {k: SEED/f"{k}.so" for k in ("geographic", "regional", "block", "projection")}
    for k, path in libraries.items():
        checked(path, admission["library_sha256"][k])
    root.mkdir()
    (root/"tmp").mkdir()
    decoder = root/"unfilter.so"
    build = ["cc", "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
             HERE/"verified_rgba_rows.c", "-o", decoder]
    subprocess.run(build, check=True)
    digest = sha256(decoder.read_bytes()).hexdigest()
    job = root/"binding.json"
    write(job, dict(recording=admission["recording"], session=admission["session"], inventory=admission["inventory"],
                    native=expected["native_sha256"], packet=packet, inventory_file=inventory, archive=archive,
                    offer=offer, libraries=libraries, decoder=decoder, decoder_pin=digest))
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    python = RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    runs = {}
    for mode in MODES:
        out = root/mode
        command = [python, "-IB", __file__, "worker", job, mode, out]
        clocks = measure(command, env, out)
        write(root/f"{mode}-clock.json", dict(process=clocks, command=command))
        if clocks["exit_code"]:
            raise RuntimeError(clocks["stderr_tail"])
        worker = read(out/"positive-fix.json")
        publication = worker["receipt"]
        science = pairs.evidence(out, publication, clocks["started_unix_ns"], read_only=True)
        figures = artifacts(out, publication)["images"]
        research = read(out/"joint-research-receipt.json")
        original = expected["science"]
        if (worker["waveform_calls"] or worker["finish"] != {"requested": True, "paid_final_fit": True}
                or any(science[k] != original[k] for k in ("arms", "owners", "raw_authority", "scientific_digests"))
                or publication["region"] != admission["offer"]
                or publication["terminal_sha256"] != original["receipt"]["terminal_sha256"]
                or research["selected_rows"] != expected["research"]["selected_rows"]
                or canonical_digest(figures) != canonical_digest(expected["figures"])
                or canonical_digest(figures) != canonical_digest(research["evidence"]["images"])):
            raise ValueError("The official science, owner roles, grid or original figures changed")
        runs[mode] = dict(clocks=clocks, worker=worker, science=science, figures=figures,
                          owner_rows_sha256=canonical_digest(research["selected_rows"]))
    a, b = ("control", "native")
    sidecars = verify_position_sidecars(root/a, root/b, runs[a]["science"]["receipt"]["run_id"],
                                       runs[a]["figures"], runs[b]["figures"])
    write(root/"result.json", dict(machine=machine, runs=runs, build=build, library_sha256=digest,
                                  original_raw_sha256=RAW_PIN, source_sha256={
                                      p: sha256((HERE/p).read_bytes()).hexdigest() for p in
                                      ("positive_fix_trial.py", "verified_rgba.py", "verified_rgba_rows.c")},
                                  sidecars=sidecars))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("worker_mode", choices=MODES, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mode == "run":
        run(args.root)
    else:
        worker(args.root, args.worker_mode, args.output)
