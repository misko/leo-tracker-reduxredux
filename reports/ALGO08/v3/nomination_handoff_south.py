"""Compare the frozen routed solver to installed v3 on one signed South omission."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
MODES = ("routed", "installed")
ARCHIVE_REFERENCE = Path("/dev/shm/leo-v3-nomination-handoff-0419-local01/admission.json")
ARCHIVE_REFERENCE_SHA = "ef2f3b0367b94b998b7b1eea3d59b925f104b51067e947410241f3f0ffe6a343"
MIRROR = Path("/dev/shm/leo-isolated-south-run01")
MIRROR_REQUEST_SHA = "5920a50abc8aec8956eb2c96b16b21702e2b689000f4d1d4bb2919817c7b6b3d"
FONT_SHA = "07189bbdc3694211155db6c4c6f677b7de06867976a2c4e2d8a57c228cb7688b"
TMPFS_MOUNTS = (Path("/tmp"), Path("/dev/shm"))
PROTOCOL = HERE/"nomination-handoff-south-protocol.md"
CONTROL = Path("/tmp/leo-v3-nomination-offsite-south01")
CONTROL_SEAL = "61a680e4f098c9d3aa3c25b44df87c29063f9d68d1456c4c9b4c7528fb752312"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def staged(path):
    """Allow the two actual RAM mounts, with no links or nested backing devices."""
    mount = next((root for root in TMPFS_MOUNTS if path.is_relative_to(root)), None)
    if (mount is None or path.resolve(strict=True) != path or path.stat().st_dev != mount.stat().st_dev):
        raise ValueError(f"Expected an original direct tmpfs path: {path}")
    return path


def single_segment_manifest(original, request):
    manifests = request["manifests"]
    if len(manifests) == 1 and Path(manifests[0][0]) == Path(request["recording"])/"manifest.json":
        return request
    return original(request)


@contextmanager
def staged_saved_ports():
    import exact_named_route as exact

    # Only extend the physical worker's mount admission. Its own catalogue
    # roster, cutoff, each read, entire inventory and pinned worker stay active.
    with (patch.object(exact, "manifest_paths", partial(single_segment_manifest, exact.manifest_paths)),
          patch.object(exact, "resident_path", staged),
          patch.object(exact, "exact_ports", partial(exact.exact_ports, resident=staged))):
        yield


def source_pins():
    from empty_bootstrap import checked
    from nomination_handoff_0255_publication import remediation_pins

    reference = json.loads(checked(staged(ARCHIVE_REFERENCE), ARCHIVE_REFERENCE_SHA))
    actual = remediation_pins()
    if actual != reference["source_pins"]:
        raise ValueError("Require the 37 exact sources measured on DS30-0419")
    return actual


def enrolled():
    from empty_bootstrap import checked
    from isolated_salvage_south import DETECTOR, INVENTORY_SHA, LIBRARIES, NATIVE_SHA, enrollment
    from leo.operations.tle_archive import TleArchiveReader

    req, inventory, controls = enrollment()
    saved = json.loads(checked(staged(MIRROR/"near-omitted-request.json"), MIRROR_REQUEST_SHA))
    if any(saved[k] != v for k, v in req.items()) or read(staged(Path(saved["offer_file"]))) != controls["near-omitted"]["offer"]:
        raise ValueError("The same authentic 20 ms packet and omitted offer are required")
    archive = staged(Path(req["local_archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    request = dict(saved, case="South near-omitted simulation", issued=1200, admitted=1200,
        original_archive=req["local_archive"], native_sha256=NATIVE_SHA, detector_sha256=DETECTOR,
        local_archive=dict(req["local_archive"], snapshots=len(refs), bytes=sum(ref.byte_size for ref in refs)))
    packets = {str(inventory): INVENTORY_SHA, saved["native_file"]: NATIVE_SHA, saved["offer_file"]: saved["offer_sha256"]}
    packets.update({path: LIBRARIES[k][1] for k, path in saved["local_libraries"].items()})
    for path, sha in packets.items():
        checked(staged(Path(path)), sha)
    return request, inventory, packets, controls


def warm_staged(refs):
    from empty_bootstrap import checked, clock, now
    from visit_frame_raw_0016 import resident

    started = now()
    names = [str(staged(ref.path)) for ref in refs]
    if any(ref.path.stat().st_uid != os.geteuid() for ref in refs):
        raise ValueError("Cache admission must run as the owner of the pre-staged files")
    counters = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,FILE", *names]))["fincore"]
    if set(names) != {row["file"] for row in counters}:
        raise ValueError("The existing tmpfs catalogue census changed")
    needed = {row["file"]: row["size"]-row["res"] for row in counters if row["res"] < row["size"]}
    bodies = [ref for ref in refs if str(ref.path) in needed]
    if sum(body.byte_size for body in bodies) > 5_000_000:
        raise ValueError("Only a bounded recheck of the previously staged RAM bodies is admitted")
    for ref in bodies:
        checked(ref.path, ref.sha256[7:])
    return dict(remaining_page_bytes_before=needed, checked_bytes=sum(ref.byte_size for ref in bodies),
                check=clock(started), residency=resident(names))


def checked_control(root, expected):
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked

    control = json.loads(checked(staged(root/"prediction-seal.json"), CONTROL_SEAL))
    if (control != output_seal(root) or read(root/"request.json") != expected
            or read(root/"installed/clock.json")["exit_code"] != 0
            or "The saved inventory must bind to the original path" not in read(root/"routed/clock.json")["stderr_tail"]
            or (root/"routed/candidate").exists()):
        raise ValueError("Require the exact completed installed control and earlier pre-solve route abort")
    return control


def cache(root):
    from empty_bootstrap import checked
    from isolated_salvage_south import ORIGINAL, PAIR_SHA
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    archive = json.loads(checked(staged(ORIGINAL/"pair.json"), PAIR_SHA))["archive"]
    references = TleArchiveReader(staged(Path(archive["root"]))).list_snapshots("space-track")
    if canonical_digest({r.path.name: r.sha256 for r in references}) != archive["snapshots_sha256"]:
        raise ValueError("The resident owner census must bind the original archive")
    data = dict(archive=archive, **warm_staged(references))
    with root.open("x") as output:
        json.dump(data, output, sort_keys=True, allow_nan=False)


def launch(root, owner_cache, *, retry):
    from empty_bootstrap import RELEASE, clock, now
    from portable_orbit_index_trial import local_launcher_tools

    begin = now()
    local_launcher_tools()
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from exact_named_route import checked_catalogue
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    if root.exists() or staged(root.parent) != Path("/tmp"):
        raise ValueError("Run under a fresh private tmpfs output directory")
    sources = source_pins()
    request, inventory, packets, controls = enrolled()
    bound = dict(case=request["case"], stage=str(root), archive=request["local_archive"]["root"],
                 request=str(root/"request.json"), inventory=str(inventory), issued=1200, admitted=1200,
                 portable=None, packets=packets, sources=sources)
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest, resident=staged)
    residency = read(staged(owner_cache))
    if (residency["archive"] != request["original_archive"] or residency["residency"]["members"] != len(refs)
            or residency["residency"]["bytes"] != sum(ref.byte_size for ref in refs)):
        raise ValueError("Require the measured owner cache check for this exact archive")
    control = checked_control(CONTROL, request) if retry else None
    running = ("routed",) if retry else MODES

    root.mkdir(mode=0o700)
    for name in (*running, "fonts", "tmp"):
        (root/name).mkdir()
    from empty_bootstrap import checked

    font = "fontlist-v3.11.0.json"
    (root/"fonts"/font).write_bytes(checked(staged(MIRROR/"fonts"/font), FONT_SHA))
    write(root/"request.json", request)
    packets[bound["request"]] = digest(root/"request.json")
    job = root/"job.json"
    write(job, dict(binding=bound, original_archive=request["original_archive"]))
    job_sha = digest(job)
    commands = {}
    for mode in running:
        output = root/mode
        write(output/"binding.json", {"input": bound})
        commands[mode] = ["/usr/bin/timeout", "--kill-after=2s", "45s", str(RELEASE/"venv/bin/python"),
                          "-IB", __file__, "worker", str(output), "--mode", mode, "--job-sha256", job_sha]
    write(root/"admission.json", dict(source_pins=sources, job_sha256=job_sha, roles=list(MODES),
          adapter=digest(Path(__file__)), protocol=digest(PROTOCOL), commands=commands, machine=machine,
          archive_residency=residency, owner_cache_sha256=digest(owner_cache), installed_control=str(CONTROL) if control else None,
          installed_control_seal=CONTROL_SEAL if control else None, running=running,
          setup=clock(begin), historical_installed=controls, waveform_reads=0))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    for mode in running:
        output = root/mode
        timing = measure(commands[mode], env, output/"candidate")
        write(output/"clock.json", timing)
    write(root/"prediction-seal.json", output_seal(root))


def worker(mode, output, job_sha):
    from clean_saved_publication import run
    from nomination_handoff_0255_publication import worker as frozen

    root = output.parent
    admission = read(root/"admission.json")
    if admission["adapter"] != digest(Path(__file__)) or admission["protocol"] != digest(PROTOCOL):
        raise ValueError("The timetable or narrow mount adapter changed")
    recording = Path(read(root/"request.json")["recording"])

    def deny_recording(event, arguments):
        if event == "open" and isinstance(arguments[0], (str, bytes)):
            if Path(os.fsdecode(arguments[0])).resolve().is_relative_to(recording):
                raise ValueError("Cannot open the original simulated recording during saved publication")

    sys.addaudithook(deny_recording)
    with staged_saved_ports():
        if mode == "routed":
            frozen(root/"job.json", job_sha, output)
        else:
            run(mode, root/"job.json", job_sha, output)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("cache", "launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--job-sha256")
    parser.add_argument("--owner-cache", type=Path)
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args()
    if args.operation == "worker":
        worker(args.mode, args.root, args.job_sha256)
    elif args.operation == "launch":
        launch(args.root, args.owner_cache, retry=args.retry)
    elif args.operation == "cache":
        cache(args.root)
    else:
        from nomination_handoff_south_score import score

        score(args.root)
