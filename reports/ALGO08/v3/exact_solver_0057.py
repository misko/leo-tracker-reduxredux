"""Run the three reviewed solver options on the existing signed 0057 publication."""

import argparse
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PRIOR = Path("/dev/shm/leo-cumulative-forecast.PcphGbhH/run")
REQUEST_SHA = "2a53c844add2d7aebba2521c1762fd8acb07655a436241607fa5579faefa0944"
CONTROL_SHA = "61b75640af7342370116be601e2d7e923b292468b46f16b64983fc734dcb121d"
CONTROL_SCIENCE_SHA = "6fba696eb2e8d7b18b19edd62a10331e8f853e8360de36f5bc0b527047874bd2"
STAGED = tuple(Path("/dev/shm") / name / "tle/archive/space-track" for name in (
    "leo-v3-raw-cfo-0016-result03", "leo-v3-short-raw-0180-01"))
ARTIFACT = Path("/dev/shm/leo-v3-portable-orbit-prep-02/dense-orbits.bin")
ARTIFACT_SHA = "sha256:fc51655ff19185cc382aeed925e466cea7290453256d45f80446aceef6f9e30e"
PRODUCER_SHA = "c1c2f5d911c978ad7673a2a53f05e272806f87c539f2f0a552b7e02916fe9c8b"
PRODUCER_OUTPUT_SHA = "be404261457e6938511dc6268d7f2f0da562ea0dc6ee728ab845604e9416d214"


def archive_plan(snapshots, roots, device):
    plan = {}
    for ref in snapshots:
        for directory in roots:
            source = directory / ref.path.name
            try:
                info = source.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISREG(info.st_mode) and info.st_size == ref.byte_size
                    and info.st_dev == device and source.resolve(strict=True) == source):
                plan[ref.path.name] = source
                break
        else:
            raise ValueError(f"No existing exact tmpfs snapshot {ref.path.name}")
    return plan


def archive_view(root, request):
    from aperture_trial import archive_identity
    from leo.operations.tle_archive import TleArchiveReader

    origin = Path(request["archive"]["root"])
    snapshots = TleArchiveReader(origin).list_snapshots("space-track")
    if (archive_identity(origin) != request["archive"] or len(snapshots) != 49
            or any(ref.collected_utc_ns >= request["clock_cutoff_utc_ns"] for ref in snapshots)):
        raise ValueError("Original sealed DS30-0057 causal archive changed")
    target = root / "tle-view"
    directory = target / "archive/space-track"
    directory.mkdir(parents=True)
    planned = archive_plan(snapshots, STAGED, directory.stat().st_dev)
    residency = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE", *planned.values()], text=True))["fincore"]
    if len(residency) != len(planned) or any(row["res"] < row["size"] for row in residency):
        raise ValueError("The exact private archive is no longer fully resident")
    for name, path in planned.items():
        os.link(path, directory/name, follow_symlinks=False)
    actual = archive_identity(target)
    if actual["snapshots_sha256"] != request["archive"]["snapshots_sha256"]:
        raise ValueError("The local catalogue view changed the authenticated inventory")
    return actual, dict(paths={name: str(path) for name, path in planned.items()},
                        resident_pages=sum(row["pages"] for row in residency),
                        catalogue_bytes=sum(ref.byte_size for ref in snapshots), copied_catalogue_bytes=0)


def portable_preparation(ordinary, audit):
    from leo.operations.tle_archive import TleArchiveReader
    from historical_orbit_index import guarded_preparation
    from portable_orbit_index import PortableSourceIndex, load_index
    from portable_orbit_index_trial import begin, bound_versions, observed, timing
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed

    def prepare(document, reader, config, **options):
        if audit:
            raise ValueError("Expected one active preparation call")
        start = begin()
        versions = bound_versions(ARTIFACT.parent/"artifact-bind.json", PRODUCER_SHA, ARTIFACT_SHA)
        artifact, loading = load_index(ARTIFACT, ARTIFACT_SHA, versions)
        if artifact is None:
            raise ValueError("The previously sealed portable artifact was refused: " + loading["fallback"])
        index = PortableSourceIndex(artifact)
        audit.update(loading=loading, index_sha256=ARTIFACT_SHA, artifact_bodies=len(artifact.bodies))
        portable = guarded_preparation(ordinary, audit, index_factory=lambda: index)
        verify, parse = {}, {}
        with (patch.object(TleArchiveReader, "read", observed(TleArchiveReader.read, verify)),
              patch.object(installed, "parse_element_set_records", observed(installed.parse_element_set_records, parse))):
            prepared = portable(document, reader, config, **options)
        audit.update(preparation=timing(start), hits=index.counts, index_bytes=index.size(),
                     verified_reads=verify, strict_parse=parse)
        return prepared

    return prepare


def worker(binding, output):
    import cumulative_phase_forecast_trial as baseline
    import unified_short_bootstrap as unified
    from aperture_trial import write

    ordinary = unified.publish_active
    audit, ranks, duplicates, grouped = {}, [], Counter(), {}

    def optimized(*args, **kwargs):
        from active_preparation_trial import bind_preparation
        from catalogue_block_port import use_catalogue_blocks
        from catalogue_block_portable_0316 import inclusive_rank, verified_port
        from duplicate_graph_proposals import stable_finalization

        verified_port()
        with ExitStack() as stack:
            stack.enter_context(stable_finalization(duplicates))
            counted = stack.enter_context(use_catalogue_blocks())
            stack.enter_context(inclusive_rank(ranks))
            stack.enter_context(bind_preparation(portable_preparation, audit))
            result = ordinary(*args, **kwargs)
        grouped.update(counted)
        return result

    with patch.object(unified, "publish_active", optimized):
        baseline.worker(binding, "stock", output)
    write(output / "exact-options.json", dict(duplicate=dict(duplicates), grouped=grouped, ranks=ranks, portable=audit))


def verify(root):
    import cumulative_phase_forecast_trial as baseline
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from triage_bounds import calibration_comparison

    timing = read(root/"candidate-clock.json")
    if timing["exit_code"]:
        raise ValueError("The candidate must exit successfully before scoring")
    control = json.loads(checked(PRIOR/"result.json", CONTROL_SHA))["runs"]["stock"]
    initial = json.loads(checked(PRIOR/"stock-verified.json", CONTROL_SCIENCE_SHA))
    initial_science = dict(initial["science"])
    initial_products = initial_science.pop("products")
    control_products = control["persisted_sidecar_digests"] | {"images": control["science"]["images"]}
    if (initial_products != control_products or initial["process"] != control["process"]
            or initial["worker"] != control["worker"]
            or any(control["science"][key] != value for key, value in initial_science.items())):
        raise ValueError("The prior same-packet control changed")
    request = read(root/"binding.json")
    _, original, details = baseline.checked_case()
    target = root/"candidate"
    candidate = baseline.verify(target, "stock", timing, original, details, request)
    audit = read(target/"exact-options.json")
    if canonical_digest(candidate["science"]) != canonical_digest(control["science"]):
        raise ValueError("The three solver options changed the original publication")
    proof = candidate["science"]["regional"]
    if "diagnostic_error" in proof or proof["probes_evaluated"] != 25 or not proof["snapshots"]:
        raise ValueError("The original regional diagnostic did not complete its 25 probes")
    geography = calibration_comparison({"control": control["science"], "candidate": candidate["science"]}, "DS30-0057")
    write(root/"result.json", dict(control=control, candidate=candidate, geography=geography,
          options=audit, archive_view=read(root/"custody.json"), input=request,
          paired_historical_control_sha256=CONTROL_SHA, waveform_reads=0,
          source_pins={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
              "exact-solver-0057-protocol.md", "exact_solver_0057.py", "duplicate_graph_proposals.py",
              "catalogue_block_port.py", "historical_orbit_index.py", "portable_orbit_index.py")}))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Expected a fresh Gauss tmpfs path")
    request = json.loads(checked(PRIOR/"binding.json", REQUEST_SHA))
    producer = json.loads(checked(ARTIFACT.parent/"artifact-bind.json", PRODUCER_SHA))
    check = json.loads(checked(ARTIFACT.parent/"result.json", PRODUCER_OUTPUT_SHA))
    if (producer["portable_sha256"] != ARTIFACT_SHA or check["artifact_sha256"] != ARTIFACT_SHA
            or not check["same_scientific_arrays"]
            or producer["source"]["cutoff_utc_ns"] >= request["clock_cutoff_utc_ns"]):
        raise ValueError("Expected the eligible earlier signed producer")
    root.mkdir()
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for file in (PRIOR/"fonts").glob("fontlist-*.json"):
        os.link(file, root/"fonts"/file.name)
    archive, custody = archive_view(root, request)
    write(root/"custody.json", custody | dict(machine=machine, original_archive=request["archive"],
          prior_request_sha256=REQUEST_SHA, producer_sha256=PRODUCER_SHA))
    bound = root/"binding.json"
    write(bound, request | {"archive": archive})
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    timing = measure(["/usr/bin/timeout", "--kill-after=2s", "60s", RELEASE/"venv/bin/python", "-IB",
                      __file__, "worker", bound, root/"candidate"], env, root/"candidate")
    write(root/"candidate-clock.json", timing)
    if timing["exit_code"]:
        raise RuntimeError(timing["stderr_tail"])


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker", "verify"))
    parser.add_argument("path", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.path, args.output)
    else:
        {"run": launch, "verify": verify}[args.action](args.path)
