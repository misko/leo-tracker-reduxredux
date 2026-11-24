"""Run the originally frozen DS30-0163 mask through the clean composed solver."""

import argparse
from contextlib import ExitStack
from functools import partial
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from alternate_original_members import member_spans, project, report_adapter
from ds30_0163_composed_saved import HEADROOM, TRANSFER_0163, digest, donor_sources, read


PROTOCOL = HERE / "alternate-original-members-protocol.md"
TRANSFER = TRANSFER_0163
PACKET_PIN = "f026bb3822ad7a946979a091c55b06d11d7c675e667c564f7d984e9f38fb2651"
INVENTORY_PIN = "d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd"
CONTROL = Path("/dev/shm/leo-v3-0163-composed-saved-result01")
CONTROL_PIN = "e08d702e92753fe2bc274c39f742815cc23b8be74415b3476a13b3b7bfac4573"
CONTROL_SEAL = "b274c007546f7c36fae3b17d31d5e870ca96c47d47bdd99bffc4b36b79272176"
DESCRIPTION = "private post-temporal 20 ms detector replay, even original member ordinals"
ENTRY = Path(__file__).resolve()
SCORER = HERE / "alternate_original_members_0163_score.py"
METADATA = Path("/tmp/leo-v3-0163-authenticated-member-map01")
FAILED_PREFLIGHT = HERE / "measurements/alternate-original-members-0163-admission-failure.json.gz"
FAILED_PREFLIGHT_PIN = "1948e4382648e83229333e8553adfd91de69a4a81c4b13ab9c88fb03cb6009bf"


def frozen_sources():
    names = (ENTRY, PROTOCOL, SCORER, HERE / "alternate_original_members.py",
             HERE / "alternate_original_members_score.py", HERE / "ds30_0163_composed_saved.py")
    return {path.name: digest(path) for path in names}


def restricted_request(request, packet, pin, kept):
    return dict(request, admitted=kept, native_file=str(packet), native_sha256=pin)


def restricted_binding(bound, path, packet, pin, kept):
    packets = bound["packets"] | {str(path): digest(path), str(packet): pin}
    return dict(bound, request=str(path), packets=packets, admitted=kept, parent_request=bound["request"])


def original_probe():
    import ds30_0359_composed_saved as composed

    with patch.multiple(composed, READY=TRANSFER.ready, READY_PIN=TRANSFER.ready_pin, JOB_PIN=TRANSFER.job_pin):
        composed.probe()


def worker(root):
    import clean_saved_publication as saved
    import ds30_0359_composed_saved as composed
    import empty_bootstrap as boot
    import prospective_0316_solver as publication
    from aperture_trial import read as read_publication_request

    admission = read(root / "admission.json")
    if admission["member_trial_sources"] != frozen_sources() or admission["job_sha256"] != TRANSFER.job_pin:
        raise ValueError("The frozen source or ready job changed")
    runtime, original_load_job = boot.load_runtime, saved.load_job

    with ExitStack() as scope:
        def load_job(path, pin):
            if path != TRANSFER.ready / "job.json" or pin != TRANSFER.job_pin:
                raise ValueError("Require the original authenticated ready job")
            bound, request = original_load_job(path, pin)
            packet = root / "restricted-native.json"
            pin = admission["derived_packet_sha256"]
            derived = json.loads(boot.checked(packet, pin))
            source = derived["provenance"]["research_sampling"]
            if (source["original_packet_sha256"] != "sha256:" + PACKET_PIN
                    or source["original_inventory_sha256"] != request["inventory"]
                    or source["members_sha256"] != admission["members_sha256"]):
                raise ValueError("The derived packet does not bind its original source and member schedule")
            kept = derived["provenance"]["processed_windows"]
            path = root / "restricted-request.json"
            boot.checked(path, admission["derived_request_sha256"])
            expected = restricted_request(request, packet, pin, kept)
            if read_publication_request(path) != expected:
                raise ValueError("The persisted request and original authenticated binding disagree")
            return restricted_binding(bound, path, packet, pin, kept), expected

        def load():
            loaded = runtime()
            from tools import algo08_scan

            scope.enter_context(patch.object(algo08_scan, "scan_report", partial(report_adapter, algo08_scan.scan_report)))
            return loaded

        scope.enter_context(patch.object(saved, "load_job", load_job))
        scope.enter_context(patch.object(boot, "load_runtime", load))
        scope.enter_context(patch.object(publication, "worker", partial(publication.worker, input_description=DESCRIPTION)))
        scope.enter_context(patch.multiple(composed, READY=TRANSFER.ready, READY_PIN=TRANSFER.ready_pin, JOB_PIN=TRANSFER.job_pin))
        composed.worker(root)


def launch(root, metadata):
    import combined_successor_0289 as combined
    import ds30_0359_composed_saved as composed
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, bind_native, checked, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest, canonical_json_bytes
    from leo.operations.tle_archive import TleArchiveReader
    from prospective_0316_solver import DETECTOR
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Require a fresh private tmpfs root")
    filesystem = os.statvfs(root.parent)
    free = filesystem.f_bavail * filesystem.f_frsize
    if free < HEADROOM:
        raise ValueError("Insufficient tmpfs headroom")
    machine = host()
    original.ready(check_assignment=False)
    bound, request = load_job(TRANSFER.ready / "job.json", TRANSFER.job_pin)
    if bound["case"] != TRANSFER.case or request["native_sha256"] != PACKET_PIN:
        raise ValueError("The fixed case or detector packet changed")
    inventory = json.loads(checked(Path(bound["inventory"]), INVENTORY_PIN))
    manifests = []
    if metadata != METADATA or metadata.resolve(strict=True) != metadata:
        raise ValueError("Require the fixed local signed segment metadata copy")
    manifest_paths = []
    for segment, signed in zip(inventory["segments"], request["manifests"], strict=True):
        folder = Path(segment["path"])
        path = metadata / (segment["scope"] + ".json")
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("Expected a direct local signed manifest file")
        manifest_paths.append(path)
        if signed != [str(folder / "manifest.json"), segment["manifest_digest"]] or path.stat().st_size > 256_000:
            raise ValueError("Require small authenticated copies of the exact original manifest sequence")
        manifests.append(json.loads(checked(path, signed[1].removeprefix("sha256:"))))
    members = member_spans(inventory, manifests)
    native = json.loads(checked(Path(request["native_file"]), PACKET_PIN))
    bind_native(native, request["session"], request["inventory"], DETECTOR, expected="sha256:" + PACKET_PIN)
    derived, scope = project(native, members, canonical_digest)
    if scope["full"]["visits"] != bound["issued"] or scope["full"]["processed_visits"] != bound["admitted"]:
        raise ValueError("The signed full detector ledger and compressed members differ")
    active, donor = donor_sources()
    sources, libraries = original.pinned_sources(), combined.admitted_libraries()
    release = verified_v3(NAMED_V3)
    if donor["sources"] != sources or donor["libraries"] != libraries or donor["installed_release"] != release:
        raise ValueError("The composed science, native libraries or installed release differ from the verified donor")
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    if len(refs) != 51 or sum(ref.byte_size for ref in refs) != TRANSFER.archive_bytes:
        raise ValueError("The original causal catalogue differs")
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries), *manifest_paths])
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts", "routed"):
        (root / name).mkdir()
    for path in (TRANSFER.ready / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), root / "fonts" / path.name)
    packet = root / "restricted-native.json"
    packet.write_bytes(canonical_json_bytes(derived))
    packet_pin = digest(packet)
    kept = scope["retained"]["processed_visits"]
    path = root / "restricted-request.json"
    write(path, restricted_request(request, packet, packet_pin, kept))
    write(root / "routed/binding.json", {"input": restricted_binding(bound, path, packet, packet_pin, kept)})
    checked(FAILED_PREFLIGHT, FAILED_PREFLIGHT_PIN)
    write(root / "members.json", members)
    argv = [str(RELEASE / "venv/bin/python"), "-IB", str(ENTRY)]
    timeout = ["/usr/bin/timeout", "--kill-after=2s"]
    command = [*timeout, "45s", *argv, "worker", str(root)]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    setup, smoke_start, before = clock(began), now(), resource.getrusage(resource.RUSAGE_CHILDREN)
    probe = subprocess.run([*timeout, "15s", *argv, "probe"], env=env, capture_output=True, text=True, check=False)
    smoke, after = clock(smoke_start), resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke["cpu_s"] += after.ru_stime + after.ru_utime - before.ru_stime - before.ru_utime
    book = dict(case=TRANSFER.case, command=command, sources=sources, libraries=libraries,
                protocol_sha256=digest(composed.PROTOCOL), member_trial_sources=frozen_sources(),
                job_sha256=TRANSFER.job_pin, ready_sha256=TRANSFER.ready_pin,
                original_packet_sha256=PACKET_PIN, inventory_sha256=INVENTORY_PIN,
                derived_packet_sha256=packet_pin, derived_request_sha256=digest(path), members_sha256=canonical_digest(members),
                earlier_admission_failure_sha256=FAILED_PREFLIGHT_PIN,
                full_composed_result_sha256=CONTROL_PIN, full_composed_seal_sha256=CONTROL_SEAL,
                original_comparators_sha256=TRANSFER.control_pin, original_comparators_seal_sha256=TRANSFER.seal_pin,
                machine=machine, installed_release=release, resident=cache, tmpfs_free_bytes_at_admission=free,
                archive_bodies=len(refs), archive_bytes=sum(ref.byte_size for ref in refs), setup=setup,
                smoke=dict(clock=smoke, exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr),
                waveform_reads=0, backing_archive_reads=0, planned_candidate_children=1, acquisition=scope, **active)
    write(root / "admission.json", book)
    probe.check_returncode()
    if json.loads(probe.stdout) != dict(composed_ready=True, early_leo_import=False,
                                        guarded_worker_available=True, worker_available=True):
        raise ValueError("Original isolated import smoke failed")
    write(root / "routed/clock.json", measure(command, env, root / "routed/candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("probe", "worker", "launch"))
    parser.add_argument("root", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "probe":
        original_probe()
    elif args.action == "worker":
        worker(args.root)
    else:
        launch(args.root, METADATA)
