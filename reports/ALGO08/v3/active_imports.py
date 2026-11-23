"""Census the actual exclusive imports in a complete fresh saved publication."""

import argparse
from contextlib import contextmanager, ExitStack
from hashlib import sha256
import importlib._bootstrap as bootstrap
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BINDING = Path("/dev/shm/leo-saved-overhead.qn1Ynllz/trial/binding.json")
BINDING_SHA = "0d67c61df120f9db660c18ebd6ff8f4c2cdcbafcb2a63c558b2554998ac0dc78"
RAW = Path("/dev/shm/leo-unified-short-layout.lDeYMN5U/trial/result.json")
RAW_SHA = "d1eee8981f1be7e09c79019b7c3e0dbf2136cebaa453e2ae0ff5440d222ace7e"
NATIVE = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
RECEIVER = "tools.pipeline_eval.qualification.blind_compact_run"


def clocks():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    cpu, wall = clocks()
    return dict(cpu_ns=cpu-start[0], elapsed_ns=wall-start[1])


class ImportTrace:
    def __init__(self):
        self.modules, self.compiles, self.stack = [], [], []
        self.phase = "outer"

    @contextmanager
    def scope(self):
        original_load, original_compile = bootstrap._find_and_load, SourceFileLoader.source_to_code

        def load(name, mechanism):
            if name in sys.modules:
                return original_load(name, mechanism)
            parent = self.stack[-1] if self.stack else None
            frame = dict(index=len(self.modules), name=name, phase=self.phase,
                         parent=parent["index"] if parent is not None else None, child_cpu_ns=0, child_elapsed_ns=0)
            self.modules.append(frame)
            self.stack.append(frame)
            start = clocks()
            try:
                return original_load(name, mechanism)
            finally:
                took = elapsed(start)
                frame.update(took)
                for key, value in took.items():
                    frame["exclusive_"+key] = value - frame["child_"+key]
                    if parent is not None:
                        parent["child_"+key] += value
                self.stack.pop()

        def compile_source(loader, data, path, *values, **options):
            start = clocks()
            try:
                return original_compile(loader, data, path, *values, **options)
            finally:
                self.compiles.append(dict(name=loader.name, path=str(path), phase=self.phase,
                                          size=len(data), **elapsed(start)))

        with (patch.object(bootstrap, "_find_and_load", load),
              patch.object(SourceFileLoader, "source_to_code", compile_source)):
            yield

    def mark(self, function, label):
        def called(*args, **kwargs):
            old = self.phase
            self.phase = label
            try:
                return function(*args, **kwargs)
            finally:
                self.phase = old

        return called


def worker(job, mode, output):
    start = clocks()
    trace = ImportTrace() if mode == "traced" else None
    with ExitStack() as scope:
        if trace is not None:
            scope.enter_context(trace.scope())
        import empty_bootstrap as staged
        import unified_short_bootstrap as unified

        _, spec, sources, publication, _ = staged.load_runtime()
        from combined_frontier_run import BLOCK_SHA
        from full_short_raw import RECIPE_SHA
        from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
        from short_graph_guard import prove

        request = json.loads(staged.checked(job, BINDING_SHA))
        args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                              region=Path(request["region"]), output=output, one_pass_web_png=True, exact_graph_reuse=False,
                              **{key: Path(value) for key, value in request["libraries"].items()})
        for path, pin in ((args.geographic_library, GEOGRAPHIC_SHA), (args.regional_track_library, TRACK_SCORES_SHA),
                          (args.frontier_block_library, BLOCK_SHA), (HERE / "one_pass_web_png.py", unified.LAYOUT_SHA256),
                          (args.region, request["region_sha256"])):
            staged.checked(path, pin)
        native = json.loads(staged.checked(Path(request["native"]), NATIVE))
        scan = staged.staged_scanner(sources)
        session, inventory, original = scan.FastScanStore(output).inventory(args.recording, verify_windows=False)
        staged.bind_native(native, session, inventory, RECIPE_SHA, expected="sha256:"+NATIVE)
        if (original["window_count"] != 808 or inventory != request["input_manifest"]
                or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]):
            raise ValueError("Expected the original active weak handoff")
        proof = prove(native, staged.RELEASE / "assets")
        if proof["proven"] or proof["winning_rows"] != 475:
            raise ValueError("The original weak packet requires scientific fitting")

        if trace is not None:
            prepare = unified.layout_renderer

            @contextmanager
            def mark_science(live, enabled, audit):
                with (prepare(live, enabled, audit), patch.object(live, "solve", trace.mark(live.solve, "solve")),
                      patch.object(live, "render", trace.mark(live.render, "render"))):
                    yield

            scope.enter_context(patch.object(unified, "layout_renderer", mark_science))
        handoff, layout = unified.Handoff(session, inventory, RECIPE_SHA, native), {}
        receipt, details = unified.publish_active(args, publication, spec, handoff, layout)
        stage = elapsed(start)
    if receipt["decision"] != "complete" or handoff.calls != 1:
        raise ValueError("Active import trial did not complete one scientific publication")
    result = dict(receipt=receipt, mode=mode, stage=stage, solve=details["solve"], layout=layout, waveform_calls=0)
    if trace is not None:
        result.update(modules=trace.modules, compiles=trace.compiles)
    with (output / "imports.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(receipt, allow_nan=False))


def timed(root, mode):
    from aperture_trial import RELEASE, archive_identity, read, write
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import checked, measure, pairs

    request = read(checked(BINDING, BINDING_SHA))
    raw = read(checked(RAW, RAW_SHA))["observations"]["weak"]["rows"]["candidate"]["science"]
    if archive_identity(Path(request["archive"]["root"])) != request["archive"]:
        raise ValueError("The causal archive has changed")
    output = root / mode
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    invocation = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", BINDING, mode, output]
    timing = measure(invocation, env, output)
    write(root / f"{mode}-clock.json", dict(timing=timing, command=list(map(str, invocation))))
    if timing["exit_code"]:
        raise RuntimeError(timing["stderr_tail"])
    observed = read(output / "imports.json")
    receipt = observed["receipt"]
    evidence = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
    figures = artifacts(output, receipt)["images"]
    detail = read(output / "joint-research-receipt.json")
    (native,) = (output / "fast-scan-automatic-work").glob("*/detections.json")
    if (sha256(native.read_bytes()).hexdigest() != NATIVE
            or any(evidence[key] != raw["publication"][key] for key in ("arms", "owners", "scientific_digests", "raw_authority"))
            or receipt["region"] != raw["publication"]["receipt"]["region"]
            or receipt["terminal_sha256"] != raw["publication"]["receipt"]["terminal_sha256"]
            or len(figures) != 8 or canonical_digest(figures) != canonical_digest(raw["figures"])):
        raise ValueError("Import timing did not reproduce exact original science and publication")
    write(root / f"{mode}-verified.json", dict(timing=timing, profile=observed, figures=figures,
          evidence=evidence, selected_rows=canonical_digest(detail["selected_rows"])))


def setup(root):
    from aperture_trial import RELEASE
    from full_short_physical import environment

    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use new local tmpfs publication roots")
    root.mkdir()
    (root / "tmp").mkdir()
    subprocess.run([RELEASE / "venv/bin/python", "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=environment(root), check=True, timeout=30)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=("original", "traced"))
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        root = parser.parse_args().root
        from dense_geographic_trial import host
        host()
        setup(root)
        for mode in ("original", "traced"):
            timed(root, mode)
