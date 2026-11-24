"""One held saved-input adaptive publication against the immutable named-v3 control."""

import argparse
from collections import Counter
from hashlib import file_digest
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STAGED = Path("/dev/shm/leo-v3-saved-0160-pair-01")
RESULT_NAME = "held-adaptive-worker.json"
PINS = {
    "request.json": "c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e",
    "stock-clock.json": "6462606e312e928aff3e4a175ccc580b16bd43a80a57f1628b88cf4ce844d9fa",
    "stock/saved-0160-worker.json": "8e08a9af8f911a2b212be56249e07b0d78db471a14f8f295424d0aaa1ccefae5",
    "stock/joint-research-receipt.json": "ebf1a80ae206a9c32cae2374e49b050faa1d0087413b313a3189a541d7e4ed08",
}
SOURCE_FILES = (
    Path(__file__).name, "held-adaptive-0160-protocol.md", "unified_short_bootstrap.py", "empty_bootstrap.py",
    "joint_publication.py", "prospective_0316_solver.py", "combined_raw_research.py", "north_orbit_index_raw.py",
    "historical_orbit_index.py", "portable_orbit_index.py", "portable_orbit_compatibility.py",
    "catalogue_block_port.py", "duplicate_graph_proposals.py", "exact_graph_execution.py",
    "grid_feature_projection.c", "grid_feature_projection.py", "named_survivor_fit.py", "one_pass_web_png.py",
    "direct_orbit_figures.py", "direct_residual_figures.py", "live_adaptive_grid.py", "live_adaptive_grid_entry.py",
)
FLAGS = dict(named_survivor_finish=True, reuse_verified_png_reads=True, direct_orbit_figures=True,
             direct_residual_figures=True, one_pass_web_png=True, exact_graph_reuse=True)
ARMS = ("c0", "fitted_c")
sys.path[:0] = [str(HERE), str(ROOT)]


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def resident_path(path):
    """Refuse indirect links and files outside the private tmpfs device."""
    tmpfs = Path("/dev/shm")
    if (not path.is_relative_to(tmpfs) or path.resolve(strict=True) != path
            or path.stat().st_dev != tmpfs.stat().st_dev):
        raise ValueError(f"Expected an exact tmpfs path: {path}")
    return path


def catalogue_scope(archive, refs, cutoff, original, counts):
    elected = frozenset(refs)

    def read(reader, ref):
        if reader.root != archive or ref not in elected or ref.collected_utc_ns >= cutoff:
            raise ValueError("Attempted access outside the signed local causal catalogue")
        resident_path(ref.path)
        raw = original(reader, ref)
        counts[ref.path.name] += len(raw)
        return raw

    return read


def catalogue(request):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    local = request["local_archive"]
    archive = resident_path(Path(local["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != local["snapshots"] or sum(ref.byte_size for ref in refs) != local["bytes"]
            or canonical_digest({ref.path.name: ref.sha256 for ref in refs}) != request["original_archive"]["snapshots_sha256"]
            or any(ref.collected_utc_ns >= request["causal_cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The staged catalogue does not bind the original signed causal inventory")
    for ref in refs:
        resident_path(ref.path)
    return archive, refs


def binding():
    from aperture_trial import read
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA
    from exact_solver_0008 import GRID_SOURCE_PINS
    from grid_feature_projection import LIBRARY_SHA
    from prospective_0160_solver import CASE, DETECTOR, NATIVE_SHA, PAIR_SHA
    from prospective_0316_solver import LIBRARIES

    for name, expected in PINS.items():
        if digest(resident_path(STAGED/name)) != expected:
            raise ValueError(f"The sealed saved replay changed: {name}")
    request = read(STAGED/"request.json")
    old = read(STAGED/"stock/saved-0160-worker.json")
    receipt = old["receipt"]
    inventory = resident_path(STAGED/"stock/fast-scan-inputs"/f"{request['session']}.json")
    paths = {"inventory": (inventory, request["inventory"][7:]),
             "native": (Path(request["native_file"]), NATIVE_SHA),
             "offer": (Path(request["offer_file"]), request["offer_sha256"]),
             "producer": (ARTIFACT.parent/"artifact-bind.json", PRODUCER_SHA), "artifact": (ARTIFACT, ARTIFACT_SHA[7:]),
             "grid_projection": (Path("/dev/shm/leo-cumulative-grid-projection-01/projection.so"), LIBRARY_SHA),
             **{k: (Path(v), LIBRARIES[k][1]) for k, v in request["local_libraries"].items()}}
    if (request["case"] != CASE or request["original_pair_sha256"] != PAIR_SHA or request["native_sha256"] != NATIVE_SHA
            or old["mode"] != "stock" or not old["no_waveform"] or old["handoffs"] != 1 or old["detector"] != DETECTOR
            or old["native_sha256"] != NATIVE_SHA or receipt["session_id"] != request["session"]):
        raise ValueError("Expected the original signed native packet and its installed-v3 saved replay")
    for kind, (path, pin) in paths.items():
        if digest(resident_path(path)) != pin:
            raise ValueError(f"Saved {kind} changed at {path}")
    producer = read(paths["producer"][0])
    if producer["source"]["cutoff_utc_ns"] >= request["causal_cutoff_utc_ns"] or producer["portable_sha256"] != ARTIFACT_SHA:
        raise ValueError("The selected portable producer must predate this session")
    sources = {name: digest(HERE/name) for name in SOURCE_FILES}
    if any(sources[k] != v for k, v in GRID_SOURCE_PINS.items()):
        raise ValueError("Native grid projection source is absent or changed")
    return dict(request=str(STAGED/"request.json"), paths={k: [str(p), pin] for k, (p, pin) in paths.items()},
                stock_exit=PINS["stock-clock.json"], expected_earlier_cutoff=producer["source"]["cutoff_utc_ns"],
                source_sha256=sources, publication_flags=FLAGS)


def worker(root):
    import unified_short_bootstrap as entry
    from aperture_trial import read, write
    from combined_raw_research import Portable, combined_runtime, rank_status
    from duplicate_graph_proposals import stable_finalization
    from prospective_0160_solver import SETTINGS
    from prospective_0316_solver import worker as saved_worker

    frozen = read(root/"binding.json")["input"]
    if frozen != binding():
        raise ValueError("Frozen saved adaptive paths, pins or options changed")
    job = Path(frozen["request"])
    request = read(job)
    archive_counts, duplicate = Counter(), Counter()
    orbit, rank, publication, png = {"requested": "portable"}, {"requested": True}, {}, {}
    output = root/"candidate"
    index_path, index_hash = frozen["paths"]["artifact"]
    portable = Portable(Path(index_path), "sha256:"+index_hash, frozen["paths"]["producer"][1])
    active = entry.publish_active

    def publish(opts, *args, **kwargs):
        from leo.operations.tle_archive import TleArchiveReader
        from reports.ALGO08.v3.live_adaptive_grid_entry import research_layout

        archive, refs = catalogue(request)
        guarded = catalogue_scope(archive, refs, request["causal_cutoff_utc_ns"], TleArchiveReader.read, archive_counts)
        opts.__dict__.update(FLAGS, grid_feature_projection_library=Path(frozen["paths"]["grid_projection"][0]))
        with (patch.object(TleArchiveReader, "read", guarded), stable_finalization(duplicate), research_layout(output)):
            receipt, result = active(opts, *args, png_read_audit=png, **kwargs)
        publication.update({k: result[k] for k in ("named_survivor_finish", "grid_feature_projection")})
        return receipt, result

    with combined_runtime(orbit, rank, portable, use_blocks=True), patch.object(entry, "publish_active", publish):
        saved_worker(job, "cumulative", output, source_pins=frozen["source_sha256"],
                     inventory_file=Path(frozen["paths"]["inventory"][0]), **(SETTINGS | {"audit_name": RESULT_NAME}))
    write(output/"activation.json", dict(orbit=orbit, rank=rank, rank_status=rank_status(True, rank),
          duplicate=dict(duplicate), publication=publication, png=png, causal_bytes_by_snapshot=dict(archive_counts)))


def launch(root):
    from aperture_trial import RELEASE, read, write

    sys.path.extend((str(ROOT/"src"), str(RELEASE/"src")))
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    if resident_path(root.parent) != Path("/dev/shm") or root.exists():
        raise ValueError("A fresh private tmpfs result is required")
    machine = host()
    frozen = binding()
    request = read(Path(frozen["request"]))
    _, refs = catalogue(request)
    residency = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(ref.path for ref in refs)], text=True))["fincore"]
    if len(residency) != len(refs) or any(row["res"] < row["size"] for row in residency):
        raise ValueError("Causal catalogue view must already be fully resident")
    root.mkdir(mode=0o700)
    (root/"fonts").mkdir()
    (root/"tmp").mkdir()
    for font in (STAGED/"fonts").glob("fontlist-*.json"):
        os.link(resident_path(font), root/"fonts"/font.name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "65s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", root]
    write(root/"binding.json", dict(input=frozen, machine=machine, command=list(map(str, command)),
          local_catalogue_bytes=sum(row["size"] for row in residency), fully_resident=len(refs), copied_bytes=0))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"candidate-clock.json", measure(command, env, root/"candidate"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker}[args.action](args.root)
