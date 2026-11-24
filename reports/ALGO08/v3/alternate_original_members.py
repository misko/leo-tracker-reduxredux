"""Solve the post-temporal saved DS30-0016 subset from even original members."""

import argparse
from collections import Counter
from contextlib import ExitStack
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
from ds30_0359_cairo_saved import digest, read


CASE = "DS30-0016"
PROTOCOL = HERE / "alternate-original-members-0016-protocol.md"
PACKET_PIN = "4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"
INVENTORY_PIN = "e22b918df63370a0590757b70f71a0e620792cf90cf78a833e601af7a0b395a6"
ADMISSION_PIN = "7139e35e91870e05aa95b2eecddb9cf6beeb231428cb986be3f1935fe010b243"
CONTROL_SEAL = "660dec373641a410d30a0695378df859922adde4868561b8457ae88e45e921dd"
ARCHIVE_PIN = "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
CONTROL = Path("/dev/shm/leo-v3-stock-raw-repeat-DS30-0016-01")
STOCK = CONTROL / "stock"
PACKET = STOCK / "fast-scan-automatic-work/algo08-v2-56f5b28446c41ce61e320ada30bd0562/detections.json"
INVENTORY = STOCK / "fast-scan-inputs/fast-e22b918df63370a0590757b70f71a0e6.json"
METADATA = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01/fast8-auto-20261113-112146-b04f5461-1-lower")
DESCRIPTION = "private post-temporal 20 ms detector replay, even original member ordinals"
ENTRY = Path(__file__).resolve()
SCORER = HERE / "alternate_original_members_score.py"
LIMIT_KM = 0.250
LEASE = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")


def member_spans(inventory, manifests):
    """Use signed local sequences, with parity carried across segments."""
    members = []
    offset = 0
    for segment, manifest in zip(inventory["segments"], manifests, strict=True):
        if (manifest["receiver_ids"] != [0, 1] or manifest["window_ms"] != 20
                or manifest["window_count"] != segment["windows"]
                or manifest["session_id"] != Path(segment["path"]).name):
            raise ValueError("Original stereo member geometry differs from signed inventory")
        local = 0
        names = set()
        for index, chunk in enumerate(manifest["chunks"]):
            name = chunk["payload_relative_path"]
            count, size = chunk["window_count"], chunk["compressed_bytes"]
            if (chunk["chunk_index"] != index or chunk["first_sequence"] != local or count <= 0
                    or size <= 0 or name in names or Path(name).name != name):
                raise ValueError("Unordered, overlapping or invalid signed compressed member")
            ordinal = len(members)
            members.append(dict(ordinal=ordinal, segment=segment["scope"], manifest=segment["manifest_digest"],
                                first_visit=offset + local, stop_visit=offset + local + count,
                                retained=ordinal % 2 == 0, **chunk))
            names.add(name)
            local += count
        if local != segment["windows"] or not local:
            raise ValueError("Signed compressed members do not exactly account for segment visits")
        offset += local
    if offset != inventory["window_count"] or len(members) < 2:
        raise ValueError("Signed compressed members do not account for the recording")
    return members


def project(native, members, canonical_digest):
    source, provenance = native["source"], native["provenance"]
    count = provenance["window_count"]
    original = source["probes"]
    stereo = {}
    for row in original:
        receivers = stereo.setdefault(row["visit_index"], set())
        receiver = row["receiver_id"]
        if receiver in receivers:
            raise ValueError("Duplicate original receiver slot")
        receivers.add(receiver)
    excluded = {row["visit"]: row for row in provenance["excluded_windows"]}
    if (len(native["delivery_clocks"]) != count or len(stereo) != provenance["processed_windows"]
            or len(excluded) != len(provenance["excluded_windows"]) or len(excluded) != provenance["invalid_capture"]
            or set(stereo) & set(excluded) or set(stereo) | set(excluded) != set(range(count))
            or any(receivers != {0, 1} for receivers in stereo.values())):
        raise ValueError("Expected a complete stereo and invalid-capture ledger in the original packet")
    retained = {i for m in members if m["retained"] for i in range(m["first_visit"], m["stop_visit"])}
    skipped = sorted(set(range(count)) - retained)
    probes = [row for row in original if row["visit_index"] in retained]
    invalid = [row for row in provenance["excluded_windows"] if row["visit"] in retained]
    detector = provenance["detector_sha256"].removeprefix("sha256:")
    authority = source["raw_recording_authority_digest"]
    if source["analysis_manifest_sha256"] != canonical_digest(["cancellation", authority, detector, original]):
        raise ValueError("Original native factors differ from their manifest")
    analysis = canonical_digest(["cancellation", authority, detector, probes])
    if analysis == source["analysis_manifest_sha256"] or len(probes) // 2 + len(invalid) + len(skipped) != count:
        raise ValueError("Member projection did not form a smaller, exhaustive acquisition ledger")
    sampling = dict(kind="saved-post-temporal-member-mask", original_packet_sha256=canonical_digest(native),
                    original_inventory_sha256=source["input_manifest_sha256"], members_sha256=canonical_digest(members),
                    skipped_acquisition_windows=skipped, receiver_slots=[0, 1])
    derived = dict(native, source=dict(source, probes=probes, analysis_manifest_sha256=analysis),
                   provenance=dict(provenance, run_id="blind-compact-" + analysis[7:39],
                                   processed_windows=len(probes) // 2, invalid_capture=len(invalid),
                                   excluded_windows=invalid, research_sampling=sampling))
    summary = {}
    for label, chosen, rows, invalid_count in (("full", members, original, len(excluded)),
                                               ("retained", [m for m in members if m["retained"]], probes, len(invalid))):
        summary[label] = dict(members=len(chosen), visits=sum(m["window_count"] for m in chosen),
                              compressed_bytes=sum(m["compressed_bytes"] for m in chosen),
                              uncompressed_bytes=sum(m["uncompressed_bytes"] for m in chosen),
                              index_bytes=sum(m["index_bytes"] for m in chosen),
                              processed_visits=len(rows) // 2, invalid_capture=invalid_count,
                              receiver_factors=sum(len(row["candidates"]) for row in rows),
                              stereo_by_channel=dict(Counter(row["channel"] for row in rows if row["receiver_id"] == 0)))
    return derived, summary


def report_adapter(report, recording, run_id, native):
    result = report(recording, run_id, native)
    sampling = native["provenance"]["research_sampling"]
    result["counts"]["skipped_acquisition"] = len(sampling["skipped_acquisition_windows"])
    result["research_sampling"] = sampling
    if sum(result["counts"].values()) != result["window_count"]:
        raise ValueError("The private receipt must disclose all scheduled visit outcomes")
    return result


def frozen_sources():
    dependencies = tuple(HERE / name for name in ("alternate-original-members-protocol.md", "empty_bootstrap.py",
                         "prospective_0316_solver.py", "joint_publication.py", "unified_short_bootstrap.py"))
    return {path.name: digest(path) for path in (ENTRY, PROTOCOL, SCORER, *dependencies)}


def probe():
    import empty_bootstrap as boot
    import prospective_0316_solver as ordinary

    _, specification, _, _, _ = boot.load_runtime()
    print(json.dumps(dict(ordinary=callable(ordinary.worker), detector=specification["detector_sha256"])))


def worker(root):
    import empty_bootstrap as boot
    import prospective_0316_solver as ordinary

    admission = read(root / "admission.json")
    request = root / "request.json"
    if (admission["member_trial_sources"] != frozen_sources() or admission["request_sha256"] != digest(request)
            or admission["inventory_sha256"] != digest(INVENTORY)):
        raise ValueError("The frozen program, original inventory or derived request changed")
    runtime = boot.load_runtime
    with ExitStack() as scope:
        def load():
            loaded = runtime()
            from tools import algo08_scan

            scope.enter_context(patch.object(algo08_scan, "scan_report", partial(report_adapter, algo08_scan.scan_report)))
            return loaded

        scope.enter_context(patch.object(boot, "load_runtime", load))
        ordinary.worker(request, "stock", root / "candidate", source_pins={},
                        native_sha=admission["derived_packet_sha256"], windows=admission["acquisition"]["full"]["visits"],
                        admitted=admission["acquisition"]["retained"]["processed_visits"], inventory_file=INVENTORY,
                        audit_name="worker.json", input_description=DESCRIPTION)


def launch(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, bind_native, checked, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest, canonical_json_bytes
    from leo.operations.tle_archive import TleArchiveReader
    from prospective_0316_solver import DETECTOR
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Require a fresh private tmpfs root")
    machine = host()
    filesystem = os.statvfs(root.parent)
    free = filesystem.f_bavail * filesystem.f_frsize
    if free < 128 * 1024**2:
        raise ValueError("Insufficient tmpfs headroom")
    stock_admission = json.loads(checked(CONTROL / "admission.json", ADMISSION_PIN))
    prior = stock_admission["request"]
    inventory = json.loads(checked(resident_path(INVENTORY), INVENTORY_PIN))
    native = json.loads(checked(resident_path(PACKET), PACKET_PIN))
    bind_native(native, prior["session"], prior["inventory"], DETECTOR, expected="sha256:" + PACKET_PIN)
    if (stock_admission["case"] != CASE or stock_admission["machine"] != machine
            or native["source"]["probe_ms"] != 20 or native["provenance"]["processed_windows"] != 713
            or native["source"]["raw_recording_authority_digest"] != prior["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != prior["cutoff_utc_ns"]):
        raise ValueError("The authenticated installed acquisition does not match the frozen case")
    manifests = []
    manifest_paths = []
    recording = Path(prior["recording"])
    for segment in inventory["segments"]:
        folder = Path(segment["path"])
        if folder.parent != recording:
            raise ValueError("Inventory points outside of the original recording")
        path = resident_path(METADATA / folder.name / "manifest.json")
        if path.stat().st_size > 256_000:
            raise ValueError("Expected a small signed manifest only")
        manifest_paths.append(path)
        manifests.append(json.loads(checked(path, segment["manifest_digest"].removeprefix("sha256:"))))
    members = member_spans(inventory, manifests)
    derived, acquisition = project(native, members, canonical_digest)
    if (acquisition["full"]["members"], acquisition["full"]["visits"], acquisition["full"]["compressed_bytes"]) != (
            13, 808, 991_734_597):
        raise ValueError("The signed member scope differs from the existing recording custody")
    release = verified_v3(NAMED_V3)
    region = resident_path(Path(prior["region"]))
    checked(region, prior["offer_sha256"])
    archive, refs = checked_catalogue({"archive": prior["archive"]["root"]},
        dict(local_archive=stock_admission["archive_before"], original_archive=prior["archive"],
             causal_cutoff_utc_ns=prior["cutoff_utc_ns"]), TleArchiveReader, canonical_digest)
    if len(refs) != 46 or prior["archive"]["snapshots_sha256"] != ARCHIVE_PIN:
        raise ValueError("The original causal catalogue differs")
    cache = resident([*(ref.path for ref in refs), *manifest_paths, PACKET, INVENTORY, region])
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    for path in (CONTROL / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), root / "fonts" / path.name)
    restricted = root / "restricted-native.json"
    restricted.write_bytes(canonical_json_bytes(derived))
    packet_pin = digest(restricted)
    request = dict(recording=str(recording), session=prior["session"], inventory=prior["inventory"],
                   raw_authority=prior["authority"], causal_cutoff_utc_ns=prior["cutoff_utc_ns"],
                   native_file=str(restricted), native_sha256=packet_pin, offer_file=str(region),
                   offer_sha256=prior["offer_sha256"], local_archive=dict(root=str(archive)), local_libraries={},
                   manifests=[[str(Path(s["path"]) / "manifest.json"), s["manifest_digest"]] for s in inventory["segments"]])
    write(root / "request.json", request)
    write(root / "members.json", members)
    argv = [str(RELEASE / "venv/bin/python"), "-IB", str(ENTRY)]
    timeout = ["/usr/bin/timeout", "--kill-after=2s"]
    command = [*timeout, "45s", *argv, "worker", str(root)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    setup, smoke_start, before = clock(began), now(), resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke_run = subprocess.run([*timeout, "15s", *argv, "probe"], env=env, capture_output=True, text=True, check=False)
    smoke, after = clock(smoke_start), resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke["cpu_s"] += after.ru_stime + after.ru_utime - before.ru_stime - before.ru_utime
    book = dict(case=CASE, command=command, member_trial_sources=frozen_sources(), request_sha256=digest(root / "request.json"),
                original_packet_sha256=PACKET_PIN, inventory_sha256=INVENTORY_PIN, original_admission_sha256=ADMISSION_PIN,
                derived_packet_sha256=packet_pin, members_sha256=canonical_digest(members), original_seal_sha256=CONTROL_SEAL,
                machine=machine, installed_release=release, resident=cache, tmpfs_free_bytes_at_admission=free,
                archive_bodies=len(refs), archive_bytes=sum(ref.byte_size for ref in refs), setup=setup,
                smoke=dict(clock=smoke, exit_code=smoke_run.returncode, stdout=smoke_run.stdout, stderr=smoke_run.stderr),
                waveform_reads=0, backing_archive_reads=0, planned_candidate_children=1, acquisition=acquisition)
    write(root / "admission.json", book)
    smoke_run.check_returncode()
    if json.loads(smoke_run.stdout) != dict(ordinary=True, detector=DETECTOR):
        raise ValueError("Original installed ordinary imported worker differs from the frozen one")
    write(root / "clock.json", measure(command, env, root / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "worker", "launch"))
    parser.add_argument("root", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "probe":
        probe()
    elif args.action == "worker":
        worker(args.root)
    else:
        launch(args.root)
