"""Charge disjoint fixed costs around a saved weak official publication."""

import argparse
from collections import Counter
from contextlib import contextmanager, ExitStack
import gzip
from hashlib import sha256
import importlib._bootstrap as imports
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REFERENCE_ROOT = Path("/dev/shm/leo-unified-short-layout.lDeYMN5U/trial")
RAW_RECEIPT = "d1eee8981f1be7e09c79019b7c3e0dbf2136cebaa453e2ae0ff5440d222ace7e"
NATIVE_SHA = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
ORDER = ("original", "reuse")
SHIELDED = frozenset(("solve", "render", "imports"))


def now():
    return process_time_ns(), perf_counter_ns()


class Ledger:
    """Exclusive stage times, even when an official operation calls another."""

    def __init__(self):
        self.started = self.last = now()
        self.active = "remaining"
        self.cpu, self.wall, self.calls = Counter(), Counter(), Counter()

    def switch(self, name):
        current = now()
        self.cpu[self.active] += current[0]-self.last[0]
        self.wall[self.active] += current[1]-self.last[1]
        self.last, self.active = current, name

    @contextmanager
    def stage(self, name):
        old = self.active
        if old == name or old in SHIELDED:
            yield
            return
        self.calls[name] += 1
        self.switch(name)
        try:
            yield
        finally:
            self.switch(old)

    def wrap(self, owner, attr, label):
        original = getattr(owner, attr)

        def observed(*values, **options):
            name = label() if callable(label) else label
            with self.stage(name):
                return original(*values, **options)

        return patch.object(owner, attr, observed)

    def finish(self):
        self.switch("complete")
        return {key: dict(cpu_ns=self.cpu[key], elapsed_ns=self.wall[key], calls=self.calls[key])
                for key in sorted(self.cpu)}


def worker(job, mode, output):
    ledger = Ledger()
    original_import = imports._find_and_load

    def imported(name, mechanism):
        if name in sys.modules or ledger.active in SHIELDED:
            return original_import(name, mechanism)
        with ledger.stage("imports"):
            return original_import(name, mechanism)

    original_read = Path.read_bytes

    def read_bytes(path):
        if path.name == "detections.json" and output in path.parents:
            with ledger.stage("detector_readback"):
                return original_read(path)
        return original_read(path)

    with ExitStack() as hooks:
        hooks.enter_context(patch.object(imports, "_find_and_load", imported))
        hooks.enter_context(patch.object(Path, "read_bytes", read_bytes))
        import empty_bootstrap as staged
        import unified_short_bootstrap as unified

        with ledger.stage("checked_sources_and_assets"):
            _, specification, sources, publication, _ = staged.load_runtime()
        from combined_frontier_run import BLOCK_SHA
        from full_short_raw import RECIPE_SHA
        from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
        from leo.contracts import digests
        from leo.storage import fast_scan, fast_standard_analysis as standard
        from short_graph_guard import prove
        import joint_publication

        for owner, attr, label in (
            (json, "loads", "json_decode"), (json, "dumps", "json_encode"), (json, "dump", "json_encode"),
            (fast_scan.FastScanStore, "inventory", "inventory"), (fast_scan.FastScanStore, "publish_inventory", "persist"),
            (fast_scan.FastScanStore, "publish", "persist"),
            (standard.FastStandardAnalysisStore, "publish", "persist"),
            (standard.FastStandardAnalysisStore, "detail", "manifest_validate"),
            (standard.FastStandardAnalysisStore, "position_grid", "sidecar_readback"),
            (standard.FastStandardAnalysisStore, "position_path", "sidecar_readback"),
            (standard.FastStandardAnalysisStore, "artifact", lambda: "research_png_read" if ledger.active == "research_evidence" else "official_png_read"),
            (joint_publication, "artifacts", "research_evidence"),
            (joint_publication, "figure_evidence", "png_decode"),
            (digests, "canonical_json_bytes", "json_encode"), (fast_scan, "canonical_json_bytes", "json_encode"),
            (os, "fsync", "fsync"),
        ):
            hooks.enter_context(ledger.wrap(owner, attr, label))

        request = json.loads(job.read_bytes())
        args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                               region=Path(request["region"]), output=output, one_pass_web_png=True,
                               reuse_verified_png_reads=mode == "reuse", exact_graph_reuse=False,
                               **{key: Path(value) for key, value in request["libraries"].items()})
        with ledger.stage("checked_sources_and_assets"):
            for path, pin in ((args.geographic_library, GEOGRAPHIC_SHA), (args.regional_track_library, TRACK_SCORES_SHA),
                              (args.frontier_block_library, BLOCK_SHA), (HERE / "one_pass_web_png.py", unified.LAYOUT_SHA256)):
                staged.checked(path, pin)
            if sha256(args.region.read_bytes()).hexdigest() != request["region_sha256"]:
                raise ValueError("Original weak regional offer changed")
        with ledger.stage("saved_packet_load"):
            native = json.loads(staged.checked(Path(request["native"]), NATIVE_SHA))
        scan = staged.staged_scanner(sources)
        session, digest, inventory = scan.FastScanStore(output).inventory(args.recording, verify_windows=False)
        with ledger.stage("signed_packet_verify"):
            staged.bind_native(native, session, digest, RECIPE_SHA, expected="sha256:"+NATIVE_SHA)
            if (inventory["window_count"] != 808 or digest != request["input_manifest"]
                    or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]):
                raise ValueError("Original saved packet or recording authority changed")
        with ledger.stage("graph_ineligible_proof"):
            proof = prove(native, staged.RELEASE / "assets")
            if proof["proven"] or proof["winning_rows"] != 475:
                raise ValueError("Expected the original active short packet")

        handoff, layout, png_audit = unified.Handoff(session, digest, RECIPE_SHA, native), {}, {}
        original_layout, original_install = unified.layout_renderer, handoff.install

        @contextmanager
        def instrumented_handoff(target):
            with original_install(target), ledger.wrap(target, "acquire", "handoff"):
                yield

        @contextmanager
        def instrumented_layout(target, enabled, audit):
            with (original_layout(target, enabled, audit), ledger.wrap(target, "render", "render"),
                  ledger.wrap(target, "solve", "solve"), ledger.wrap(target, "immutable_json", "persist")):
                yield

        with patch.object(handoff, "install", instrumented_handoff), patch.object(unified, "layout_renderer", instrumented_layout):
            receipt, detail = unified.publish_active(args, publication, specification, handoff, layout, png_read_audit=png_audit)
    stages = ledger.finish()
    if handoff.calls != 1 or receipt["decision"] != "complete":
        raise ValueError("The fresh saved active publication must use one signed handoff")
    with (output / "overhead.json").open("x") as stream:
        json.dump(dict(stages=stages, receipt=receipt, layout=layout, reuse=png_audit, waveforms=0,
                       handoffs=handoff.calls, source_sha256=detail["source_sha256"],
                       measured_cpu_ns=ledger.last[0]-ledger.started[0], measured_elapsed_ns=ledger.last[1]-ledger.started[1]),
                  stream, indent=2, allow_nan=False)
    print(json.dumps(receipt, allow_nan=False))


def run(root):
    from aperture_trial import RELEASE, archive_identity, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from publication_media_checks import image_comparison_fields, verify_position_sidecars
    from short_raw_diagnostic import checked, measure, pairs

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh saved outputs on tmpfs")
    raw = gzip.decompress((HERE / "measurements/unified-short-layout.json.gz").read_bytes())
    if sha256(raw).hexdigest() != RAW_RECEIPT:
        raise ValueError("The authoritative cumulative raw pair changed")
    weak = json.loads(raw)["observations"]["weak"]
    reference = weak["rows"]["candidate"]
    command = reference["command"]
    def flag(name):
        return command[command.index("--"+name)+1]

    packet = checked(native_packet(REFERENCE_ROOT / "weak/candidate"), NATIVE_SHA)
    if archive_identity(Path(flag("archive"))) != weak["causal_archive"]:
        raise ValueError("Original causal archive changed")
    root.mkdir()
    (root / "tmp").mkdir()
    request = dict(archive=weak["causal_archive"], recording=flag("recording"), region=flag("region"),
                   region_sha256=weak["request_offer_sha256"], native=str(packet),
                   input_manifest=reference["science"]["input_manifest"], raw_authority=reference["science"]["publication"]["raw_authority"],
                   libraries={key.replace("-", "_"): flag(key) for key in ("geographic-library", "regional-track-library", "frontier-block-library")})
    job = root / "binding.json"
    write(job, request)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    result, owners = {}, {}
    for mode in ORDER:
        output = root / mode
        invocation = [python, "-IB", __file__, "worker", job, mode, output]
        timing = measure(invocation, env, output)
        write(root / f"{mode}-clock.json", dict(timing=timing, command=list(map(str, invocation))))
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])
        profile = read(output / "overhead.json")
        receipt = profile["receipt"]
        achieved = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
        evidence = artifacts(output, receipt)
        archived = reference["science"]["publication"]
        science_fields = ("raw_authority", "arms", "owners", "scientific_digests")
        if (any(achieved[k] != archived[k] for k in science_fields) or achieved["receipt"]["region"] != archived["receipt"]["region"]
                or receipt["terminal_sha256"] != archived["receipt"]["terminal_sha256"]
                or canonical_digest(evidence["images"]) != canonical_digest(reference["science"]["figures"])
                or len(evidence["images"]) != 8 or profile["waveforms"] != 0):
            raise ValueError(f"{mode} changed scoped weak raw-archived science or images")
        detail = read(output / "joint-research-receipt.json")
        owners[mode] = detail["selected_rows"]
        if canonical_digest(detail["evidence"]["images"]) != canonical_digest(evidence["images"]):
            raise ValueError("The timed research receipt lost an independent image check")
        result[mode] = dict(profile=profile, clock=timing, evidence=achieved, images=evidence["images"],
                            selected_rows=canonical_digest(owners[mode]))
    a, b = (result[mode] for mode in ORDER)
    run_id = a["profile"]["receipt"]["run_id"]
    sa, sb = (FastStandardAnalysisStore(root / mode) for mode in ORDER)
    if (owners["original"] != owners["reuse"] or a["images"] != b["images"]
            or any(sa.artifact(run_id, name) != sb.artifact(run_id, name) for name in a["images"])
            or b["profile"]["reuse"]["verified"] != 8 or b["profile"]["reuse"]["reused"] != 8
            or b["profile"]["reuse"]["fallbacks"] != 0):
        raise ValueError("The matched saved publication did not validate all eight reused reads")
    sidecars = verify_position_sidecars(root / ORDER[0], root / ORDER[1], run_id, a["images"], b["images"])
    write(root / "result.json", dict(case="DS30-0016", machine=machine, order=ORDER, inputs=request, runs=result,
          sidecars=sidecars, archived_raw_sha256=RAW_RECEIPT,
          archived_raw=dict(clock=reference["clock"], report_file_s=reference["science"]["report_file_s"],
                            bootstrap=reference["science"]["bootstrap"]),
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "saved-overhead-protocol.md").read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        cli.add_argument("job", type=Path)
        cli.add_argument("mode", choices=ORDER)
        cli.add_argument("output", type=Path)
        worker(**vars(cli.parse_args(sys.argv[2:])))
    else:
        cli.add_argument("root", type=Path)
        run(cli.parse_args().root)
