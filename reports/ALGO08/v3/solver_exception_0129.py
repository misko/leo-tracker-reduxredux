"""Stage one exact DS30-0129 job for the unchanged in-flight worker."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from solver_exception_0022 import DONORS, OFFER_PIN, ROOT, digest, selected_refs
from solver_exception_live import PREVIOUS, PREVIOUS_PIN, sources


CASE = "DS30-0129"
PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
PAIR_PIN = "9cd756f25810f2fd308a1d6ccc5c4691ff3a46c3f6ed9e841312f92fb3bc16f0"
NATIVE_PIN = "2b81287ab8a4e7448a1f48a998a6851672908e45cfd19715436a51ebcc129e60"
INVENTORY_PIN = "08ac1f53b9d7e3798e7577c8a626bd577fc26f39080e85846147c53b5eeea458"
ARCHIVE_PIN = "sha256:1e53d0142c863621a187f4c91a3c3fb1b738707258f3f5dabc28e208fd713966"
SESSION = "fast-" + INVENTORY_PIN[:32]
NATIVE = "fast-scan-automatic-work/algo08-v2-d836ceaa67c63be1d6bfad25bc1a2e92/detections.json"
CAPTURE, CUTOFF = 1794733922460795334, 1794733922242636106
ISSUED, ADMITTED = 6767, 6752


def read(path):
    return json.loads(path.read_bytes())


def runtime_pins():
    path = Path(__file__)
    return sources() | {str(path.relative_to(ROOT)): digest(path.read_bytes())}


def validate(pair, packet, inventory):
    source, provenance = packet["source"], packet["provenance"]
    failed = pair["runs"]["candidate"]
    binding = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    if (source["session_id"] != SESSION or source["input_manifest_sha256"] != "sha256:" + INVENTORY_PIN
            or source["raw_recording_authority_digest"] != failed["raw_authority"]
            or failed["native_sha256"] != "sha256:" + NATIVE_PIN
            or pair["archive"]["snapshots_sha256"] != ARCHIVE_PIN
            or packet["clock_anchor"]["before"]["realtime_ns"] != CUTOFF
            or inventory["window_count"] != ISSUED or provenance["processed_windows"] != ADMITTED
            or len(source["probes"]) != 2 * ADMITTED or failed["failure_observation"]["exit_code"] != 1
            or binding != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]
            or pair["runs"]["baseline"]["receipt"]["region"] != read(PREVIOUS / "offer.json")):
        raise ValueError("The saved original offer, acquisition, cutoff or manifest sequence changed")
    return binding


def launch(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from combined_raw_trial import PRODUCER, checked_producer
    from dense_geographic_trial import host
    from exact_named_route import resident_path
    from full_short_physical import environment
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs result")
    machine = host()
    prior = json.loads(boot.checked(PREVIOUS / "result.json", PREVIOUS_PIN))
    if not prior["qualified_recovery"] or prior["run"]["machine"] != machine:
        raise ValueError("Expected the qualified comparison's low-priority environment")
    old_job = json.loads(boot.checked(PREVIOUS / "job.json", prior["admission"]["job_sha256"]))["binding"]
    old_req = json.loads(boot.checked(Path(old_job["request"]), old_job["packets"][old_job["request"]]))
    pair = json.loads(boot.checked(PANEL / "pair.json", PAIR_PIN))
    warehouse = {
        "native": (PANEL / "candidate" / NATIVE, NATIVE_PIN),
        "inventory": (PANEL / "candidate/fast-scan-inputs" / f"{SESSION}.json", INVENTORY_PIN),
        "offer": (PREVIOUS / "offer.json", OFFER_PIN),
    }
    data = {key: boot.checked(path, pin) for key, (path, pin) in warehouse.items()}
    packet, inventory = (json.loads(data[name]) for name in ("native", "inventory"))
    manifests = validate(pair, packet, inventory)
    refs = selected_refs(((donor, TleArchiveReader(donor).list_snapshots("space-track")) for donor in DONORS),
                         CAPTURE, CUTOFF, ARCHIVE_PIN)
    extent = sum(ref.byte_size for ref in refs)
    if len(refs) != 51 or extent > 96 * 1024**2:
        raise ValueError("Require the complete bounded 51-snapshot causal archive")
    cached = resident([resident_path(ref.path) for ref in refs])
    producer = checked_producer(CUTOFF, {ref.sha256 for ref in refs})
    if not producer["overlapping_bodies"]:
        raise ValueError("The frozen earlier portable index requires actual causal overlap")
    archive = root / "tle"
    link_root = archive / "archive/space-track"
    link_root.mkdir(parents=True, mode=0o700)
    for ref in refs:
        boot.checked(ref.path, ref.sha256)
        os.link(ref.path, link_root / ref.path.name, follow_symlinks=False)
    paths = {name: root / (name + ".json") for name in data}
    for name, path in paths.items():
        path.write_bytes(data[name])
    req_path = root / "request.json"
    req = old_req | dict(case=CASE, session=SESSION, inventory="sha256:" + INVENTORY_PIN,
                         raw_authority=packet["source"]["raw_recording_authority_digest"], issued=ISSUED,
                         admitted=ADMITTED, causal_cutoff_utc_ns=CUTOFF, recording=pair["recording"],
                         manifests=manifests, native_file=str(paths["native"]), native_sha256=NATIVE_PIN,
                         offer_file=str(paths["offer"]), original_archive=pair["archive"],
                         local_archive=dict(root=str(archive), snapshots_sha256=ARCHIVE_PIN,
                                            snapshots=len(refs), bytes=extent))
    write(req_path, req)
    artifacts = [*(Path(path) for path in req["local_libraries"].values()),
                 PRODUCER.file, PRODUCER.file.parent / "artifact-bind.json"]
    for file in artifacts:
        boot.checked(resident_path(file), old_job["packets"][str(file)])
    binding = dict(case=CASE, stage=str(root), archive=str(archive), request=str(req_path),
                   inventory=str(paths["inventory"]), issued=ISSUED, admitted=ADMITTED,
                   portable=old_job["portable"], sources=runtime_pins(),
                   packets={str(path): digest(path.read_bytes()) for path in [*paths.values(), req_path, *artifacts]})
    job = root / "job.json"
    write(job, dict(binding=binding, original_archive=pair["archive"]))
    (root / "tmp").mkdir()
    shutil.copytree(PREVIOUS / "fonts", root / "fonts")
    target = root / "routed"
    target.mkdir()
    write(target / "binding.json", {"input": binding})
    job_pin = digest(job.read_bytes())
    cmd = ["/usr/bin/timeout", "--kill-after=2s", "110s", str(boot.RELEASE / "venv/bin/python"), "-IB",
           str(HERE / "solver_exception_live.py"), "worker", str(job), job_pin, str(target)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "admission.json", dict(command=cmd, machine=machine, job_sha256=job_pin, setup=boot.clock(started),
          causal_residency=cached, archive_sources=[str(ref.path) for ref in refs], producer=producer,
          native_from=str(warehouse["native"][0]), inventory_from=str(warehouse["inventory"][0]),
          source_bytes=sum(map(len, data.values())), archive_payload_copied_bytes=0, no_waveform=True,
          source_pins=binding["sources"], prior_result_sha256=PREVIOUS_PIN, candidate_children=1,
          authentic_factors=sum(len(row["candidates"]) for row in packet["source"]["probes"])))
    write(root / "clock.json", measure(cmd, env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    launch(cli.parse_args().root)
