"""Price the corrected exact solver on the genuine full dense mixed packet."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
GRID_SOURCE_PINS = {
    "grid_feature_projection.c": "bdfc20a3acd1fce79897839252ae4abb6da3bfb3ce3929ffa67ed167adb22e6a",
    "grid_feature_projection.py": "51bfc042192302eba70c6e2f77ba65a76f1b93ad35cd2130ad1c2ae783f52920",
}
RANK = Path("/dev/shm/leo-v3-catalogue-block-dense-pair01")
RANK_RECEIPT_SHA = "80918787b0ee721ea86bfc7d83a868e1d7da51749f3214e780e0116ba877a90e"
RANK_REQUEST_SHA = "4b6d07ea28051a4ac70030bd20f5da7e8f3bb8187dc84ea4b73fbbb6d04f94f5"
QUALIFICATION_ELAPSED = 113.021
PRODUCER_CUTOFFS = {"DS30-0008": 1794556783056720638, "DS30-0306": 1794992226324353171}


def raw_budget(clock, acquisition):
    target = QUALIFICATION_ELAPSED / 2
    elapsed = clock["elapsed_s"]
    room = target - elapsed
    size = acquisition["dense_compressed_MB"]
    return dict(qualification_elapsed_s=QUALIFICATION_ELAPSED, half_s=target,
                original_acquire_cpu_s=acquisition["acquire_cpu_s"],
                original_acquire_elapsed_s=acquisition["acquire_wall_s"],
                original_exposed_wait_s=acquisition["acquire_wall_s"]-acquisition["acquire_cpu_s"],
                optimistic_no_overlap_cpu_s=clock["cpu_s"]+acquisition["acquire_cpu_s"],
                historical_input_wait_sum_elapsed_s=elapsed+acquisition["acquire_wall_s"],
                remaining_acquire_elapsed_s=room, dense_compressed_MB=size,
                minimum_verified_acquisition_MBps=None if room <= 0 else size / room)


def preflight():
    from catalogue_block_portable_0316 import verified_port
    from empty_bootstrap import checked
    from leo.operations.tle_archive import TleArchiveReader
    from mixed_named_finish_0008 import assigned

    for name, pin in GRID_SOURCE_PINS.items():
        checked(HERE/name, pin)
    verified_port()
    job = assigned()
    if any(before < job["cutoff_utc_ns"] for before in PRODUCER_CUTOFFS.values()):
        raise ValueError("A previously unknown earlier artifact requires a new admission check")
    archive = Path(job["archive"]["root"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if len(refs) != 47 or not all(ref.path.resolve(strict=True).is_relative_to(Path("/dev/shm"))
                                  and ref.collected_utc_ns < job["cutoff_utc_ns"] for ref in refs):
        raise ValueError("Only the earlier staged causal snapshots are allowed")
    resident = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE", *(r.path for r in refs)], text=True))["fincore"]
    if len(resident) != len(refs) or any(file["res"] < file["size"] for file in resident):
        raise ValueError("Require all of the staged catalogue pages before the paid run")
    return job, dict(archive_resident_pages=sum(item["pages"] for item in resident),
                     archive_bytes=sum(ref.byte_size for ref in refs), archive_count=len(refs),
                     producer_cutoff_utc_ns=PRODUCER_CUTOFFS, portable_enabled=False,
                     grid_source_sha256=GRID_SOURCE_PINS)


def ordinary_preparation(ordinary, audit):
    from leo.operations.tle_archive import TleArchiveReader
    from portable_orbit_index_trial import begin, observed, timing
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed

    def prepare(document, reader, config, **options):
        if audit:
            raise ValueError("Expected exactly one active ordinary preparation")
        start = begin()
        reads, parses = {}, {}
        with (patch.object(TleArchiveReader, "read", observed(TleArchiveReader.read, reads)),
              patch.object(installed, "parse_element_set_records", observed(installed.parse_element_set_records, parses))):
            prepared = ordinary(document, reader, config, **options)
        audit.update(clock=timing(start), verified_reads=reads, strict_parse=parses, portable=False)
        return prepared

    return prepare


def worker(job, output):
    import cumulative_grid_projection as baseline
    import unified_short_bootstrap as unified
    from aperture_trial import write

    ordinary = unified.publish_active
    duplicates, rank, groups, prep = Counter(), [], {}, {}

    def use_grouped(options, *args, **kwargs):
        from active_preparation_trial import bind_preparation
        from catalogue_block_port import use_catalogue_blocks
        from catalogue_block_portable_0316 import inclusive_rank
        from duplicate_graph_proposals import stable_finalization
        from leo.operations.tle_archive import TleArchiveReader

        archive_root = options.archive.resolve(strict=True)
        original_read = TleArchiveReader.read

        def staged_read(reader, snapshot):
            if reader.root.resolve(strict=True) != archive_root or not archive_root.is_relative_to(Path("/dev/shm")):
                raise ValueError("Only the admitted resident archive is readable")
            return original_read(reader, snapshot)

        with ExitStack() as stack:
            stack.enter_context(patch.object(TleArchiveReader, "read", staged_read))
            stack.enter_context(stable_finalization(duplicates))
            grouped = stack.enter_context(use_catalogue_blocks())
            stack.enter_context(inclusive_rank(rank))
            stack.enter_context(bind_preparation(ordinary_preparation, prep))
            publication = ordinary(options, *args, **kwargs)
        groups.update(grouped)
        return publication

    with patch.object(unified, "publish_active", use_grouped):
        baseline.worker(job, "combined", output)
    write(output/"exact-options.json", dict(duplicate=dict(duplicates), group=groups, rank=rank, preparation=prep))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from mixed_named_finish_0008 import PREVIOUS
    from short_raw_diagnostic import measure

    machine = host()
    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Expected fresh tmpfs output")
    job, inspected = preflight()
    root.mkdir()
    (root/"tmp").mkdir()
    (root/"fonts").mkdir()
    for existing in (PREVIOUS/"dense-pair/fonts").glob("fontlist-*.json"):
        (root/"fonts"/existing.name).hardlink_to(existing)
    binding = root/"binding.json"
    write(binding, job | dict(preflight=inspected, machine=machine))
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    command = ["/usr/bin/timeout", "--kill-after=2s", "80s", RELEASE/"venv/bin/python", "-IB",
               __file__, "worker", binding, root/"candidate"]
    clock = measure(command, env, root/"candidate")
    write(root/"clock.json", dict(timing=clock, command=list(map(str, command))))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def verify(root):
    from aperture_trial import read, write
    from cumulative_grid_projection import proof_fields
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from mixed_named_finish_0008 import ORIGINAL_V3_PIN, PREVIOUS, PRIOR_PIN, PRIOR_ROWS_PIN, sidecars
    from publication_media_checks import verify_position_sidecars
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from triage_bounds import calibration_comparison

    launch_record = read(root/"clock.json")
    clock = launch_record["timing"]
    if clock["exit_code"]:
        raise ValueError("An unsuccessful publication cannot enter scoring")
    job, target = read(root/"binding.json"), root/"candidate"
    prior_root = PREVIOUS/"dense-pair"
    review = json.loads(checked(prior_root/"result.json", PRIOR_PIN))
    historical = review["runs"]["combined"]
    old = json.loads(checked(prior_root/"combined/joint-research-receipt.json", PRIOR_ROWS_PIN))
    worker, trace, work = (read(target/name) for name in (
        "cumulative-grid-worker.json", "joint-research-receipt.json", "exact-options.json"))
    receipt = worker["receipt"]
    fields = ("native", "session", "inventory", "authority", "offer_sha256", "cutoff_utc_ns", "issued")
    if (any(job[key] != review["inputs"][key] for key in fields)
            or job["archive"]["snapshots_sha256"] != review["inputs"]["archive"]["snapshots_sha256"]
            or receipt["region"] != historical["worker"]["receipt"]["region"]
            or receipt["terminal_sha256"] != historical["worker"]["receipt"]["terminal_sha256"]
            or receipt["counts"] != dict(processed=6765, invalid_capture=7, skipped_fast_score=0)
            or worker["waveform_calls"] or not worker["staged_inventory"] or worker["handoffs"] != 1):
        raise ValueError("The paid run changed the signed packet, offer, cutoff, archive or outcome")
    native = json.loads(checked(native_packet(target), job["native"][7:]))
    probes = native["source"]["probes"]
    if len(probes) != 13530 or sum(len(row["candidates"]) for row in probes) != 7336:
        raise ValueError("The played detector packet was thinned")
    science = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    figures = artifacts(target, receipt)["images"]
    _, media = sidecars(FastStandardAnalysisStore(target), receipt["run_id"], figures)
    (regional,) = trace["early_regional"]
    proof = proof_fields(regional)
    if (any(canonical_digest(science[key]) != canonical_digest(historical["science"][key])
            for key in ("arms", "owners", "scientific_digests", "raw_authority"))
            or trace["selected_rows"] != old["selected_rows"] or proof != historical["regional"]
            or proof["probes_evaluated"] != 25 or "diagnostic_error" in proof
            or canonical_digest(figures) != canonical_digest(historical["images"])):
        raise ValueError("The full scientific and publication witness changed")
    sidecar_match = verify_position_sidecars(prior_root/"combined", target, receipt["run_id"], historical["images"], figures)
    graph, previous_graph = (value["graph"]["graph"] for value in (worker, historical["worker"]))
    calls = worker["projection"]["calls"]
    if (not worker["graph"]["enabled"] or any(graph[k] != previous_graph[k] for k in ("calls", "edges", "tracks", "assigned"))
            or calls["native_selection"] != 356 or any(count for key, count in calls.items() if "fallback" in key)):
        raise ValueError("Expected exact Graph and native checked grid activation")
    rank_source = json.loads(checked(RANK/"request.json", RANK_REQUEST_SHA))
    rank_witness = json.loads(checked(RANK/"result.json", RANK_RECEIPT_SHA))["rank"]["paired"]
    live_rank, = work["rank"]
    group = work["group"]
    if (rank_source["inventory"] != job["inventory"] or rank_source["raw_authority"] != job["authority"]
            or rank_source["native_file"] != job["packet"] or group["admitted_ranks"] != 1
            or group["original_ranks"] or group.get("full_fallback", 0) or group["calls"] != 1792
            or group["compact_calls"] != group["calls"] or not work["duplicate"]["calls"]
            or live_rank["digest"] != rank_witness["control_digest"] or live_rank["nodes"] != 7):
        raise ValueError("The independently sealed dense rank did not reproduce exactly")
    original = json.loads(gzip.decompress(checked(HERE/"measurements/dense-full-short-raw.json.gz", ORIGINAL_V3_PIN)))
    named = original["baseline"]
    if named["authority"] != job["authority"] or named["receipt"]["region"] != receipt["region"]:
        raise ValueError("Named geographic comparator does not belong to the same original recording and offer")
    geography = calibration_comparison(dict(named=named, historical=historical["science"], candidate=science), "DS30-0008")
    budget = raw_budget(clock, read(HERE/"measurements/dense-measured-budget.json"))
    write(root/"result.json", dict(recording="DS30-0008", historical=historical, actual=worker, timing=clock,
          geography=geography, original_named=dict(owners=named["owners"], timing=named["clocks"]),
          receipt=science, ranked_owner_sha256=canonical_digest(trace["selected_rows"]), options=work,
          proof=proof, media=media, figures=figures, sidecar_match=sidecar_match, budget=budget, input=job,
          waveform_reads=0, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "launch", "worker", "verify"))
    parser.add_argument("path", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    opts = parser.parse_args()
    if opts.action == "worker":
        worker(opts.path, opts.output)
    elif opts.action == "preflight":
        print(json.dumps(preflight()[1], indent=2))
    else:
        {"launch": launch, "verify": verify}[opts.action](opts.path)
