"""Replay the exact North raw combination on the original South containing offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
NORTH = Path("/dev/shm/leo-v3-combined-raw-north-result01")
NORTH_BINDING = "da2d6859a2d01ce852a41ba1b637fc334df9a28f523ed6583fdf313564082bed"
SOUTH = Path("/dev/shm/leo-v3-south-cfo-route-02")
SOUTH_RESULT = "cee62c62dddca08dc2e256791c28febd76da38d27a300e36c07e34a836a0c25f"
DIAGNOSTIC_CHANGES = {"combined-raw-protocol.md", "combined-raw.md", "combined_raw_trial.py",
                      "continued_cfo_north_trial.py", "guarded_cfo_small_raw.py", "north_orbit_index_trial.py"}


def bindings(root, request):
    from anchored_cfo_raw import verified_pack
    from combined_raw_trial import checked_producer
    from empty_bootstrap import checked
    from leo.operations.tle_archive import TleArchiveReader
    from north_orbit_index_trial import snapshot_census

    north = json.loads(checked(NORTH / "binding.json", NORTH_BINDING))
    command = list(north["command"])
    entry = Path(command[5])
    checkout = entry.parents[3]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    old, head = north["commit"], subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).splitlines()
    drift = subprocess.check_output([*git, "diff", "--name-only", old, head, "--", "src", "tools", "reports/ALGO08/v3"],
                                    text=True).splitlines()
    if dirty or any(Path(name).name not in DIAGNOSTIC_CHANGES and "/measurements/" not in name for name in drift):
        raise ValueError("Executing runtime sources changed after the North replay")
    for name, pin in north["source_sha256"].items():
        data = subprocess.check_output([*git, "show", f"{old}:reports/ALGO08/v3/{name}"])
        if sha256(data).hexdigest() != pin:
            raise ValueError(f"Acquired North source pin differs: {name}")
        if name not in DIAGNOSTIC_CHANGES:
            checked(entry.parent / name, pin)
    proof = json.loads((NORTH / "containing/unified-short-bootstrap.json").read_bytes())
    continued_pin = proof["receiver_recipe"]["continued_cfo"]["wrapper_sha256"]
    checked(entry.parent / "continued_cfo.py", continued_pin)
    for flag, library in north["libraries"].items():
        if command[command.index(flag) + 1] != library["path"]:
            raise ValueError("The sealed North command differs from its native pin")
        checked(Path(library["path"]), library["sha256"])
    pack = Path(command[command.index("--anchored-cfo-pack") + 1])
    checked(pack / "pack.json", north["pack_sha256"])
    verified_pack(pack)
    if command[command.index("--archive") + 1] != request["archive"]["root"] or request["archive"] != north["request"]["archive"]:
        raise ValueError("The original signed simulation archives differ")
    archive = TleArchiveReader(Path(request["archive"]["root"]))
    census = snapshot_census(archive.list_snapshots("space-track"), request["cutoff_utc_ns"])
    producer = checked_producer(request["cutoff_utc_ns"], census["72"]["body_digests"])
    if not producer["overlapping_bodies"]:
        raise ValueError("The earlier causal producer cannot transfer any source bodies to South")
    for flag, val in (("--recording", request["recording"]), ("--region", request["offers"]["containing"]),
                      ("--output", str(root / "containing"))):
        command[command.index(flag) + 1] = val
    return dict(command=command, request=request, north_binding_sha256=NORTH_BINDING, original_commit=old,
                execution_checkout_commit=head, changed_launch_and_score_sources=drift, producer=producer, archive_census=census,
                continuation_source_sha256=continued_pin, libraries=north["libraries"], pack_sha256=north["pack_sha256"],
                runtime_source_sha256=north["source_sha256"], protocol_sha256=sha256((HERE / "combined-raw-south-protocol.md").read_bytes()).hexdigest())


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure
    from south_cfo_route import admissible, assigned, residency

    machine = host()
    request, chunks = assigned()
    filesystems = (root.parent, Path(request["recording"]), Path(request["archive"]["root"]), Path(request["offers"]["containing"]))
    if any(subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", path], text=True).strip() != "tmpfs" for path in filesystems):
        raise ValueError("Original South inputs and output must be on verified tmpfs")
    binding = bindings(root, request)
    root.mkdir()
    for name in ("fonts", "tmp"):
        (root / name).mkdir()
    write(root / "binding.json", dict(binding, machine=machine))
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    subprocess.run([RELEASE / "venv/bin/python", "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=25)
    before = residency(chunks)
    write(root / "cache-before.json", before)
    if not admissible(before):
        write(root / "admission.json", dict(raw_admissible=False, cache=before, warmed_pages=0, raw_launches=0))
        return
    clock = measure(binding["command"], env, root / "containing")
    write(root / "clock.json", clock)
    write(root / "cache-after.json", residency(chunks))
    score(root)


def score(root):
    from aperture_trial import read, write
    from empty_bootstrap import bind_native, checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from south_cfo_route import admissible
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km

    binding, clock = (read(root / (name + ".json")) for name in ("binding", "clock"))
    request = binding["request"]
    before, after = (read(root / f"cache-{state}.json") for state in ("before", "after"))
    if clock["exit_code"]:
        write(root / "result.json", dict(completed=False, clock=clock, before=before, after=after, binding=binding))
        return
    old = json.loads(checked(SOUTH / "result.json", SOUTH_RESULT))
    target = root / "containing"
    raw, research = (read(target / name) for name in ("unified-short-bootstrap.json", "joint-research-receipt.json"))
    receipt = raw["receipt"]
    native = json.loads(checked(native_file(target), raw["native_sha256"][7:]))
    previous = json.loads(checked(Path(old["seal"]["packet"]), old["seal"]["native_sha256"][7:]))
    bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=raw["native_sha256"])
    if (raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"] or raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or raw["receiver_recipe"]["continued_cfo"]["wrapper_sha256"] != binding["continuation_source_sha256"]):
        raise ValueError("Live South acquisition does not bind the original input or executable receiver")
    archived = old["cases"]["containing"]
    one = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    earlier = evidence(SOUTH / "containing", archived["receipt"], archived["clock"]["started_unix_ns"], read_only=True)
    media = artifacts(target, receipt)
    old_research = read(SOUTH / "containing/joint-research-receipt.json")
    current = dict(probes=canonical_digest(native["source"]["probes"]), terminal=receipt["terminal_sha256"],
                   science=one["scientific_digests"], arms=one["arms"], owners=one["owners"],
                   ordered_roles_sha256=canonical_digest(research["selected_rows"]),
                   proof=[row["result"] for row in research["early_regional"]], figures=media["images"])
    position = FastStandardAnalysisStore(target)
    grid = position.position_grid(receipt["run_id"])
    path = position.position_path(receipt["run_id"])
    if grid is not None and path is not None:
        current["position_bindings_valid"] = all(doc["binding"]["position_png_sha256"] == media["images"]["position"]["sha256"]
                                                 for doc in (grid, path))
        current["grid_points"] = grid["evaluated_points"]
        current["grid_complete"] = grid["matched_c_grid"] and grid["complete"] and grid["evaluated_points"] == grid["planned_points"]
    orbit, rank = (read(root / name) for name in ("orbits-indexed.json", "catalogue-block-rank.json"))
    transfers = orbit.get("transfers", [])
    checks = dict(cache_matched=admissible(before) and admissible(after),
                  offer_inventory=receipt["region"] == archived["receipt"]["region"] and receipt["window_count"] == request["issued"],
                  probes=native["source"]["probes"] == previous["source"]["probes"],
                  arms=one["arms"] == earlier["arms"], owners=one["owners"] == earlier["owners"],
                  ordered_roles=research["selected_rows"] == old_research["selected_rows"],
                  regional=current["proof"] == archived["early"] and research["route_details"].get("exterior") == archived["exterior"],
                  path_grid=one["scientific_digests"] == earlier["scientific_digests"] and current.get("position_bindings_valid", False)
                  and current.get("grid_complete", False) and current.get("grid_points") == archived["sidecars"]["grid_points"],
                  figures=len(current["figures"]) == 8 and canonical_digest(current["figures"]) == canonical_digest(archived["media"]["images"]),
                  portable=len(transfers) == 1 and not transfers[0]["compatibility"]["fallback"]
                  and not transfers[0]["loading"]["fallback"] and not transfers[0]["counts"]["invalid_bodies"]
                  and transfers[0]["counts"]["sidecar_hit_bodies"] == binding["producer"]["overlapping_bodies"],
                  block_rank=rank["requested"] and rank["status"] == "compacted")
    errors = {arm: distance_km(old["truth"], row["latlon"]) for arm, row in one["arms"].items()}
    write(root / "result.json", dict(completed=True, checks=checks, clock=clock, old_clock=archived["clock"],
          historical_named=archived["named_historical"], old_quality=archived["arms"], named_quality=archived["named"],
          old_terminal_sha256=archived["receipt"]["terminal_sha256"], new_native_sha256=raw["native_sha256"],
          old_native_sha256=old["seal"]["native_sha256"], phases=raw["phases"], old_phases=old["raw"]["phases"],
          solve=research["solve"], diagnostic=research["route_details"].get("reason"), current=current, error_km=errors,
          before=before, after=after, binding=binding, orbit=orbit, rank=rank,
          reference_sha256=SOUTH_RESULT, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    (run if args.mode == "run" else score)(args.root)
