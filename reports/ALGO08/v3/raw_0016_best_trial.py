"""Run exactly one candidate-first original DS30-0016 pair."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter, process_time

from empty_bootstrap import RELEASE, checked
from short_raw_0180 import BULK, BOOTSTRAP, HERE, OPERATOR_OFFER, SHORT, STAGED, Workload, enrollment, stage_orbits


BASE = "ac8c5c59e1bbecee14f80aa150cf5d6be309ec16"
CASE = Workload("DS30-0016", BULK / "leo-dev/ds30-full-20261121/bindings/DS30-0016.json",
                "c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c",
                808, 46, 991_734_597, 1_050_000_000, ("candidate", "stock"), True)
MEMBERS = 13
ARCHIVE = "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
INVENTORY = "sha256:e22b918df63370a0590757b70f71a0e620792cf90cf78a833e601af7a0b395a6"
MIXED_NATIVE = "sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
PROJECTION = Path("/dev/shm/leo-cumulative-grid-projection-01/projection.so")
PROJECTION_SHA = "7ac9f74eb08d1992bde8738dbc8f6ec9687eb7fe4f5d5f4ae3301ddfa061d0fb"
FLAGS = ("--prove-empty-graph", "--prove-graph-time-support", "--named-survivor-finish",
         "--exact-graph-reuse", "--reuse-verified-png-reads", "--one-pass-web-png",
         "--direct-residual-figures", "--direct-orbit-figures")


@dataclass(frozen=True)
class PairInputs:
    workload: Workload
    members: int
    admitted: int
    cutoff_ns: int
    inventory: str
    archive: str


ORIGINAL = PairInputs(CASE, MEMBERS, 713, 1794568912154038024, INVENTORY, ARCHIVE)


def sha(data):
    return sha256(data).hexdigest()


def frozen_sources():
    """Verify untouched trial dependencies against the frozen parent tree."""
    names = ("unified_short_bootstrap.py", "empty_bootstrap.py", "full_short_raw.py", "full_short_run.py",
             "short_graph_guard.py", "named_survivor_fit.py", "isolated_salvage.py", "endpoint_track_repair.py",
             "provisional_salvage.py", "fragment_gate_cross.py", "exact_graph_execution.py",
             "vector_graph_edges.py", "polynomial_fit_cache.py", "verified_png_reads.py", "joint_publication.py",
             "one_pass_web_png.py", "direct_residual_entry.py", "direct_residual_figures.py",
             "direct_orbit_entry.py", "direct_orbit_figures.py", "grid_feature_projection.py",
             "grid_feature_projection.c", "short_raw_0180.py", "short_raw_diagnostic.py", "triage_bounds.py")
    repo = HERE.parents[2]
    result = {}
    for name in names:
        path = HERE / name
        reference = subprocess.check_output(["git", "-c", f"safe.directory={repo}", "-C", repo,
                                             "show", f"{BASE}:{path.relative_to(repo)}"])
        checked(path, sha(reference))
        result[name] = sha(reference)
    return result


def check_extent(cache, compressed, inputs=ORIGINAL):
    workload = inputs.workload
    if (compressed != workload.compressed_bytes or compressed > workload.raw_limit
            or cache["members"] != inputs.members or cache["observed_members"] != inputs.members or cache["unavailable"]
            or cache["observed_file_pages"] < 1):
        raise ValueError("Original signed recording differs from the allocated conditioning extent")


def command(mode, root, recording, libraries, named):
    common = ["--recording", recording, "--region", root/"offer.json", "--archive", root/"tle"]
    if mode == "stock":
        return [named, *common, "--bulk-root", root/mode]
    if mode != "candidate":
        raise ValueError("Only one current candidate and one named baseline are enrolled")
    return [RELEASE/"venv/bin/python", "-IB", BOOTSTRAP, *common, "--output", root/mode,
            "--short-binary", libraries["short"], "--geographic-library", libraries["geographic"],
            "--regional-track-library", libraries["regional"], "--frontier-block-library", libraries["block"],
            "--grid-feature-projection-library", libraries["projection"], *FLAGS]


def seal(root, order=CASE.order):
    paths = [root/"admission.json", root/"offer.json", root/"conditioning-before.json", root/"conditioning.json"]
    for mode in order:
        paths.extend(root / f"{mode}{suffix}" for suffix in ("-clock.json", ".stdout", ".stderr"))
        paths.extend(p for p in (root/mode).rglob("*") if p.is_file())
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(paths)}


def configuration(root, inputs=ORIGINAL, *, selection=None, launch_order=None):
    from aperture_trial import write
    from combined_frontier_run import BLOCK_SHA
    from dense_geographic_trial import host
    from full_short_physical import REGION_SHA, environment
    from full_short_raw import SHORT_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from leo.contracts.digests import canonical_digest
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, pairs
    from triage_bounds import ShortWindowReader

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Need fresh private tmpfs for all outputs and staging")
    sources = frozen_sources()
    named = pairs.verified_v3(pairs.NAMED_V3)
    workload = inputs.workload
    signed, request = enrollment(workload)
    case, job = signed["case"], request["job"]
    manifests = tuple((BULK/r["path"], "sha256:"+r["sha256"]) for r in case["recording"]["segments"])
    recording = manifests[0][0].parent.parent
    official = checked(OPERATOR_OFFER, REGION_SHA)
    offer = json.loads(official)
    if (offer["center"] != job["search_center"] or offer["screen_center"] != job["screen_center"]
            or signed["orbit_cutoff_ns"] != inputs.cutoff_ns or case["valid_visits"] != inputs.admitted
            or canonical_digest(request["causal_snapshots"]) != inputs.archive):
        raise ValueError("The original causal inputs or operator offer changed")

    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    (root/"offer.json").write_bytes(official)
    store = FastScanStore(root)
    session, inventory, catalogue = store.inventory(recording, verify_windows=False)
    actual_manifests = [(Path(row["path"])/"manifest.json", row["manifest_digest"]) for row in catalogue["segments"]]
    if (inventory != inputs.inventory or session != case["session_id"] or catalogue["window_count"] != workload.windows
            or manifests != tuple(actual_manifests)):
        raise ValueError("Original inventory changed")
    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)

    def residency():
        return cache_residency.bound_snapshot(store, recording, manifests, os.sysconf("SC_PAGE_SIZE"), query)

    total = sum(chunk.compressed_bytes for path, _ in manifests for chunk in ShortWindowReader(path.parent).manifest.chunks)
    check_extent(residency(), total, inputs)
    start_cpu, start_wall = process_time(), perf_counter()
    archive = stage_orbits(root/"tle", Path(job["tle_root"]), request["causal_snapshots"],
                           signed["orbit_cutoff_ns"], expected_count=workload.snapshots)
    if pairs.archive_identity(root/"tle")["snapshots_sha256"] != inputs.archive:
        raise ValueError("Staged archive changed")
    libraries = {}
    library_inputs = (("short", SHORT, SHORT_SHA), ("geographic", STAGED/"geographic_library.so", GEOGRAPHIC_SHA),
                      ("regional", STAGED/"regional_track_library.so", TRACK_SCORES_SHA),
                      ("block", STAGED/"frontier_block_library.so", BLOCK_SHA), ("projection", PROJECTION, PROJECTION_SHA))
    for name, source, digest in library_inputs:
        destination = root / f"{name}.so"
        destination.write_bytes(checked(source, digest))
        libraries[name] = destination
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    subprocess.run([RELEASE/"venv/bin/python", "-Bc",
                    "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    archive["sha256"] = inputs.archive
    order = workload.order if launch_order is None else launch_order
    admission = dict(case=workload.id, base=BASE, order=order, host=machine, stock=named,
          route_flags=FLAGS, sources=sources, driver_sha256=sha(Path(__file__).read_bytes()),
          binding=workload.binding_sha, request=case["request"]["sha256"], inventory=inputs.inventory,
          cutoff_utc_ns=signed["orbit_cutoff_ns"], manifests=cache_residency.manifest_pins(manifests),
          offer=offer, offer_sha256=REGION_SHA, issued=workload.windows, admitted=case["valid_visits"],
          archive=archive, recording=str(recording), raw_authority=case["raw_authority"], session=case["session_id"],
          library_sha256={name: pin for name, _, pin in library_inputs},
          staging=dict(wall_s=perf_counter()-start_wall, driver_cpu_s=process_time()-start_cpu),
          raw_budget_bytes=workload.raw_limit, compressed_bytes=total)
    if selection is not None:
        admission["selection"] = selection
    write(root/"admission.json", admission)
    return recording, manifests, total, libraries, residency, env


def condition(root, manifests, total, residency, inputs=ORIGINAL):
    from aperture_trial import write
    from short_raw_diagnostic import require_warm
    from triage_bounds import warm_recording

    workload = inputs.workload
    before = residency()
    check_extent(before, total, inputs)
    used = before["cached_pages"] != before["observed_file_pages"]
    write(root/"conditioning-before.json", {"cache": before, "needed": used})
    cpu, wall = process_time(), perf_counter()
    blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
    charged = warm_recording(manifests, maximum_bytes=workload.raw_limit) if used else 0
    conditioning = dict(used=used, bytes=charged, wall_s=perf_counter()-wall, cpu_s=process_time()-cpu,
                        input_blocks=resource.getrusage(resource.RUSAGE_SELF).ru_inblock-blocks)
    after = residency()
    write(root/"conditioning.json", dict(conditioning, before=before, after=after))
    if charged != (total if used else 0):
        raise ValueError("The conditioning pass changed its signed extent")
    require_warm(after)


def measure_mode(root, mode, argv, env, residency):
    from aperture_trial import write
    from short_raw_diagnostic import measure, require_warm

    target = root/mode
    if mode == "stock":
        target.mkdir()
    start_cache = residency()
    require_warm(start_cache)
    clock = measure(argv, env, target)
    end_cache = residency()
    write(root/f"{mode}-clock.json", dict(clock=clock, cache_before=start_cache, cache_after=end_cache,
                                          command=list(map(str, argv))))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    require_warm(end_cache)


def launch(root, inputs=ORIGINAL, *, selection=None):
    from aperture_trial import write
    from short_raw_diagnostic import pairs

    workload = inputs.workload
    recording, manifests, total, libraries, residency, env = configuration(root, inputs, selection=selection)
    condition(root, manifests, total, residency, inputs)
    for mode in workload.order:
        argv = command(mode, root, recording, libraries, pairs.NAMED_V3)
        measure_mode(root, mode, argv, env, residency)
    write(root/"prediction-seal.json", seal(root, workload.order))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    launch(cli.parse_args().root)
