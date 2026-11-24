"""Price saved orbit-index writing, fresh loading and publication."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
TRIALS = ("dense-ordinary", "dense-export", "weak-ordinary", "weak-cache")
EXPORT = "dense-orbits.bin"
PIN_ENV = "LEO_RESEARCH_ORBIT_INDEX_SHA256"
FILE_ENV = "LEO_RESEARCH_ORBIT_INDEX_FILE"


def timing(start):
    return dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])


def begin():
    return process_time_ns(), perf_counter_ns()


def observed(original, tally):
    def measure(*args, **kw):
        start = begin()
        try:
            return original(*args, **kw)
        finally:
            for key, value in timing(start).items():
                tally[key] = tally.get(key, 0)+value
            tally["calls"] = tally.get("calls", 0)+1
    return measure


def settings():
    from empty_bootstrap import RELEASE, checked, load_runtime
    from historical_orbit_index import TRACK_PIN, installed_guard

    _, spec, _, _, check_clocks = load_runtime()
    from leo.analysis.localization_v3.tracks import TrackConfig

    if not installed_guard() or not spec["defer_preparation_gc"]:
        raise ValueError("Expected the pinned accelerated preparation")
    native = spec["tle_parser"]
    checked(Path(native["library"]), native["sha256"])
    config = TrackConfig(**json.loads(checked(RELEASE/"assets/tracks.json", TRACK_PIN))["config"])
    return config, native, check_clocks


def worker(root, mode, pin=None):
    from historical_orbit_index import SourceIndex, case_inputs, measure
    from portable_orbit_index import PortableSourceIndex, load_index, versions, write_index

    start = begin()
    config, native, checks = settings()
    from aperture_trial import write
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed
    from tools.pipeline_eval.variants.experimental.tle_records import batch_records

    job = case_inputs("DS30-0008" if mode.startswith("dense") else "DS30-0016")
    loaded, exported, version_cost, strict, verified_reads = None, None, None, {}, {}
    with batch_records(Path(native["library"])) as validation:
        compatibility = None
        if mode in ("dense-export", "weak-cache"):
            phase = begin()
            compatibility = versions()
            version_cost = timing(phase)
        index = SourceIndex() if mode == "dense-export" else None
        if mode == "weak-cache":
            artifact, loaded = load_index(root/EXPORT, pin, compatibility)
            index = PortableSourceIndex(artifact)
        with (patch.object(TleArchiveReader, "read", observed(TleArchiveReader.read, verified_reads)),
              patch.object(installed, "parse_element_set_records", observed(installed.parse_element_set_records, strict))):
            result = measure(job, config, index)
        if mode == "dense-export":
            phase = begin()
            exported = write_index(root/EXPORT, index, compatibility) | timing(phase)
        if mode == "weak-cache":
            result["portable_counts"] = index.counts
    usage = getrusage(RUSAGE_SELF)
    write(root/f"{mode}.json", dict(case=job[3], result=result, verified_archive_reads=verified_reads,
          strict_parse=strict, native_validation=validation, checked=checks, compatibility=compatibility,
          compatibility_check=version_cost, loading=loaded, export=exported, scoped_total=timing(start),
          process_peak_rss_kib=usage.ru_maxrss, process_input_blocks=usage.ru_inblock,
          process_major_faults=usage.ru_majflt, native_record_parser_sha256=native["sha256"]))


def local_launcher_tools():
    from empty_bootstrap import load_runtime

    load_runtime()
    from tools import pipeline_eval
    from tools.pipeline_eval import qualification

    # Only the outer launcher needs local comparison tools. Verified numerics
    # stay in fresh isolated children with the installed release paths.
    local = HERE.parents[2]/"tools/pipeline_eval"
    pipeline_eval.__path__.append(str(local))
    qualification.__path__.append(str(local/"qualification"))


def prepare(root):
    local_launcher_tools()
    from aperture_trial import RELEASE, read, write
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs research output")
    root.mkdir()
    (root/"tmp").mkdir()
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    python = RELEASE/"venv/bin/python"
    observations = {}
    pin = None
    for mode in TRIALS:
        command = ["/usr/bin/timeout", "--kill-after=2s", "50s", python, "-IB", __file__, root, "--worker", mode]
        if mode == "weak-cache":
            command.extend(("--pin", pin))
        clock = measure(command, env, root/mode)
        write(root/f"{mode}-clock.json", clock)
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        result = read(root/f"{mode}.json")
        observations[mode] = dict(observation=result, exit_clock=clock)
        if mode == "dense-export":
            pin = result["export"]["sha256"]
            if pin != "sha256:"+sha256((root/EXPORT).read_bytes()).hexdigest():
                raise ValueError("Once-prepared dense array sidecar differs from its newly sealed digest")
            write(root/"artifact-bind.json", dict(portable_sha256=pin, source=result["case"],
                  implementation=result["compatibility"]))
    dense, weak = [(observations[f"{case}-{ordinary}"]["observation"], observations[f"{case}-{cache}"]["observation"])
                   for case, ordinary, cache in (("dense", "ordinary", "export"), ("weak", "ordinary", "cache"))]
    for control, candidate in (dense, weak):
        counts = candidate["native_validation"]
        if (candidate["case"] != control["case"] or candidate["result"]["science"] != control["result"]["science"]
                or counts != control["native_validation"] or counts["fallback"]
                or candidate["verified_archive_reads"]["calls"] != control["verified_archive_reads"]["calls"]):
            raise ValueError("The portable preparation changed original validation, outputs or source membership")
    if (dense[1]["case"]["cutoff_utc_ns"] >= weak[0]["case"]["cutoff_utc_ns"]
            or weak[1]["loading"]["fallback"] or not weak[1]["result"]["portable_counts"]["sidecar_hit_bodies"]
            or weak[1]["result"]["portable_counts"]["invalid_bodies"]):
        raise ValueError("Fresh weak preparation did not activate the exact pre-cutoff producer artifact")
    write(root/"result.json", dict(observations=observations, artifact_sha256=pin, same_scientific_arrays=True,
          solver_invocations=0, waveform_reads=0))


def publication_worker(root):
    from active_preparation_trial import bind_preparation
    from continued_cfo_trial import work
    import historical_orbit_index as historical
    from portable_orbit_index import PortableSourceIndex, UnsupportedExport, load_index, versions

    audit = {}

    def overlay(ordinary, receipt):
        def prepare_active(*args, **kwargs):
            path, pin = Path(os.environ[FILE_ENV]), os.environ[PIN_ENV]
            start = begin()
            try:
                compatibility = versions()
            except UnsupportedExport as error:
                receipt.setdefault("transfers", []).append(dict(file=str(path), sha256=pin,
                    loading=dict(fallback=str(error)), compatibility_clock=timing(start)))
                return ordinary(*args, **kwargs)
            check = timing(start)
            artifact, load = load_index(path, pin, compatibility)
            index = PortableSourceIndex(artifact)
            try:
                portable = historical.guarded_preparation(ordinary, receipt, index_factory=lambda: index)
                return portable(*args, **kwargs)
            finally:
                receipt.setdefault("transfers", []).append(dict(file=str(path), sha256=pin,
                    versions=compatibility, compatibility_clock=check, loading=load, counts=index.counts,
                    retained_source_bytes=index.size(), complete_preparation=timing(start)))
        return prepare_active

    with bind_preparation(overlay, audit):
        work(root)
    with (root/"orbits-indexed.json").open("x") as out:
        json.dump(audit, out, sort_keys=True, allow_nan=False)
        out.write("\n")


def publication(root, staging, pin):
    import historical_orbit_publication as ordinary

    expected = json.loads((staging/"artifact-bind.json").read_bytes())
    sealed = json.loads((staging/"result.json").read_bytes())
    if (pin != expected["portable_sha256"] or pin != sealed["artifact_sha256"]
            or not sealed["same_scientific_arrays"]
            or staging.resolve(strict=True).parent != Path("/dev/shm")):
        raise ValueError("The saved publication must use the sealed pre-cutoff producer digest")
    with patch.dict(os.environ, {FILE_ENV: str(staging/EXPORT), PIN_ENV: pin}):
        ordinary.run(root, worker_path=Path(__file__).resolve())
    audit = json.loads((root/"orbits-indexed.json").read_bytes())
    transfer, = audit["transfers"]
    if (transfer["sha256"] != pin or transfer["loading"]["fallback"]
            or transfer["counts"]["invalid_bodies"] or not transfer["counts"]["sidecar_hit_bodies"]):
        raise ValueError("The matched full publication did not use the authenticated portable index")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--prepare", action="store_true")
    cli.add_argument("--worker", action="store_true")
    cli.add_argument("--publish-from", type=Path)
    cli.add_argument("--pin")
    # historical_orbit_publication invokes this file as ROOT --worker.
    cli.add_argument("worker_mode", nargs="?", choices=TRIALS)
    args = cli.parse_intermixed_args()
    if args.prepare:
        prepare(args.root)
    elif args.worker:
        if args.worker_mode:
            worker(args.root, args.worker_mode, args.pin)
        else:
            publication_worker(args.root)
    else:
        publication(args.root, args.publish_from, args.pin)
