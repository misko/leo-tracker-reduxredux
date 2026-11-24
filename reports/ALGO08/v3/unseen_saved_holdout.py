"""Run the two frozen saved workers on the one independently assigned DS30 input."""

import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from solver_exception_0022 import DONORS, OFFER_PIN, ROOT, digest, selected_refs
from solver_exception_live import PREVIOUS, PREVIOUS_PIN, sources


CASE = "DS30-0255"
PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE
ASSIGN = HERE / "unseen-saved-assignment.py"
NATIVE_PIN = "910f1629e94500884e7429d3cb66cbec1c7ab3ce7a82d9db60db6cb37ed9235e"
INVENTORY_PIN = "cdb7b62dcc39438e7e49be237a2e5b9946f89d273d78845f36eaa80e5c30e2a3"
ARCHIVE_PIN = "sha256:2b99f89e318eb4bf94c34221a0a1396f59b0f01277bc8397e79507228df69537"
SESSION = "fast-" + INVENTORY_PIN[:32]
CAPTURE, CUTOFF = 1794917458139770218, 1794917457908207913
ISSUED, ADMITTED = 6772, 6742


def read(path):
    return json.loads(path.read_bytes())


def enrollment():
    result = runpy.run_path(str(ASSIGN))["assignment"]()
    if result["selected"] != CASE:
        raise ValueError("The sealed assignment changed")
    return result


def runtime_sources():
    paths = (Path(__file__), ASSIGN, HERE / "clean_saved_publication.py", HERE / "unseen-saved-holdout-protocol.md")
    return sources() | {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def estimated_child_ceiling(post_detection):
    """Give the routed worker two historical post-detection periods and five seconds of setup."""
    return 2 * post_detection + 5 if post_detection and post_detection > 0 else None


def inputs(pair, packet, inventory, terminal, offer):
    from leo.contracts.digests import canonical_digest

    scope = packet["source"]
    release = pair["runs"]["candidate"]
    record = release["receipt"]
    manifests = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    if (scope["session_id"] != SESSION or scope["input_manifest_sha256"] != "sha256:" + INVENTORY_PIN
            or record["session_id"] != SESSION or record["window_count"] != ISSUED
            or scope["raw_recording_authority_digest"] != release["raw_authority"]
            or terminal["native_sha256"] != "sha256:" + NATIVE_PIN
            or canonical_digest(terminal) != record["terminal_sha256"] or terminal["region"] != offer
            or record["region"] != offer or pair["archive"]["snapshots_sha256"] != ARCHIVE_PIN
            or packet["clock_anchor"]["before"]["realtime_ns"] != CUTOFF or inventory["window_count"] != ISSUED
            or packet["provenance"]["processed_windows"] != ADMITTED or len(scope["probes"]) != 2 * ADMITTED
            or manifests != [[row["path"], row["sha256"]] for row in pair["cache_observation"]["manifests"]]):
        raise ValueError("The enrolled saved detector, inventory or authoritative offer changed")
    return manifests


def launch(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from exact_named_route import resident_path
    from full_short_physical import environment
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Choose a fresh private tmpfs result")
    assigned = enrollment()
    (historical,) = (row for row in read(HERE / "measurements/release-stage-budget.json")["rows"] if row["case"] == CASE)
    estimate = estimated_child_ceiling(historical["post_s"])
    if estimate is None or estimate >= 120:
        raise ValueError("The saved worker forecast exceeds the two-minute enrollment budget")
    machine = host()
    pair = json.loads(boot.checked(PANEL / "pair.json", assigned["archived_pair_sha256"]))
    run = pair["runs"]["candidate"]["receipt"]["run_id"]
    work = PANEL / "candidate/fast-scan-automatic-work"
    native, = work.glob("*/detections.json")
    warehouse = {
        "native": (native, NATIVE_PIN),
        "inventory": (PANEL / "candidate/fast-scan-inputs" / f"{SESSION}.json", INVENTORY_PIN),
        "offer": (PREVIOUS / "offer.json", OFFER_PIN),
    }
    blobs = {key: boot.checked(path, pin) for key, (path, pin) in warehouse.items()}
    packet, inventory, offer = (json.loads(blobs[key]) for key in ("native", "inventory", "offer"))
    manifests = inputs(pair, packet, inventory, read(work / run / "terminal.json"), offer)
    refs = selected_refs(((donor, TleArchiveReader(donor).list_snapshots("space-track")) for donor in DONORS),
                         CAPTURE, CUTOFF, ARCHIVE_PIN)
    extent = sum(ref.byte_size for ref in refs)
    if len(refs) != 48 or extent != 85_770_226:
        raise ValueError("Require the complete pre-capture resident 48-snapshot archive")
    cached = resident([resident_path(ref.path) for ref in refs])
    prior = json.loads(boot.checked(PREVIOUS / "result.json", PREVIOUS_PIN))
    former = json.loads(boot.checked(PREVIOUS / "job.json", prior["admission"]["job_sha256"]))["binding"]
    artifact, _, producer_pin = former["portable"]
    provenance_file = Path(artifact).parent / "artifact-bind.json"
    index_source = json.loads(boot.checked(provenance_file, producer_pin))["source"]
    overlap = set(index_source["body_digests"]) & {ref.sha256 for ref in refs}
    if overlap or index_source["cutoff_utc_ns"] >= CUTOFF:
        raise ValueError("The frozen ordinary-preparation enrollment requires this verified index's zero overlap")
    old_req = json.loads(boot.checked(Path(former["request"]), former["packets"][former["request"]]))
    local = root / "tle"
    dest = local / "archive/space-track"
    root.mkdir(mode=0o700)
    dest.mkdir(parents=True)
    for ref in refs:
        boot.checked(ref.path, ref.sha256)
        os.link(ref.path, dest / ref.path.name, follow_symlinks=False)
    paths = {key: root / (key + ".json") for key in warehouse}
    for key, path in paths.items():
        path.write_bytes(blobs[key])
    req = old_req | dict(case=CASE, session=SESSION, inventory="sha256:" + INVENTORY_PIN, issued=ISSUED,
                         admitted=ADMITTED, raw_authority=packet["source"]["raw_recording_authority_digest"],
                         causal_cutoff_utc_ns=CUTOFF, recording=pair["recording"], manifests=manifests,
                         native_file=str(paths["native"]), native_sha256=NATIVE_PIN, offer_file=str(paths["offer"]),
                         original_archive=pair["archive"], local_archive=dict(root=str(local), snapshots_sha256=ARCHIVE_PIN,
                                                                           snapshots=len(refs), bytes=extent))
    request_file = root / "request.json"
    write(request_file, req)
    libraries = [Path(name) for name in req["local_libraries"].values()]
    for lib in libraries:
        boot.checked(resident_path(lib), former["packets"][str(lib)])
    binding = dict(case=CASE, stage=str(root), archive=str(local), request=str(request_file),
                   inventory=str(paths["inventory"]), issued=ISSUED, admitted=ADMITTED, portable=None,
                   packets={str(path): digest(path.read_bytes()) for path in [*paths.values(), request_file, *libraries]},
                   sources=runtime_sources())
    job = root / "job.json"
    write(job, dict(binding=binding, original_archive=pair["archive"]))
    job_pin = digest(job.read_bytes())
    (root / "tmp").mkdir()
    shutil.copytree(PREVIOUS / "fonts", root / "fonts")
    commands = {}
    for mode in assigned["order"]:
        target = root / mode
        target.mkdir()
        write(target / "binding.json", {"input": binding})
        common = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(boot.RELEASE / "venv/bin/python"), "-IB"]
        entry = (HERE / "solver_exception_live.py", "worker") if mode == "routed" else (
            HERE / "clean_saved_publication.py", "installed")
        commands[mode] = [*common, str(entry[0]), entry[1], str(job), job_pin, str(target)]
    write(root / "admission.json", dict(assignment=assigned, commands=commands, machine=machine,
          job_sha256=job_pin, sources=binding["sources"], setup=boot.clock(started),
          historical_post_detection_seconds=historical["post_s"], expected_saved_child_ceiling_seconds=estimate,
          paid_archive_bytes=extent, archive_residency=cached, archive_sources=[str(r.path) for r in refs],
          new_archive_copied_bytes=0, direct_inputs={key: str(path) for key, (path, _) in warehouse.items()},
          prior_portable_body_overlap=len(overlap), prior_portable_cutoff=index_source["cutoff_utc_ns"],
          use_live_orbit_support=True, use_causal_body_election=False, no_waveform=True,
          authentic_factors=sum(len(row["candidates"]) for row in packet["source"]["probes"])))
    for mode in assigned["order"]:
        env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
        target = root / mode
        write(target / "clock.json", measure(commands[mode], env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    launch(parser.parse_args().root)
