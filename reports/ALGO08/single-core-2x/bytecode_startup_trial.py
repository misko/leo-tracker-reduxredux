"""Measure fresh ALGO08 startup using private checked-hash CPython bytecode."""

import builtins
import json
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns


class ReachedAnalyze(Exception):
    """The candidate reached the boundary before acquisition."""


def frozen_candidate_imports(bundle, scratch):
    from types import SimpleNamespace

    from tools.pipeline_eval.qualification import experimental_publication

    if Path(experimental_publication.__file__).resolve() != (
        bundle / "tools/pipeline_eval/qualification/experimental_publication.py"
    ):
        raise RuntimeError("The screened-stock launcher did not load from the frozen bundle")

    def stop(*args, **kwargs):
        raise ReachedAnalyze

    original_import = builtins.__import__

    def import_boundary(name, globals=None, locals=None, fromlist=(), level=0):
        module = original_import(name, globals, locals, fromlist, level)
        if name == "tools" and fromlist and "algo08_scan" in fromlist:
            module.algo08_scan.analyze = stop
            builtins.__import__ = original_import
        return module

    args = SimpleNamespace(
        recording=scratch / "must-not-open.iq",
        bulk_root=scratch / "publication",
        archive=scratch / "archive",
        region=scratch / "region.json",
    )
    specification = json.loads((bundle / "spec.json").read_bytes())
    builtins.__import__ = import_boundary
    try:
        experimental_publication.run(args, specification)
    except ReachedAnalyze:
        return
    finally:
        builtins.__import__ = original_import
    raise RuntimeError("The import-only run did not reach the publication boundary")


def worker(target, mode, release, bundle, scratch, manifest):
    from importlib import _bootstrap_external as bootstrap
    from importlib.machinery import SourceFileLoader
    import _imp

    if not sys.dont_write_bytecode or _imp.check_hash_based_pycs != "default":
        raise RuntimeError("Expected normal checked-hash verification and no bytecode writes")
    trace = mode == "natural" or mode.endswith("-trace")
    mode = mode.removesuffix("-trace")
    roots = tuple(f"{root}/" for root in (release / "tools", release / "src", bundle / "tools"))
    entries = json.loads(manifest.read_bytes()) if mode != "natural" else {}
    cache_path = bootstrap.cache_from_source
    get_code = SourceFileLoader.get_code
    source_to_code = SourceFileLoader.source_to_code
    loaded = set()
    compiled = set()

    def private_cache(path, *args, **kwargs):
        if path in entries:
            cache = entries[path]["bytecode"]
            return f"{cache}.absent" if mode == "source" else cache
        return cache_path(path, *args, **kwargs)

    def trace_load(self, fullname):
        path = self.get_filename(fullname)
        if path.startswith(roots):
            loaded.add(path)
        return get_code(self, fullname)

    def trace_compilation(self, data, path, **kwargs):
        if path.startswith(roots):
            compiled.add(path)
        return source_to_code(self, data, path, **kwargs)

    bootstrap.cache_from_source = private_cache
    if trace:
        SourceFileLoader.get_code = trace_load
        SourceFileLoader.source_to_code = trace_compilation
    started = process_time_ns()
    if target == "candidate":
        frozen_candidate_imports(bundle, scratch)
    else:
        from tools import algo08_scan

        if Path(algo08_scan.__file__).resolve() != (release / "tools/algo08_scan.py"):
            raise RuntimeError("The released CLI did not load from the installed release")
    result = {"boundary_cpu_ns": process_time_ns() - started}
    if trace:
        result.update(loaded=sorted(loaded), compiled=sorted(compiled))
    if mode == "natural":
        result["cache_paths_present"] = sorted(path for path in loaded if Path(cache_path(path)).is_file())
    print(json.dumps(result))


def checked_cache(source, bytecode):
    from hashlib import sha256
    from importlib.util import MAGIC_NUMBER, source_hash

    source_bytes = source.read_bytes()
    code = bytecode.read_bytes()
    if code[:8] != MAGIC_NUMBER + b"\x03\x00\x00\x00" or code[8:16] != source_hash(source_bytes):
        raise ValueError(f"Checked-hash bytecode does not match the unchanged source: {source}")
    return {
        "bytecode": str(bytecode),
        "bytecode_sha256": sha256(code).hexdigest(),
        "source_sha256": sha256(source_bytes).hexdigest(),
    }


def verify_caches(entries):
    for source, expected in entries.items():
        if checked_cache(Path(source), Path(expected["bytecode"])) != expected:
            raise ValueError(f"Source or bytecode changed after private compilation: {source}")


def verify_frozen_sources(bundle):
    from hashlib import sha256

    specification = bundle / "spec.json"
    raw = specification.read_bytes()
    sources = json.loads(raw)["sources"]
    for name, digest in sources.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Expected a source path below the frozen bundle: {relative}")
        if sha256((bundle / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source differs from its pin: {relative}")
    return {"spec_sha256": sha256(raw).hexdigest(), "pins_verified": len(sources)}


def cache_self_test(scratch, environment):
    import py_compile
    import subprocess

    source = scratch / "bytecode_probe.py"
    source.write_text("value = 'original'\n")
    expected_cache = scratch / "__pycache__" / f"{source.stem}.{sys.implementation.cache_tag}.pyc"
    bytecode = Path(py_compile.compile(
        str(source), cfile=str(expected_cache), doraise=True, optimize=0,
        invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
    ))
    entries = {str(source): checked_cache(source, bytecode)}

    def observe():
        code = "import bytecode_probe; print(bytecode_probe.value)"
        return subprocess.run(
            [sys.executable, "-BPs", "-v", "-c", code], text=True, capture_output=True, check=True,
            env=dict(environment, PYTHONPATH=str(scratch)),
        )

    observed = observe()
    if observed.stdout.strip() != "original" or f"code object from {str(bytecode)!r}" not in observed.stderr:
        raise RuntimeError("The release interpreter did not read valid bytecode under -B")
    raw = bytecode.read_bytes()
    bytecode.write_bytes(raw + b"tampered")
    try:
        verify_caches(entries)
    except ValueError:
        pass
    else:
        raise RuntimeError("A changed bytecode body passed the full-file digest check")
    bytecode.write_bytes(raw)
    source.write_text("value = 'changed'\n")
    observed = observe()
    if (observed.stdout.strip() != "changed" or f"code object from {str(bytecode)!r}" in observed.stderr
            or bytecode.read_bytes() != raw):
        raise RuntimeError("The release interpreter did not bypass stale bytecode without writing under -B")


def measure(release, bundle, repeats, candidate_misses_only):
    from hashlib import sha256
    import os
    import py_compile
    import resource
    import subprocess
    from tempfile import TemporaryDirectory

    release, bundle = release.resolve(strict=True), bundle.resolve(strict=True)
    if Path(sys.executable).absolute() != release / "venv/bin/python":
        raise ValueError("Run the controller with the exact installed launcher interpreter")
    pins = verify_frozen_sources(bundle)
    script = str(Path(__file__).resolve(strict=True))
    targets = ("candidate",) if candidate_misses_only else ("release", "candidate")

    with TemporaryDirectory(prefix="algo08-private-pyc-") as temporary:
        scratch = Path(temporary)
        for name in ("publication", "archive", "mpl", "xdg"):
            (scratch / name).mkdir()
        (scratch / "region.json").write_text('{"center":[0,0],"width_km":10}')
        environment = os.environ.copy()
        environment.pop("PYTHONPYCACHEPREFIX", None)
        environment.pop("PYTHONOPTIMIZE", None)
        environment.update(
            MPLCONFIGDIR=str(scratch / "mpl"), XDG_CACHE_HOME=str(scratch / "xdg"), TMPDIR=str(scratch),
        )
        cache_self_test(scratch, environment)
        found = {}

        def run(target, mode):
            path = [str(release / "src"), str(release)]
            if target == "candidate":
                path.insert(0, str(bundle))
            manifest_path = scratch / f"{target}-cache.json"
            launch_env = dict(environment, PYTHONPATH=os.pathsep.join(path))
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = perf_counter_ns()
            process = subprocess.run(
                [sys.executable, "-BPs", script, "worker", target, mode,
                 str(release), str(bundle), str(scratch), str(manifest_path)],
                capture_output=True, text=True, env=launch_env, cwd=scratch,
            )
            elapsed_ns = perf_counter_ns() - start
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            if process.returncode:
                raise RuntimeError(f"{target} {mode} exited {process.returncode}:\n{process.stderr}")
            result = json.loads(process.stdout)
            result.update(
                cpu_ns=round(1e9 * ((usage.ru_utime - before.ru_utime) + (usage.ru_stime - before.ru_stime))),
                elapsed_ns=elapsed_ns,
                input_blocks=usage.ru_inblock - before.ru_inblock,
            )
            return result

        for target in targets:
            natural = run(target, "natural")
            entries = {}
            sources = natural["compiled"] if candidate_misses_only else natural["loaded"]
            for source in sources:
                bytecode = scratch / f"{sha256(source.encode()).hexdigest()}.pyc"
                py_compile.compile(
                    source, cfile=str(bytecode), dfile=source, doraise=True,
                    invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH, optimize=0,
                )
                entries[source] = checked_cache(Path(source), bytecode)
            verify_caches(entries)
            (scratch / f"{target}-cache.json").write_text(json.dumps(entries))
            source_trace = run(target, "source-trace")
            checked_trace = run(target, "checked-trace")
            if (source_trace["loaded"] != natural["loaded"] or checked_trace["loaded"] != natural["loaded"]
                    or source_trace["compiled"] != sorted(entries) or checked_trace["compiled"]):
                raise RuntimeError(
                    f"The {target} cache experiment did not exercise both intended paths. "
                    f"Missing source compilations: {sorted(set(entries) - set(source_trace['compiled']))}. "
                    f"Unexpected source compilations: {sorted(set(source_trace['compiled']) - set(entries))}. "
                    f"Checked-arm compilations: {checked_trace['compiled']}."
                )
            for property_name in ("loaded", "compiled", "cache_paths_present"):
                paths = natural.pop(property_name)
                natural[property_name] = {
                    "bundle": sum(path.startswith(f"{bundle}/") for path in paths),
                    "release": sum(path.startswith(f"{release}/") for path in paths),
                }
            found[target] = {
                "natural": natural, "trials": [], "entries": entries,
                "source_compilations": len(source_trace["compiled"]),
                "checked_compilations": len(checked_trace["compiled"]),
            }

        for repetition in range(repeats):
            ordered_targets = targets if repetition % 2 == 0 else reversed(targets)
            for target in ordered_targets:
                ordering = ("source", "checked") if (target == "release") == (repetition % 2 == 0) else (
                    "checked", "source",
                )
                found[target]["trials"].append({mode: run(target, mode) for mode in ordering})

        for data in found.values():
            verify_caches(data.pop("entries"))
        if any(scratch.glob("*.absent")) or any((scratch / "publication").iterdir()):
            raise RuntimeError("An import-only arm wrote a bytecode or publication artifact")
        if verify_frozen_sources(bundle) != pins:
            raise RuntimeError("The frozen candidate specification changed")
    return dict(
        pins=pins, release=str(release), candidate=str(bundle), python=sys.version,
        candidate_misses_only=candidate_misses_only, targets=found,
    )


if __name__ == "__main__":
    if sys.argv[1] == "worker":
        worker(sys.argv[2], sys.argv[3], *map(Path, sys.argv[4:]))
    else:
        import argparse

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("release", type=Path)
        parser.add_argument("bundle", type=Path)
        parser.add_argument("receipt", type=Path)
        parser.add_argument("--repeats", type=int, default=8)
        parser.add_argument("--candidate-misses-only", action="store_true")
        args = parser.parse_args()
        if args.repeats < 2 or args.repeats % 2:
            parser.error("Use a positive even pair count")
        result = measure(args.release, args.bundle, args.repeats, args.candidate_misses_only)
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
