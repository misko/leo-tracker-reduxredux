"""Admit the original DS30-0419 inputs from the local collector and time the frozen pair."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from shutil import copytree, disk_usage
import stat
from statistics import median
import subprocess
import sys
from unittest.mock import patch

from reports.ALGO08.v3.nomination_handoff_0419_admission import (
    CASE, HOUR_NS, OFFER, OFFER_PIN, PAIR_PIN, PANEL, checked, digest, enrollment, input_binding, tmpfs,
)
from leo.contracts.digests import canonical_digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COLLECTOR = Path("/var/lib/leo/tle/archive/space-track")
COLLECTOR_DEVICE = 64512
MAX_ARCHIVE_BYTES = 100_000_000
HANDOFF_RESULT = Path("/dev/shm/leo-v3-nomination-handoff-0255-result01/result.json")
HANDOFF_RESULT_PIN = "192ee623532d238f589737a46d0472ec6ddd11fa14aa109468236426b45278ec"
FILENAME = re.compile(r"([0-9]{1,19})-([0-9a-f]{64})\.tle\Z")


def collector_roster(folder, device, capture_ns, cutoff_ns, expected, *, limit=MAX_ARCHIVE_BYTES):
    if folder.resolve(strict=True) != folder or folder.stat().st_dev != device:
        raise ValueError("The local collector path changed devices or traverses a symlink")
    roster = []
    with os.scandir(folder) as entries:
        for entry in entries:
            match = FILENAME.fullmatch(entry.name)
            if match is None or not capture_ns - 72 * HOUR_NS <= int(match[1]) < cutoff_ns:
                continue
            info = entry.stat(follow_symlinks=False)
            if info.st_dev != device or not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Unexpected collector file identity: {entry.name}")
            roster.append((entry.name, match[2], info.st_size, info.st_ino))
    actual = canonical_digest({name: pin for name, pin, _, _ in roster})
    if actual != expected:
        raise ValueError(f"Collector roster differs from original: {len(roster)} files, {actual}, expected {expected}")
    size = sum(row[2] for row in roster)
    if not 0 < size <= limit:
        raise ValueError(f"The verified catalogue exceeds the staging budget: {size} bytes")
    return sorted(roster), size


def copy_archive(source, destination, roster, device):
    destination.mkdir(parents=True)
    folder = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(folder).st_dev != device:
            raise ValueError("Collector directory moved")
        for name, expected, size, inode in roster:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino, info.st_size) != (device, inode, size) or not stat.S_ISREG(info.st_mode):
                    raise ValueError(f"Collector file changed after roster check: {name}")
                body = stream.read(size + 1)
            if len(body) != size or digest(body) != expected:
                raise ValueError(f"Collector body failed its signed hash: {name}")
            (destination / name).write_bytes(body)
    finally:
        os.close(folder)


def assigned():
    assignment = enrollment()
    return assignment | {"order": assignment["planned_order"], "archived_pair_sha256": PAIR_PIN}


def nvme_read_bytes():
    return int(next(line.split()[1] for line in Path("/proc/self/io").read_text().splitlines()
                    if line.startswith("read_bytes:")))


def launch(root, *, assign=assigned, execute=True, expected_inputs=None, resident_refs=None):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    import empty_bootstrap as boot
    from full_short_physical import environment
    from nomination_handoff_0255 import BASE, saved
    from nomination_handoff_0255_publication import remediation_pins
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if (root.exists() or root.parent != Path("/dev/shm") or root.parent.resolve() != root.parent
            or disk_usage(root.parent).free < 350_000_000):
        raise ValueError("Require a fresh private tmpfs root with room for archive and both publications")
    machine = host()
    assignment = assign()
    if not 0 < assignment["estimated_worker_ceiling_s"] < 120:
        raise ValueError("The originally frozen worker timing budget was exceeded")
    pins = remediation_pins()
    old = checked(tmpfs(HANDOFF_RESULT), HANDOFF_RESULT_PIN)
    if old["admission"]["source_pins"] != pins:
        raise ValueError("The post-holdout candidate source changed")
    release = verified_v3(NAMED_V3)
    case = assignment["case"]
    panel = PANEL.parent / case
    pair = checked(tmpfs(panel / "pair.json"), assignment["release_pair_sha256"])
    bound = input_binding(pair, panel)
    offer = boot.checked(Path(pair["region"]), OFFER_PIN)
    if offer != boot.checked(tmpfs(OFFER), OFFER_PIN):
        raise ValueError("The original installed offer and resident offer differ")
    nominal = "-".join(Path(pair["recording"]).name.split("-")[2:4])
    capture_ns = int(datetime.strptime(nominal, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()) * 10**9
    expected = pair["archive"]["snapshots_sha256"]
    observed_inputs = bound | {"archive_sha256": expected,
                               "frozen_specification": release["frozen_specification"]}
    if expected_inputs and any(observed_inputs.get(key) != value for key, value in expected_inputs.items()):
        raise ValueError("Admitted data differs from the frozen input metadata")
    roster_start = boot.now()
    if resident_refs is None:
        roster, size = collector_roster(COLLECTOR, COLLECTOR_DEVICE, capture_ns, bound["cutoff_utc_ns"], expected)
        archive_source, archive_device = str(COLLECTOR), COLLECTOR_DEVICE
    else:
        refs = resident_refs(capture_ns, bound["cutoff_utc_ns"], expected)
        names = {ref.path.name: ref.sha256 for ref in refs}
        if len(names) != len(refs) or canonical_digest(names) != expected:
            raise ValueError("The signed existing tmpfs roster differs")
        roster = [(ref.path.name, ref.sha256, ref.byte_size, None) for ref in refs]
        size = sum(row[2] for row in roster)
        if not 0 < size <= MAX_ARCHIVE_BYTES:
            raise ValueError("The signed existing tmpfs roster exceeds the archive cap")
        archive_source, archive_device = "existing tmpfs hard links", root.parent.stat().st_dev
    roster_clock = boot.clock(roster_start)

    root.mkdir(mode=0o700)
    local = root / "tle"
    archive = local / "archive/space-track"
    copying = boot.now()
    before_read_bytes = nvme_read_bytes()
    if resident_refs is None:
        copy_archive(COLLECTOR, archive, roster, COLLECTOR_DEVICE)
    else:
        archive.mkdir(parents=True)
        for ref in refs:
            path = tmpfs(ref.path)
            if not path.is_relative_to(root.parent) or path.stat().st_dev != archive_device:
                raise ValueError("Unexpected source outside the ready tmpfs device")
            body = boot.checked(path, ref.sha256)
            if len(body) != ref.byte_size:
                raise ValueError("The signed local body extent changed")
            os.link(path, archive / path.name, follow_symlinks=False)
    copy_clock = boot.clock(copying)
    backing_bytes = nvme_read_bytes() - before_read_bytes
    availability = resident([archive / row[0] for row in roster])

    previous = saved()
    prior_job = checked(tmpfs(BASE / "job.json"), previous["admission"]["job_sha256"])["binding"]
    prior_request = checked(tmpfs(Path(prior_job["request"])), prior_job["packets"][prior_job["request"]])
    files = {name: root / f"{name}.json" for name in ("native", "inventory", "offer")}
    for name in ("native", "inventory"):
        files[name].write_bytes(boot.checked(tmpfs(Path(bound[f"{name}_path"])), bound[f"{name}_sha256"]))
    files["offer"].write_bytes(offer)
    inventory = json.loads(files["inventory"].read_bytes())
    manifests = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    request = prior_request | dict(
        case=case, session=bound["session"], inventory="sha256:" + bound["inventory_sha256"],
        issued=bound["issued"], admitted=bound["admitted"], raw_authority=bound["raw_authority"],
        causal_cutoff_utc_ns=bound["cutoff_utc_ns"], recording=pair["recording"], manifests=manifests,
        native_file=str(files["native"]), native_sha256=bound["native_sha256"], offer_file=str(files["offer"]),
        offer_sha256=OFFER_PIN, original_archive=pair["archive"],
        local_archive=dict(root=str(local), snapshots_sha256=expected, snapshots=len(roster), bytes=size))
    request_file = root / "request.json"
    write(request_file, request)
    libraries = request["local_libraries"].values()
    for name in libraries:
        boot.checked(tmpfs(Path(name)), prior_job["packets"][name])
    packets = {str(path): digest(path.read_bytes()) for path in (*files.values(), request_file)}
    packets.update({name: prior_job["packets"][name] for name in libraries})
    binding = dict(case=case, stage=str(root), archive=str(local), request=str(request_file),
                   inventory=str(files["inventory"]), issued=bound["issued"], admitted=bound["admitted"],
                   portable=None, packets=packets, sources=pins)
    job = root / "job.json"
    write(job, dict(binding=binding, original_archive=pair["archive"]))
    job_pin = digest(job.read_bytes())
    (root / "tmp").mkdir()
    copytree(BASE / "fonts", root / "fonts")
    commands = {}
    for mode in assignment["order"]:
        target = root / mode
        target.mkdir()
        write(target / "binding.json", {"input": binding})
        prefix = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(boot.RELEASE / "venv/bin/python"), "-IB"]
        if mode == "routed":
            commands[mode] = [*prefix, str(HERE / "nomination_handoff_0255_publication.py"),
                              "worker", str(target), str(job), job_pin]
        else:
            commands[mode] = [*prefix, str(HERE / "clean_saved_publication.py"),
                              "installed", str(job), job_pin, str(target)]
    write(root / "admission.json", dict(
        assignment=assignment, source_pins=pins, sources=pins, job_sha256=job_pin, original_inputs=bound,
        setup=boot.clock(started), archive=dict(
            source=archive_source, device=archive_device, filename_roster_sha256=expected,
            nominal_capture_ns=capture_ns, snapshots=len(roster), bytes=size, charged_io_bytes=backing_bytes,
            new_archive_payload_copies=0 if resident_refs is not None else size,
            metadata_clock=roster_clock, verified_copy_clock=copy_clock, staged_residency=availability,
            names=[{"filename": name, "sha256": pin, "bytes": count} for name, pin, count, _ in roster]),
        commands=commands, installed_release=release, machine=machine, detector_waveform_reads=0,
        controller_commit=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        original_backing_archive_reads=0, use_live_orbit_support=True, portable=None,
        prepared_only=not execute))
    if not execute:
        return
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    for mode in assignment["order"]:
        target = root / mode
        write(target / "clock.json", measure(commands[mode], env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


def score(root, *, assign=assigned, previous_blind=None, pool_blind=None):
    import unseen_saved_holdout_score as known
    from aperture_trial import write
    import empty_bootstrap as boot
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from nomination_handoff_0255_publication import remediation_pins

    started = boot.now()
    admission = json.loads((root / "admission.json").read_bytes())
    row = admission["original_inputs"]
    assignment = assign()
    case = assignment["case"]
    panel = PANEL.parent / case
    result = {}

    def reference():
        body = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
                                        "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
        if digest(body) != known.REFERENCE_PIN:
            raise ValueError("The previously sealed reference changed")
        (reference_row,) = (p for p in json.loads(body)["cases"] if p["dataset_label"] == case
                   and p["authority_eligible"] and p["sealed_metadata_digests_verified"])
        return [reference_row["reference"][key] for key in ("latitude_deg", "longitude_deg")]

    def collect(path, value):
        if path != root / "result.json":
            raise ValueError("Unexpected scorer output")
        result.update(value)

    with (patch("aperture_trial.write", collect),
          patch.multiple(known, CASE=case, PANEL=panel, ADMITTED=row["admitted"], ISSUED=row["issued"],
                         NATIVE_PIN=row["native_sha256"], runtime_sources=remediation_pins,
                         enrollment=assign, reference=reference)):
        known.score(root)

    original = checked(tmpfs(panel / "pair.json"), assignment["release_pair_sha256"])["runs"]["candidate"]
    historical, fresh = panel / "candidate", root / "installed/candidate"
    evidence = artifacts(tmpfs(historical), original["receipt"])
    installed = result["jobs"]["installed"]["publication"]
    result["archived_installed_products"] = dict(figures=evidence["images"], equal_pngs=(
        evidence["images"] == installed["figures"] if installed else None))
    if installed and result["jobs"]["installed"]["decision"] == original["receipt"]["decision"] == "complete":
        run = original["receipt"]["run_id"]
        archived, repeated = (FastStandardAnalysisStore(folder) for folder in (historical, fresh))
        for name in ("grid", "path"):
            a = getattr(archived, "position_" + name)(run)
            b = getattr(repeated, "position_" + name)(run)
            a.pop("elapsed_seconds", None)
            b.pop("elapsed_seconds", None)
            result["archived_installed_products"][f"equal_{name}"] = a == b
    result["publication_clocks"] = {
        mode: {key: saved_report[key] for key in ("publication_elapsed_s", "publication_cpu_s", "solve")}
        for mode, report in result["jobs"].items() if report["publication"]
        for saved_report in (json.loads((root / mode / "candidate/joint-research-receipt.json").read_bytes()),)}
    previous = checked(tmpfs(HANDOFF_RESULT), HANDOFF_RESULT_PIN)
    if previous_blind is None:
        result["cumulative_development_and_blind"] = {
            metric: pooled(previous["controls"]["installed"][metric], previous["clock"][metric],
                           timing["installed"], timing["routed"], admission["setup"][metric])
            for metric, timing in result["time"].items()
        }
    else:
        result["independent_pool"] = pool_blind(previous_blind, result)
        result["development_only"] = dict(case="DS30-0255", installed=previous["controls"]["installed"],
                                          routed=previous["clock"], geographic=previous["original_geographic"])
    result["study_scope"] = dict(
        frozen_development_cases=["DS30-0255"], blind_cases=(
            [case] if previous_blind is None else [previous_blind["case"], case]),
        new_waveform_reads=0, production_changes=0, timed_runtime_source=admission.get(
            "controller_commit", "76b28b6ebfd911a67ac1fc48f9127ced05eecae9"),
        release_handoff_source="3a49c5f1241f935d30f3348eed77c8d3c7e4a919",
        new_scoring_clock=boot.clock(started))
    write(root.with_name(root.name + "-comparison.json"), result)


def pooled(dev_named, dev_routed, blind_named, blind_routed, common_admission):
    named = dev_named + blind_named
    routed = dev_routed + blind_routed
    return dict(combined_named=named, combined_routed=routed, summed_speedup=named / routed,
                median_paired_speedup=1 / median((dev_routed / dev_named, blind_routed / blind_named)),
                blind_speedup_shared_admission=(blind_named + common_admission) / (blind_routed + common_admission),
                blind_speedup_candidate_only_admission=blind_named / (blind_routed + common_admission))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    opts = cli.parse_args()
    (launch if opts.action == "launch" else score)(opts.root)
