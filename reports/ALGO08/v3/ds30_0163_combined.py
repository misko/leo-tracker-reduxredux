"""Run the pinned combined scientific worker on the already staged blind input."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
from shutil import copytree
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from reports.ALGO08.v3.ds30_0163_blind import CASE, PAIR_PIN, assigned
READY = Path("/dev/shm/leo-v3-ds30-0163-ready01")
READY_PIN = "dfbcde4feb942fc95c2ec8ff9d26fe30fe238bb570413dd03b19b97de11a7cd7"
JOB_SHA = "3b79aefb7f540ec55193a5e54b3ee57cb60f0a27a3371b64c2e5504be15be7d3"
DEVELOPMENT = Path("/dev/shm/leo-v3-combined-successor-0289-01/admission.json")
DEVELOPMENT_PIN = "2eb508f6c61519290e59e55170051daee848ce49fd56303f091046c2ee87b2b0"
LOGGER_SOURCE = "reports/ALGO08/v3/combined_successor_0289.py"
LOGGER_SHA = "8cfcb991ad883f820154834c0c658de903207ba56fda7c3de4e617a36bb481d0"
SCIENCE_COMMIT = "ad319307d"
LOGGER_COMMIT = "d0f399eb1fd673f0fff4c19fb944724d906c805e"
FIRST = Path("/dev/shm/leo-v3-combined-0163-blind01")
FIRST_ADMISSION = "60893a0fa73b7439a741f9f5ee4e46c2d3c80b6d8dac87d790e8f813b7f2b7b2"
FIRST_SEAL = "12b00b10289013a825d5a9c2eb35e2adc81931d7d16b047c15cb22ea335673ab"
FAILED_CLOCK = "9c157d201e72790e9bd81753685c47d938c9d7c700eea76128e678ea35bcd7c0"
INSTALLED_CLOCK = "30f99fb8fe9630246db9721aa350576506dd1fef69e03dbabd0e1f2eb98e7e6d"


def source_binding(current, previous):
    if (set(current) != set(previous) or current.get(LOGGER_SOURCE) != LOGGER_SHA
            or any(current[name] != previous[name] for name in previous if name != LOGGER_SOURCE)):
        raise ValueError("The candidate differs from the development science or corrected logger")
    return current


def pinned_sources():
    import combined_successor_0289 as combined
    from reports.ALGO08.v3.nomination_handoff_0419_admission import checked, tmpfs

    source = checked(tmpfs(DEVELOPMENT), DEVELOPMENT_PIN)
    return source_binding(combined.source_pins(), source["sources"])


def ready(*, check_assignment=True, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_SHA, assign=assigned):
    path = job_root / "admission.json"
    if job_root.parent != Path("/dev/shm") or path.resolve(strict=True) != path:
        raise ValueError("The prepared admission traversed a symlink")
    body = path.read_bytes()
    if sha256(body).hexdigest() != admission_pin:
        raise ValueError("The prepared admission bytes changed")
    book = json.loads(body)
    if (not book["prepared_only"] or book["job_sha256"] != job_pin
            or (check_assignment and book["assignment"] != assign())):
        raise ValueError("The original scope or frozen ready status changed")
    return book


def worker(output, *, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_SHA):
    import combined_successor_0289 as combined

    ready(check_assignment=False, job_root=job_root, admission_pin=admission_pin, job_pin=job_pin)
    with patch.multiple(combined, STAGED=job_root, JOB_SHA=job_pin):
        combined.worker(output)


def probe(*, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_SHA):
    import combined_successor_0289
    import solver_exception_live

    ready(check_assignment=False, job_root=job_root, admission_pin=admission_pin, job_pin=job_pin)
    if "leo" in sys.modules:
        raise ValueError("The candidate adapter loaded a local scientific package before installed bootstrap")
    return dict(worker_available=callable(combined_successor_0289.worker),
                guarded_worker_available=callable(solver_exception_live.worker), early_leo_import=False)


def launch(output):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    import combined_successor_0289 as combined
    from dense_geographic_trial import host
    import empty_bootstrap as boot
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from reports.ALGO08.v3.nomination_handoff_0419_admission import checked, tmpfs
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = boot.now()
    if output.exists() or resident_path(output.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    cold = ready()
    first = checked(tmpfs(FIRST / "admission.json"), FIRST_ADMISSION)
    seal = checked(tmpfs(FIRST / "prediction-seal.json"), FIRST_SEAL)
    failed = checked(tmpfs(FIRST / "routed/clock.json"), FAILED_CLOCK)
    installed = checked(tmpfs(FIRST / "installed/clock.json"), INSTALLED_CLOCK)
    if (seal != output_seal(FIRST) or first["job_sha256"] != JOB_SHA or failed["exit_code"] != 1
            or (FIRST / "routed/candidate").exists() or installed["exit_code"]):
        raise ValueError("Expected the sealed import-only failure and the one original installed exit")
    machine, release = host(), verified_v3(NAMED_V3)
    if machine != cold["machine"] or release != cold["installed_release"]:
        raise ValueError("Host or installed release changed between admission and launch")
    sources, libraries = pinned_sources(), combined.admitted_libraries()
    bound, request = load_job(READY / "job.json", JOB_SHA)
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries)])
    output.mkdir(mode=0o700)
    for name in ("fonts", "tmp", "routed"):
        (output / name).mkdir()
    copytree(FIRST / "installed", output / "installed", copy_function=os.link)
    for name in ("job.json", "request.json"):
        os.link(resident_path(READY / name), output / name)
    for path in (READY / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), output / "fonts" / path.name)
    write(output / "routed/binding.json", {"input": bound})
    command = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(boot.RELEASE / "venv/bin/python"), "-IB"]
    commands = {
        "routed": [*command, str(Path(__file__).resolve()), "worker", str(output)],
        "installed": first["commands"]["installed"],
    }
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT),
                                        "rev-parse", "HEAD"], text=True).strip()
    write(output / "admission.json", dict(
        case=CASE, assignment=cold["assignment"], sources=sources, libraries=libraries, machine=machine,
        job_sha256=JOB_SHA, ready_admission_sha256=READY_PIN, job_root=str(READY), commands=commands,
        science_commit=SCIENCE_COMMIT, telemetry_commit=LOGGER_COMMIT, controller_commit=revision,
        cold_setup=cold["setup"], cold_archive=cold["archive"], warm_setup=boot.clock(began),
        first_setup=first["warm_setup"], failed_start=failed, first_seal_sha256=FIRST_SEAL,
        installed_clock_sha256=INSTALLED_CLOCK, actual_worker_order=["installed", "routed"],
        original_inputs=cold["original_inputs"], resident=cache, installed_release=release,
        detector_waveform_reads=0, original_backing_archive_reads=0,
    ))
    env = environment(output) | {"TMPDIR": str(output / "tmp"), "XDG_CACHE_HOME": str(output / "tmp")}
    stage = output / "routed"
    write(stage / "clock.json", measure(commands["routed"], env, stage / "candidate"))
    write(output / "prediction-seal.json", output_seal(output))


def check_entries(probes, env):
    import empty_bootstrap as boot

    checks = {}
    for mode, command in probes.items():
        started = boot.now()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        child = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        clock = boot.clock(started)
        checks[mode] = dict(argv=command, exit_code=child.returncode, stdout=child.stdout, stderr=child.stderr,
                            elapsed_s=clock["elapsed_s"], cpu_s=after.ru_utime + after.ru_stime
                            - before.ru_utime - before.ru_stime)
    routed, installed = checks["routed"], checks["installed"]
    passed = False
    if routed["exit_code"] == installed["exit_code"] == 0:
        try:
            passed = (json.loads(routed["stdout"]) == {
                "early_leo_import": False, "guarded_worker_available": True, "worker_available": True}
                and "job_sha256" in installed["stdout"] and "installed" in installed["stdout"])
        except json.JSONDecodeError:
            pass
    return checks, passed


def launch_fresh(output, *, job_root, assign):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    import combined_successor_0289 as combined
    from dense_geographic_trial import host
    import empty_bootstrap as boot
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = boot.now()
    if output.exists() or resident_path(output.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    job_root = resident_path(job_root)
    admission_pin = sha256((job_root / "admission.json").read_bytes()).hexdigest()
    job_pin = sha256((job_root / "job.json").read_bytes()).hexdigest()
    cold = ready(job_root=job_root, admission_pin=admission_pin, job_pin=job_pin, assign=assign)
    machine, release = host(), verified_v3(NAMED_V3)
    if machine != cold["machine"] or release != cold["installed_release"]:
        raise ValueError("Host or installed release changed between admission and launch")
    sources, libraries = pinned_sources(), combined.admitted_libraries()
    bound, request = load_job(job_root / "job.json", job_pin)
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries)])
    output.mkdir(mode=0o700)
    for name in ("fonts", "tmp", "routed", "installed"):
        (output / name).mkdir()
    for name in ("job.json", "request.json"):
        os.link(resident_path(job_root / name), output / name)
    for path in (job_root / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), output / "fonts" / path.name)
    for mode in ("routed", "installed"):
        write(output / mode / "binding.json", {"input": bound})
    executable = [str(boot.RELEASE / "venv/bin/python"), "-IB"]
    argv = {"routed": [*executable, str(Path(__file__).resolve())],
            "installed": [*executable, str(HERE / "clean_saved_publication.py")]}
    flags = ["--job-root", str(job_root), "--admission-sha256", admission_pin, "--job-sha256", job_pin]
    prefix = ["/usr/bin/timeout", "--kill-after=2s"]
    commands = {
        "routed": [*prefix, "115s", *argv["routed"], "worker", str(output), *flags],
        "installed": [*prefix, "115s", *argv["installed"], "installed", str(job_root / "job.json"),
                      job_pin, str(output / "installed")],
    }
    env = environment(output) | {"TMPDIR": str(output / "tmp"), "XDG_CACHE_HOME": str(output / "tmp")}
    probes = {"routed": [*prefix, "15s", *argv["routed"], "probe", *flags],
              "installed": [*prefix, "15s", *argv["installed"], "--help"]}
    audits, passed = check_entries(probes, env)
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT),
                                        "rev-parse", "HEAD"], text=True).strip()
    assignment, warm = cold["assignment"], boot.clock(began)
    warm["cpu_s"] += sum(audit["cpu_s"] for audit in audits.values())
    order = assignment["order"]
    write(output / "admission.json", dict(
        case=assignment["case"], assignment=assignment, sources=sources, libraries=libraries, machine=machine,
        job_sha256=job_pin, ready_admission_sha256=admission_pin, job_root=str(job_root), commands=commands,
        science_commit=SCIENCE_COMMIT, telemetry_commit=LOGGER_COMMIT, controller_commit=revision,
        cold_setup=cold["setup"], cold_archive=cold["archive"], warm_setup=warm,
        original_inputs=cold["original_inputs"], resident=cache, installed_release=release,
        import_smoke=audits, smoke_passed=passed, actual_worker_order=order if passed else [],
        detector_waveform_reads=0, original_backing_archive_reads=0,
    ))
    if not passed:
        raise ValueError("At least one isolated entry failed smoke; no measured child launched")
    for mode in order:
        stage = output / mode
        write(stage / "clock.json", measure(commands[mode], env, stage / "candidate"))
    write(output / "prediction-seal.json", output_seal(output))


def score(output, *, assign=assigned, case=CASE, pair_pin=PAIR_PIN, reduce_pool=None):
    from aperture_trial import read, write
    import empty_bootstrap as boot
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from nomination_handoff_0419_admission import PANEL
    from reports.ALGO08.v3.nomination_handoff_0419_admission import checked, digest, tmpfs
    import unseen_saved_holdout_score as ordinary

    started = boot.now()
    panel = PANEL.parent / case
    book = read(output / "admission.json")
    inputs = book["original_inputs"]
    result = {}

    def reference():
        body = subprocess.check_output([
            "git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
            "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
        if digest(body) != ordinary.REFERENCE_PIN:
            raise ValueError("The sealed independent reference changed")
        row, = (row["reference"] for row in json.loads(body)["cases"]
                if row["dataset_label"] == case and row["authority_eligible"]
                and row["sealed_metadata_digests_verified"])
        return [row["latitude_deg"], row["longitude_deg"]]

    def collect(path, data):
        if path != output / "result.json":
            raise ValueError("Unexpected scorer output")
        result.update(data)

    with (patch("aperture_trial.write", collect),
          patch.multiple(ordinary, CASE=case, PANEL=panel, ADMITTED=inputs["admitted"], ISSUED=inputs["issued"],
                         NATIVE_PIN=inputs["native_sha256"], runtime_sources=pinned_sources,
                         enrollment=assign, reference=reference)):
        ordinary.score(output)

    installed = result["jobs"]["installed"]["publication"]
    old = checked(tmpfs(panel / "pair.json"), pair_pin)["runs"]["candidate"]["receipt"]
    historical = tmpfs(panel / "candidate")
    baseline = artifacts(historical, old)
    media = {"equal_pngs": bool(installed) and baseline["images"] == installed["figures"]}
    if result["jobs"]["installed"]["decision"] == old["decision"] == "complete":
        origin, repeated = (FastStandardAnalysisStore(folder)
                            for folder in (historical, output / "installed/candidate"))
        for name in ("grid", "path"):
            earlier = getattr(origin, "position_" + name)(old["run_id"])
            fresh = getattr(repeated, "position_" + name)(old["run_id"])
            earlier.pop("elapsed_seconds", None)
            fresh.pop("elapsed_seconds", None)
            media["equal_" + name] = earlier == fresh
    result["historical_installed_products"] = media
    grid_audit = output / "routed/combined-grid.json"
    result["candidate_traces"]["combined-grid.json"] = read(grid_audit) if grid_audit.exists() else None
    result["publication_clocks"] = {
        mode: {name: observed[name] for name in ("publication_elapsed_s", "publication_cpu_s", "solve")}
        for mode, job in result["jobs"].items() if job["publication"]
        for observed in (read(output / mode / "candidate/joint-research-receipt.json"),)
    }
    result["paid_setup_and_time"] = {}
    for metric, arms in result["time"].items():
        ready = book["cold_setup"][metric] + book["warm_setup"][metric] + book.get("first_setup", {}).get(metric, 0)
        result["paid_setup_and_time"][metric] = dict(
            combined_setup=ready, installed_with_setup=arms["installed"] + ready,
            candidate_with_setup=arms["routed"] + ready,
            failed_start=book.get("failed_start", {}).get(metric, 0),
            speedup_with_shared_setup=(arms["installed"] + ready) / (arms["routed"] + ready))
    result["study"] = dict(independent_cases=[case], previous_combined_development=["DS30-0289"],
                           prediction_scoring=boot.clock(started), original_waveform_reads=0)
    if reduce_pool is not None:
        result["combined_independent_pool"] = reduce_pool(result)
    write(output / "result.json", result)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker", "score", "probe"))
    cli.add_argument("output", nargs="?", type=Path)
    cli.add_argument("--job-root", type=Path, default=READY)
    cli.add_argument("--admission-sha256", default=READY_PIN)
    cli.add_argument("--job-sha256", default=JOB_SHA)
    args = cli.parse_args()
    job = dict(job_root=args.job_root, admission_pin=args.admission_sha256, job_pin=args.job_sha256)
    if args.mode == "probe" and args.output is None:
        print(json.dumps(probe(**job), sort_keys=True))
    elif args.mode == "worker" and args.output is not None:
        worker(args.output, **job)
    elif args.mode != "probe" and args.output is not None:
        {"launch": launch, "score": score}[args.mode](args.output)
    else:
        cli.error("A study output is required except for the isolated import probe")
