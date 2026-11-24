"""Evaluate the original active combined solver on the sealed dense 8/12 ms hybrid."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / "dense-hybrid-combined-protocol.md"
HYBRID = Path("/dev/shm/leo-dense-8ms-prefix-fit01")
HYBRID_PIN = "6e3a7dd4da79b20b2b30412d08bf857e6677ce43ab35441cbde7964acd9a3157"
HYBRID_ROW_PIN = "f70566671491da7eb1b5b572e60ffd5eb5ab65c398757de9e1e40137d2784c95"
HYBRID_REQUEST_PIN = "4c74d02b61a428ef87ffbaba45b950188b7fd2e33f0dae9e5eda64d5b3e8a30f"
PLAN_PIN = "f27a310ca77245d0d310ca80a63ff118ab87750e819c7adbe94cef6be89ec003"
NORTH_PIN = "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d"
NAMED_PIN = "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38"
RAW_BUDGET_PIN = "72963a8b89ceeb265410b37ffa71d0f79778f784dd7db35bcd1ce88b91c4d985"
PRODUCER_CLOCK_PIN = "ea78ecc07d20b61b5f3473d08f849efe178df093c53c095fa9a7a0d6152993f2"
PRODUCER_RUN_PIN = "8a0e2b6e02ad429e00d86aaf33da090d78f5012bfdd16d8cf20a19e15ee71249"
SOURCE_FILES = (Path(__file__).name, PROTOCOL.name, "combined_raw_research.py", "unified_short_bootstrap.py",
                "historical_orbit_index.py", "catalogue_block_port.py", "grid_feature_projection.c", "grid_feature_projection.py",
                "raw_cfo_north_trial.py", "direct_orbit_figures.py", "direct_residual_figures.py", "named_survivor_fit.py")
ARMS = ("c0", "fitted_c")


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def data(path, expected):
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != expected:
        raise ValueError(f"Original frozen input changed at {path}")
    return json.loads(gzip.decompress(payload) if path.suffix == ".gz" else payload)


def compatible_producer(source, request, causal_bodies):
    return (source["archive"] == request["archive"]["snapshots_sha256"] and source["authority"] == request["authority"]
            and source["cutoff_utc_ns"] == request["cutoff_utc_ns"]
            and set(source["body_digests"]) == set(causal_bodies) and bool(causal_bodies))


def budgets(saved_clock, producer, raw):
    half = 113.021 / 2
    warm = saved_clock["elapsed_s"]
    first = warm + producer["elapsed_s"]
    return dict(half_named_qualification_s=half, already_built_saved_elapsed_s=warm, first_use_serial_saved_elapsed_s=first,
                already_built_saved_cpu_s=saved_clock["cpu_s"], first_use_serial_saved_cpu_s=saved_clock["cpu_s"]+producer["cpu_s"],
                prior_acquire_cpu_s=raw["acquire_cpu_s"], prior_acquire_elapsed_s=raw["acquire_wall_s"],
                already_built_required_acquire_MBps=raw["dense_compressed_MB"]/(half-warm) if warm < half else None,
                first_use_required_acquire_MBps=raw["dense_compressed_MB"]/(half-first) if first < half else None)


def worker(job, output):
    """Consume a signed saved packet with the shared combined solver port."""
    import empty_bootstrap as staged
    from aperture_trial import read, write
    from combined_raw_research import Portable, combined_runtime, rank_status
    from raw_cfo_north_trial import ORDER, PUBLICATION_FLAGS, publish_saved

    started = process_time(), perf_counter()
    binding = read(job)
    request = binding["request"]
    if (not Path(request["packet"]).resolve(strict=True).is_relative_to(Path("/dev/shm"))
            or not output.parent.resolve(strict=True).is_relative_to(Path("/dev/shm"))):
        raise ValueError("The active worker may only use the local saved input scope")
    archive = Path(request["archive"]["root"]).resolve(strict=True)
    portable = Portable(Path(binding["portable"]["file"]), binding["portable"]["artifact"], binding["portable"]["producer"])
    orbit, rank = {"requested": "portable"}, {"requested": True}
    with combined_runtime(orbit, rank, portable, use_blocks=True):
        runtime = staged.load_runtime()
        from leo.contracts.digests import canonical_digest
        from leo.operations.tle_archive import TleArchiveReader
        from leo.storage.fast_scan import FastSegmentSource
        from named_constrained_research import deny_waveform

        packet = Path(request["packet"])
        native = json.loads(staged.checked(packet, request["native"][7:]))
        detector = canonical_digest(binding["detector_recipe"])
        staged.bind_native(native, request["session"], request["inventory"], detector[7:], expected=request["native"])
        if (detector != request["detector"] or native["source"]["raw_recording_authority_digest"] != request["authority"]
                or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]):
            raise ValueError("The exact original hybrid and raw authority differ")
        raw = dict(detector_recipe_sha256=detector, native_sha256=request["native"])
        offers = dict(request, offer_sha256={ORDER[1]: request["offer_sha256"]}, libraries=binding["libraries"])
        ordinary_read = TleArchiveReader.read

        def local_reader(reader, snapshot):
            if reader.root.resolve(strict=True) != archive or not snapshot.path.resolve(strict=True).is_relative_to(archive):
                raise ValueError("Request may only access its original staged causal body")
            return ordinary_read(reader, snapshot)

        with patch.object(FastSegmentSource, "windows", deny_waveform), patch.object(TleArchiveReader, "read", local_reader):
            publish_saved(offers, output, Path(request["region"]), packet, native, raw, started=started, runtime=runtime,
                          receipt_name="dense-hybrid-combined-worker.json", flags=PUBLICATION_FLAGS)
    write(output / "combined-activation.json", dict(orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


def launch(root):
    from aperture_trial import RELEASE, archive_identity, write
    from combined_raw_trial import PRODUCER
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from leo.operations.tle_archive import TleArchiveReader
    from raw_cfo_north_trial import CURVATURE_FLAGS, PUBLICATION_FLAGS
    from short_raw_diagnostic import measure

    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    admission_start = process_time(), perf_counter()
    request = data(HYBRID / "binding.json", HYBRID_REQUEST_PIN)
    old = data(HYBRID / "result.json", HYBRID_PIN)
    trace = data(HYBRID / "candidate/joint-research-receipt.json", HYBRID_ROW_PIN)
    plan = data(Path(request["plan"]) / "plan.json", PLAN_PIN)
    if (old["request"] != request or old["decision"] != "complete" or old["sidecars"]["grid_points"] != 179
            or old["worker"]["named_survivor_finish"] is not None or trace["route_details"].get("named_survivor_fit") is not None
            or plan["native_sha256"] != request["native"] or plan["detector_sha256"] != request["detector"]):
        raise ValueError("Require the exact original complete explicit-layout hybrid control")
    archive = Path(request["archive"]["root"])
    if not archive.resolve(strict=True).is_relative_to(Path("/dev/shm")) or archive_identity(archive)["snapshots_sha256"] != request["archive"]["snapshots_sha256"]:
        raise ValueError("The original tmpfs causal archive changed")
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    files = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE", *(ref.path for ref in refs)]))
    if len(refs) != 47 or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs) or any(x["res"] < x["size"] for x in files["fincore"]):
        raise ValueError("Use only the intact local causal archive")
    checked(PRODUCER.file, PRODUCER.sha256[7:])
    producer = data(PRODUCER.file.parent / "artifact-bind.json", PRODUCER.producer_sha256)
    if not compatible_producer(producer["source"], request, [ref.sha256 for ref in refs]):
        raise ValueError("The same-cutoff producer must bind the exact original separately authenticated causal content")
    generator = data(PRODUCER.file.parent / "dense-export-clock.json", PRODUCER_CLOCK_PIN)
    prep = data(PRODUCER.file.parent / "dense-export.json", PRODUCER_RUN_PIN)
    if generator["exit_code"] or producer["portable_sha256"] != PRODUCER.sha256 or prep["export"]["sha256"] != PRODUCER.sha256:
        raise ValueError("The producer timing did not build the exact artifact used by this request")
    north = data(HERE / "measurements/eight-ms-native-live.json.gz", NORTH_PIN)
    positive = north["raw_binding"]["command"]
    shared_flags = (*CURVATURE_FLAGS, *PUBLICATION_FLAGS, "--catalogue-block-rank")
    if set(shared_flags) - set(positive):
        raise ValueError("The saved active options differ from the original native 8 ms positive route")
    libraries = dict(request["libraries"], grid_feature_projection_library=request["projection"])
    for label, location in libraries.items():
        flag = "--"+label.replace("_", "-")
        checked(Path(location), north["raw_binding"]["libraries"][flag]["sha256"])
    for field, digest in (("region", request["offer_sha256"]), ("saved_inventory", request["inventory"][7:]), ("packet", request["native"][7:])):
        checked(Path(request[field]), digest)
    machine = host()
    root.mkdir()
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    for path in (HYBRID / "fonts").glob("fontlist-*.json"):
        (root / "fonts" / path.name).hardlink_to(path)
    job, output = root / "binding.json", root / "candidate"
    command = [RELEASE / "venv/bin/python", "-IB", Path(__file__), "worker", job, output]
    write(job, dict(request=request, detector_recipe=plan["detector_recipe"], machine=machine,
                    archive_pages=sum(row["pages"] for row in files["fincore"]), libraries=libraries, flags=shared_flags,
                    command=list(map(str, command)), portable=dict(file=str(PRODUCER.file), artifact=PRODUCER.sha256,
                    producer=PRODUCER.producer_sha256, source=producer["source"], generator=generator,
                    generator_export=prep["export"], generator_scoped=prep["scoped_total"], generator_run_sha256=PRODUCER_RUN_PIN),
                    prior_hybrid_sha256=HYBRID_PIN, north_control_sha256=NORTH_PIN,
                    source_sha256={name: pin(HERE / name) for name in SOURCE_FILES},
                    outer_admission=dict(cpu_s=process_time()-admission_start[0], elapsed_s=perf_counter()-admission_start[1])))
    clock = measure(command, environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}, output)
    write(root / "clock.json", clock)


def verify(root):
    from aperture_trial import read, write
    from causal_pre_refit_0155 import compare_grid
    from cumulative_grid_projection import proof_fields
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from mixed_named_finish_0008 import sidecars
    from prospective_0316_solver import owner_delta
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from triage_bounds import calibration_comparison

    job, clock = (read(root / n) for n in ("binding.json", "clock.json"))
    if clock["exit_code"]:
        write(root / "result.json", dict(clock=clock, state="process_failed", binding_sha256=pin(root / "binding.json")))
        return
    target = root / "candidate"
    worker, activation = (read(target / n) for n in ("dense-hybrid-combined-worker.json", "combined-activation.json"))
    request, prior = job["request"], data(HYBRID / "result.json", HYBRID_PIN)
    receipt = worker["receipt"]
    seen = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    media = artifacts(target, receipt)
    if (not worker["staged_inventory"] or worker["handoffs"] != 1 or worker["waveform_calls"]
            or pin(native_file(target)) != request["native"][7:] or seen["raw_authority"] != request["authority"]
            or receipt["region"] != prior["science"]["receipt"]["region"] or receipt["counts"] != prior["science"]["receipt"]["counts"]):
        raise ValueError("The measured process changed the saved input or exact operator offer")
    named = data(HERE / "measurements/dense-full-short-raw.json.gz", NAMED_PIN)["baseline"]
    if named["authority"] != seen["raw_authority"] or named["receipt"]["region"] != receipt["region"]:
        raise ValueError("The independently acquired named comparator differs in original recording or offer")
    score = calibration_comparison(dict(candidate=seen, prior=prior["science"], named=named), "DS30-0008")
    raw = data(HERE / "measurements/dense-measured-budget.json", RAW_BUDGET_PIN)
    checks = dict(clock=clock, state=receipt["decision"], science=seen, media=media, worker=worker, activation=activation,
                  scope=budgets(clock, job["portable"]["generator"], raw), geography=score, binding_sha256=pin(root / "binding.json"))
    if receipt["decision"] == "complete":
        trace = read(target / "joint-research-receipt.json")
        previous = data(HYBRID / "candidate/joint-research-receipt.json", HYBRID_ROW_PIN)
        (regional,) = trace["early_regional"]
        grid, paths = sidecars(FastStandardAnalysisStore(target), receipt["run_id"], media["images"])
        old_grid = FastStandardAnalysisStore(HYBRID / "candidate").position_grid(previous["receipt"]["run_id"])
        if job["request"]["native"] != previous["saved_digest"] and pin(native_file(HYBRID / "candidate")) != job["request"]["native"][7:]:
            raise ValueError("The prior full-layout comparator must be the exact hybrid")
        (transfer,) = activation["orbit"]["transfers"]
        direct = worker["layout"]["work"]
        png = worker["png"]
        active = dict(portable=not transfer["compatibility"]["fallback"] and not transfer["loading"]["fallback"]
                      and transfer["counts"]["sidecar_hit_bodies"] > 0 and not transfer["counts"]["invalid_bodies"],
                      compact=activation["rank_status"] == "compacted", named_finish=worker["named_survivor_finish"],
                      cairo=direct.get("native_orbit_figures")==4 and direct.get("native_residual_figures")==2 and not any(
                          direct.get(name) for name in ("native_orbit_fallback", "native_residual_fallback", "layout_fallback")),
                      verified_png=png.get("verified")==8 and png.get("reused")==8 and not png.get("fallbacks"))
        checks.update(active=active, regional=proof_fields(regional), path_grid=paths, grid_comparison=compare_grid(old_grid, grid),
            output_parity={field: seen[field]==prior["science"][field] for field in ("arms", "owners", "scientific_digests")},
            images_parity={name: canonical_digest(item)==canonical_digest(prior["figures"][name])
                           for name,item in media["images"].items()},
            ordered_owners=trace["selected_rows"],
            owners={arm: owner_delta(previous["selected_rows"][arm], trace["selected_rows"][arm]) for arm in ARMS},
            route=trace["route_details"], prior_clock=prior["clock"], prior_layout=prior["worker"]["layout"],
            named_clock=named["clocks"], original_same_packet=True)
    write(root / "result.json", checks)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_subparsers(dest="action", required=True)
    for action in ("launch", "verify"):
        mode.add_parser(action).add_argument("root", type=Path)
    child = mode.add_parser("worker")
    child.add_argument("job", type=Path)
    child.add_argument("output", type=Path)
    args = vars(cli.parse_args())
    {"launch": launch, "verify": verify, "worker": worker}[args.pop("action")](**args)
