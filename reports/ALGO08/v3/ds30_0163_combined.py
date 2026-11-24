"""Run the pinned combined scientific worker on the already staged blind input."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from reports.ALGO08.v3.ds30_0163_blind import CASE, PAIR_PIN, assigned
from reports.ALGO08.v3.nomination_handoff_0419_admission import checked, digest, tmpfs


READY = Path("/dev/shm/leo-v3-ds30-0163-ready01")
READY_PIN = "dfbcde4feb942fc95c2ec8ff9d26fe30fe238bb570413dd03b19b97de11a7cd7"
JOB_SHA = "3b79aefb7f540ec55193a5e54b3ee57cb60f0a27a3371b64c2e5504be15be7d3"
DEVELOPMENT = Path("/dev/shm/leo-v3-combined-successor-0289-01/admission.json")
DEVELOPMENT_PIN = "2eb508f6c61519290e59e55170051daee848ce49fd56303f091046c2ee87b2b0"
LOGGER_SOURCE = "reports/ALGO08/v3/combined_successor_0289.py"
LOGGER_SHA = "8cfcb991ad883f820154834c0c658de903207ba56fda7c3de4e617a36bb481d0"
SCIENCE_COMMIT = "ad319307d"
LOGGER_COMMIT = "d0f399eb1fd673f0fff4c19fb944724d906c805e"


def source_binding(current, previous):
    if (set(current) != set(previous) or current.get(LOGGER_SOURCE) != LOGGER_SHA
            or any(current[name] != previous[name] for name in previous if name != LOGGER_SOURCE)):
        raise ValueError("The candidate differs from the development science or corrected logger")
    return current


def pinned_sources():
    import combined_successor_0289 as combined

    source = checked(tmpfs(DEVELOPMENT), DEVELOPMENT_PIN)
    return source_binding(combined.source_pins(), source["sources"])


def ready():
    book = checked(tmpfs(READY / "admission.json"), READY_PIN)
    if not book["prepared_only"] or book["job_sha256"] != JOB_SHA or book["assignment"] != assigned():
        raise ValueError("The original scope or frozen ready status changed")
    return book


def worker(output):
    import combined_successor_0289 as combined

    ready()
    with patch.multiple(combined, STAGED=READY, JOB_SHA=JOB_SHA):
        combined.worker(output)


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
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = boot.now()
    if output.exists() or resident_path(output.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs output")
    cold = ready()
    machine, release = host(), verified_v3(NAMED_V3)
    if machine != cold["machine"] or release != cold["installed_release"]:
        raise ValueError("Host or installed release changed between admission and launch")
    sources, libraries = pinned_sources(), combined.admitted_libraries()
    bound, request = load_job(READY / "job.json", JOB_SHA)
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"]), *map(Path, libraries)])
    output.mkdir(mode=0o700)
    for name in ("fonts", "tmp", "routed", "installed"):
        (output / name).mkdir()
    for name in ("job.json", "request.json"):
        os.link(resident_path(READY / name), output / name)
    for path in (READY / "fonts").glob("fontlist-*.json"):
        os.link(resident_path(path), output / "fonts" / path.name)
    for mode in ("routed", "installed"):
        write(output / mode / "binding.json", {"input": bound})
    command = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(boot.RELEASE / "venv/bin/python"), "-IB"]
    commands = {
        "routed": [*command, str(Path(__file__).resolve()), "worker", str(output)],
        "installed": [*command, str(HERE / "clean_saved_publication.py"),
                      "installed", str(READY / "job.json"), JOB_SHA, str(output / "installed")],
    }
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT),
                                        "rev-parse", "HEAD"], text=True).strip()
    order = cold["assignment"]["order"]
    write(output / "admission.json", dict(
        case=CASE, assignment=cold["assignment"], sources=sources, libraries=libraries, machine=machine,
        job_sha256=JOB_SHA, ready_admission_sha256=READY_PIN, job_root=str(READY), commands=commands,
        science_commit=SCIENCE_COMMIT, telemetry_commit=LOGGER_COMMIT, controller_commit=revision,
        cold_setup=cold["setup"], cold_archive=cold["archive"], warm_setup=boot.clock(began),
        original_inputs=cold["original_inputs"], resident=cache, installed_release=release,
        detector_waveform_reads=0, original_backing_archive_reads=0,
    ))
    env = environment(output) | {"TMPDIR": str(output / "tmp"), "XDG_CACHE_HOME": str(output / "tmp")}
    for mode in order:
        stage = output / mode
        write(stage / "clock.json", measure(commands[mode], env, stage / "candidate"))
    write(output / "prediction-seal.json", output_seal(output))


def score(output):
    from aperture_trial import read, write
    import empty_bootstrap as boot
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from nomination_handoff_0419_admission import PANEL
    import unseen_saved_holdout_score as ordinary

    started = boot.now()
    panel = PANEL.parent / CASE
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
                if row["dataset_label"] == CASE and row["authority_eligible"]
                and row["sealed_metadata_digests_verified"])
        return [row["latitude_deg"], row["longitude_deg"]]

    def collect(path, data):
        if path != output / "result.json":
            raise ValueError("Unexpected scorer output")
        result.update(data)

    with (patch("aperture_trial.write", collect),
          patch.multiple(ordinary, CASE=CASE, PANEL=panel, ADMITTED=inputs["admitted"], ISSUED=inputs["issued"],
                         NATIVE_PIN=inputs["native_sha256"], runtime_sources=pinned_sources,
                         enrollment=assigned, reference=reference)):
        ordinary.score(output)

    installed = result["jobs"]["installed"]["publication"]
    old = checked(tmpfs(panel / "pair.json"), PAIR_PIN)["runs"]["candidate"]["receipt"]
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
    result["candidate_traces"]["combined-grid.json"] = read(output / "routed/combined-grid.json")
    result["publication_clocks"] = {
        mode: {name: observed[name] for name in ("publication_elapsed_s", "publication_cpu_s", "solve")}
        for mode, job in result["jobs"].items() if job["publication"]
        for observed in (read(output / mode / "candidate/joint-research-receipt.json"),)
    }
    result["paid_setup_and_time"] = {}
    for metric, arms in result["time"].items():
        ready = book["cold_setup"][metric] + book["warm_setup"][metric]
        result["paid_setup_and_time"][metric] = dict(
            combined_setup=ready, installed_with_setup=arms["installed"] + ready,
            candidate_with_setup=arms["routed"] + ready,
            speedup_with_shared_setup=(arms["installed"] + ready) / (arms["routed"] + ready))
    result["study"] = dict(independent_cases=[CASE], previous_combined_development=["DS30-0289"],
                           prediction_scoring=boot.clock(started), original_waveform_reads=0)
    write(output / "result.json", result)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("launch", "worker", "score"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.mode](args.output)
