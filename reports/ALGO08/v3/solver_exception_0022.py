"""Qualify the current saved worker on the first archived interpolation exit."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

CASE = "DS30-0022"
PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
RECOVERED = Path("/var/tmp/leo-full-short-orbit-0022/current")
PAIR_PIN = "1984f1a54654b2ac9798599dd13a3de29506ce104650ef9237bdede5d413f0a4"
NATIVE_PIN = "c986ebd360dad025dacbd36901e1899920a44b51db91f7e59831828fa20907a2"
INVENTORY_PIN = "88276579d169c58ccfead7b645658da985255aa9e68071299ee83fb89c7fd841"
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
ARCHIVE_PIN = "sha256:07f2c7436354b405a41721b13bc6415eac337156364aedec9a6b1e1f6376a7e6"
GUARD = ROOT / "tools/pipeline_eval/variants/v5_orbit_domain.py"
GUARD_PIN = "14be68cd3af6906dbe0df64841e6a756e93caf234ad11b553bd1d8937fc2e18f"
OLD_GUARD = "37e894e5ff4a9d78356ccd876b5538fcdcf76d9a3b2faf99dccaead31d963464"
PACKET = "fast-scan-automatic-work/algo08-v2-a4e0600d444f191d2b82155b67dfffc7/detections.json"
SESSION = "fast-" + INVENTORY_PIN[:32]
CAPTURE = 1794578288008834160
CUTOFF = 1794578287810719418
ISSUED, ADMITTED = 6772, 5268
HOUR_NS = 3600 * 10**9
DONORS = tuple(Path("/dev/shm") / name / "tle" for name in (
    "leo-v3-raw-0016-best-results-01", "leo-held-anchor-selected-dense-01",
    "leo-v3-continued-cfo-0107-pair01", "leo-v3-saved-0160-pair-01",
    "leo-v3-family-endpoint-0169-results-01", "leo-v3-causal-0138-stage01",
    "leo-v3-saved-0316-pair-01", "leo-v3-saved-0402-pair-01",
))


def digest(data):
    return sha256(data).hexdigest()


def selected_refs(donors, capture, cutoff, expected):
    from leo.contracts.digests import canonical_digest

    chosen = {}
    for _, refs in donors:
        for ref in refs:
            if capture - 72 * HOUR_NS <= ref.collected_utc_ns < cutoff:
                chosen.setdefault(ref.path.name, ref)
    if canonical_digest({name: ref.sha256 for name, ref in chosen.items()}) != expected:
        raise ValueError("The staged donor union lacks the exact pre-capture archive")
    return tuple(chosen[name] for name in sorted(chosen))


def sources():
    from exact_named_route import SOURCES
    from history_cairo_render import RESIDUAL_SOURCES

    paths = {*SOURCES, GUARD, Path(__file__), HERE / "grid_feature_projection.c",
             HERE / "clean_saved_publication.py", HERE / "history_risk_route.py",
             *(HERE / name for name in RESIDUAL_SOURCES)}
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in sorted(paths)}


def stage(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from combined_raw_trial import PRODUCER, checked_producer
    from exact_named_route import resident_path
    from leo.operations.tle_archive import TleArchiveReader
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs study directory")
    pair = json.loads(boot.checked(PANEL / "pair.json", PAIR_PIN))
    old_attempt = pair["runs"]["candidate"]
    upstream = {
        "native": (PANEL / "candidate" / PACKET, NATIVE_PIN),
        "inventory": (RECOVERED / "fast-scan-inputs" / f"{SESSION}.json", INVENTORY_PIN),
        "offer": (Path(pair["region"]), OFFER_PIN),
    }
    bodies = {key: boot.checked(path, pin) for key, (path, pin) in upstream.items()}
    native, inventory = (json.loads(bodies[key]) for key in ("native", "inventory"))
    source, provenance = native["source"], native["provenance"]
    manifests = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    if (source["session_id"] != SESSION or source["input_manifest_sha256"] != "sha256:" + INVENTORY_PIN
            or source["raw_recording_authority_digest"] != old_attempt["raw_authority"]
            or old_attempt["native_sha256"] != "sha256:" + NATIVE_PIN
            or pair["archive"]["snapshots_sha256"] != ARCHIVE_PIN
            or native["clock_anchor"]["before"]["realtime_ns"] != CUTOFF
            or inventory["window_count"] != ISSUED or provenance["processed_windows"] != ADMITTED
            or len(source["probes"]) != 2 * ADMITTED
            or manifests != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]
            or old_attempt["failure_observation"]["exit_code"] != 1):
        raise ValueError("The archived v3 failure's physical scope changed")
    donors = {root: TleArchiveReader(root) for root in DONORS}
    refs = selected_refs(((root, reader.list_snapshots("space-track")) for root, reader in donors.items()),
                         CAPTURE, CUTOFF, ARCHIVE_PIN)
    if len(refs) != 46 or sum(ref.byte_size for ref in refs) > 96 * 1024**2:
        raise ValueError("The exact causal snapshot set must fit the saved-study bound")
    residency = resident([resident_path(ref.path) for ref in refs])
    docket = checked_producer(CUTOFF, {ref.sha256 for ref in refs})
    if not docket["overlapping_bodies"]:
        raise ValueError("The earlier portable orbit producer has no causal overlap")
    libraries = {part: Path("/dev/shm/leo-v3-saved-0402-pair-01") / (part + ".so")
                 for part in ("geographic_library", "regional_track_library", "frontier_block_library")}
    libs = dict(geographic_library="b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee",
                regional_track_library="5e96851c0f9c479dbb176eeb3f2ba143c461d590a9b35b00fb5c1d7ce984d098",
                frontier_block_library="adfbfca33caee3c6b337ddf401db1112e525867e451ad010eb30cb65965ce042")
    paths = {name: root / (name + ".json") for name in bodies}
    archive = root / "tle"
    destination = archive / "archive/space-track"
    root.mkdir(mode=0o700)
    destination.mkdir(parents=True)
    for ref in refs:
        boot.checked(ref.path, ref.sha256)
        os.link(ref.path, destination / ref.path.name, follow_symlinks=False)
    for name, path in paths.items():
        path.write_bytes(bodies[name])
    for name, path in libraries.items():
        boot.checked(resident_path(path), libs[name])
    local = dict(root=str(archive), snapshots_sha256=ARCHIVE_PIN, snapshots=len(refs),
                 bytes=sum(ref.byte_size for ref in refs))
    request = dict(case=CASE, session=SESSION, inventory="sha256:" + INVENTORY_PIN, issued=ISSUED, admitted=ADMITTED,
                   raw_authority=old_attempt["raw_authority"], original_archive=pair["archive"], local_archive=local,
                   causal_cutoff_utc_ns=CUTOFF, recording=pair["recording"], native_file=str(paths["native"]),
                   offer_file=str(paths["offer"]), offer_sha256=OFFER_PIN, native_sha256=NATIVE_PIN,
                   local_libraries={name: str(path) for name, path in libraries.items()}, manifests=manifests)
    req = root / "request.json"
    write(req, request)
    bound = dict(case=CASE, stage=str(root), archive=str(archive), request=str(req), inventory=str(paths["inventory"]),
                 issued=ISSUED, admitted=ADMITTED, portable=[str(PRODUCER.file), PRODUCER.sha256, PRODUCER.producer_sha256],
                 sources=sources(), packets={str(path): digest(path.read_bytes()) for path in (
                     *paths.values(), req, *libraries.values(), PRODUCER.file, PRODUCER.file.parent / "artifact-bind.json")})
    job = root / "job.json"
    write(job, dict(binding=bound, original_archive=pair["archive"]))
    write(root / "admission.json", dict(pair_sha256=PAIR_PIN, original_snapshot_census_captured_ns=CAPTURE,
          archive=local, archive_sources=[{"path": str(ref.path), "sha256": ref.sha256} for ref in refs],
          source_payload_reads_bytes=0, staged_catalogue_copied_bytes=0, archive_residency=residency,
          staged_non_archive_bytes=sum(len(body) for body in bodies.values()), producer=docket,
          authentic_factors=sum(len(row["candidates"]) for row in source["probes"]), sources=bound["sources"],
          setup_clock=boot.clock(started), job_sha256=digest(job.read_bytes()), planned_children=1))


def worker(job, pin, output):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_publication import run
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    original = boot.load_runtime
    recovery = []
    with ExitStack() as scope:
        def load():
            result = original()
            from tools import algo08_position

            module_path = Path(algo08_position.corner_support.__wrapped__.__code__.co_filename)
            boot.checked(module_path, OLD_GUARD)
            boot.checked(GUARD, GUARD_PIN)
            repaired = runpy.run_path(str(GUARD))["corner_support"]

            @contextmanager
            def track():
                with repaired() as entries:
                    recovery.append(entries)
                    yield

            scope.enter_context(patch.object(algo08_position, "corner_support", track))
            return result

        scope.enter_context(patch.object(boot, "load_runtime", load))
        try:
            run("routed", job, pin, output)
        finally:
            write(output / "corner-retry.json", recovery)


def launch(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    job = root / "job.json"
    book = json.loads((root / "admission.json").read_bytes())
    machine = host()
    if (machine["cpu"] != [2] or machine["nice"] != 15 or book["sources"] != sources()
            or digest(job.read_bytes()) != book["job_sha256"] or (root / "routed").exists()):
        raise ValueError("Require fresh low-priority launch and the preregistered source pins")
    (root / "tmp").mkdir()
    shutil.copytree("/dev/shm/leo-v3-clean-saved-0169-initial01/fonts", root / "fonts")
    target = root / "routed"
    target.mkdir()
    write(target / "binding.json", {"input": json.loads(job.read_bytes())["binding"]})
    cmd = ["/usr/bin/timeout", "--kill-after=2s", "100s", str(boot.RELEASE / "venv/bin/python"),
           "-IB", __file__, "worker", str(job), book["job_sha256"], str(target)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "run.json", dict(command=cmd, machine=machine))
    write(root / "clock.json", measure(cmd, env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("stage", "launch", "worker"))
    cli.add_argument("path", type=Path)
    cli.add_argument("pin", nargs="?")
    cli.add_argument("output", type=Path, nargs="?")
    args = cli.parse_args()
    if args.mode == "worker":
        worker(args.path, args.pin, args.output)
    else:
        {"stage": stage, "launch": launch}[args.mode](args.path)
