"""Profile one genuine saved 8 ms positive publication without changing its options."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import hashlib
import importlib._bootstrap as imports
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from saved_overhead import Ledger, SHIELDED, now
import weak_all8_combined as weak


REFERENCE = Path("/dev/shm/leo-v3-weak-all8-combined-result02")
REFERENCE_SEAL = "b29c1e288400792af10176f5936fce7206ba7d5f5c817cf214ce08ad800e7cfc"
PROTOCOL = HERE/"weak-publisher-attribution-protocol.md"


def read_scope(path, target):
    if path.suffix == ".zst" or path.name.endswith(".ci16"):
        raise ValueError("Saved worker attempted waveform access")
    if path.is_relative_to(target):
        if path.name == "detections.json":
            return "detection_read"
        if path.name == "manifest.json":
            return "manifest_read"
        if path.suffix == ".png":
            return "png_read"
        if path.name in ("position-grid.json", "position-path.json"):
            return "sidecar_read"
        return "output_metadata_read"
    return "source_and_asset_read"


@contextmanager
def watch(target, ledger, detail):
    """Time named operations exclusively, shielding nested statistics during solve/render."""
    original_import = imports._find_and_load
    original_read, original_text = Path.read_bytes, Path.read_text
    miss_cpu, miss_wall, file_bytes = Counter(), Counter(), Counter()

    def observed_import(name, mechanism):
        if ledger.active in SHIELDED or name in sys.modules:
            return original_import(name, mechanism)
        start = now()
        with ledger.stage("imports"):
            result = original_import(name, mechanism)
        stop = now()
        miss_cpu[name] += stop[0] - start[0]
        miss_wall[name] += stop[1] - start[1]
        return result

    def observed_read(path, read, *args, **kwargs):
        label = read_scope(path, target)
        if ledger.active in SHIELDED:
            return read(path, *args, **kwargs)
        with ledger.stage(label):
            value = read(path, *args, **kwargs)
        file_bytes[label] += len(value)  # ASCII contracts, characters for read_text.
        return value

    with ExitStack() as hooks:
        hooks.enter_context(patch.object(imports, "_find_and_load", observed_import))
        with ledger.stage("profiler_setup"):
            import joint_publication
            import short_graph_guard
            import unified_short_bootstrap as unified
            from leo.storage import fast_scan, fast_standard_analysis as standard

            hooks.enter_context(patch.object(Path, "read_bytes", lambda p: observed_read(p, original_read)))
            hooks.enter_context(patch.object(Path, "read_text", lambda p, *a, **kw: observed_read(p, original_text, *a, **kw)))
            for owner, name, label in (
                (json, "dumps", "encode"),
                (json, "dump", "encode"),
                (json, "loads", "decode"),
                (hashlib, "sha256", "hash"),
                (joint_publication, "sha256", "hash"),
                (standard, "validate", "manifest_validation"),
                (standard, "validate_grid", "grid_validation"),
                (standard, "validate_path", "path_validation"),
                (standard.FastStandardAnalysisStore, "detail", "manifest_access"),
                (standard.FastStandardAnalysisStore, "artifact", "png_validation"),
                (standard.FastStandardAnalysisStore, "_presentation_evidence", "sidecar_access"),
                (standard.FastStandardAnalysisStore, "publish", "publication_write"),
                (fast_scan.FastScanStore, "publish_inventory", "publication_write"),
                (fast_scan.FastScanStore, "publish", "publication_write"),
                (fast_scan, "immutable_json", "publication_write"),
                (standard, "immutable_json", "publication_write"),
                (short_graph_guard, "prove", "graph_eligibility"),
                (joint_publication, "figure_evidence", "png_decode_and_rgba"),
                (joint_publication, "artifacts", "research_artifact_receipt"),
                (os, "fsync", "fsync"),
            ):
                hooks.enter_context(ledger.wrap(owner, name, label))

            # hashlib covers the contracted digest adapters after their inputs
            # are encoded. These modules also hold direct imported aliases.
            hooks.enter_context(ledger.wrap(weak.staged, "sha256", "hash"))
            hooks.enter_context(ledger.wrap(short_graph_guard, "sha256", "hash"))
            layout = unified.layout_renderer

            @contextmanager
            def renderer(scan, *args, **kwargs):
                with (layout(scan, *args, **kwargs),
                      ledger.wrap(scan, "solve", "solve"),
                      ledger.wrap(scan, "render", "render"),
                      ledger.wrap(scan, "scan_report", "report_view"),
                      ledger.wrap(scan, "immutable_json", "publication_write")):
                    yield

            hooks.enter_context(patch.object(unified, "layout_renderer", renderer))
        yield
    detail.update(import_cpu_ns=dict(miss_cpu), import_elapsed_ns=dict(miss_wall), read_lengths=dict(file_bytes))


def worker(root):
    import raw_cfo_north_trial as trial

    original = trial.publish_saved
    measured = {}

    def timed(request, target, *args, **kwargs):
        ledger = Ledger()
        detail = {}
        with watch(target, ledger, detail):
            result = original(request, target, *args, **kwargs)
        stages = ledger.finish()
        measured.update(stages=stages, detail=detail, cpu_ns=ledger.last[0]-ledger.started[0],
                        elapsed_ns=ledger.last[1]-ledger.started[1])
        return result

    with patch.object(trial, "publish_saved", timed):
        weak.worker(root)
    if not measured:
        raise ValueError("Did not observe the live saved publication seam")
    weak.write(root/"profile.json", measured)


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    machine = host()
    tmpfs(root.parent)
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Freeze the observer before launch")
    root.mkdir()
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    python = weak.staged.RELEASE/"venv/bin/python"
    font = measure([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env, root/"font")
    weak.write(root/"font-clock.json", font)
    if font["exit_code"]:
        raise RuntimeError(font["stderr_tail"])
    command = ["/usr/bin/timeout", "--kill-after=2s", "35s", python, "-IB", Path(__file__), "worker", root]
    weak.write(root/"binding.json", dict(host=machine, commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
               sources=weak.pins(), command=list(map(str, command)), control_sha256=REFERENCE_SEAL,
               observer_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), PROTOCOL, HERE/"saved_overhead.py")}))
    clock = measure(command, env, root/"candidate")
    weak.write(root/"clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def validate_profile(profile):
    stages = profile["stages"]
    for key in ("cpu_ns", "elapsed_ns"):
        if sum(row[key] for row in stages.values()) != profile[key]:
            raise ValueError("Exclusive measurements do not reconcile")
    for key in ("solve", "render"):
        if stages[key]["calls"] != 1:
            raise ValueError("Expected one installed operation at each protected boundary")
    return {key: sum(row[key] for stage, row in stages.items() if stage not in ("solve", "render"))
            for key in ("cpu_ns", "elapsed_ns")}


def seal(root):
    from leo.contracts.digests import canonical_digest

    control = json.loads(weak.staged.checked(REFERENCE/"seal.json", REFERENCE_SEAL))
    weak.seal(root)
    published, profile = (weak.read(root/f"{name}.json") for name in ("seal", "profile"))
    report = validate_profile(profile)
    fields = ("identity", "terminal", "arms", "roles", "grid_and_path", "grid_points", "images", "named_finish")
    if any(canonical_digest(published["science"][name]) != canonical_digest(control["science"][name])
           for name in fields if isinstance(published["science"][name], dict)):
        raise ValueError("Instrumented publication changed signed science or media")
    if any(published["science"][name] != control["science"][name] for name in fields
           if not isinstance(published["science"][name], dict)):
        raise ValueError("Instrumented publication changed the terminal, grid or named finish")
    if [row["result"] for row in published["regional"]] != [row["result"] for row in control["regional"]]:
        raise ValueError("Actual paid regional proof did not reproduce")
    weak.write(root/"attributed.json", dict(reconciled=report, reference_seal_sha256=REFERENCE_SEAL,
               control_clock=control["clock"], control_scopes=control["disjoint_saved_costs"], profile=profile,
               through_exit=published["clock"], original_subscopes=published["disjoint_saved_costs"], parity=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "seal"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "seal": seal}[args.action](args.root)
