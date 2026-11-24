"""Refresh the installed DS30-0359 saved clock on the same authenticated job."""

import argparse
import json
from pathlib import Path
import resource
from shutil import copytree
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from ds30_0359_cairo_saved import BASE, JOB_PIN, PRIOR_PIN, READY, READY_PIN, SEAL_PIN, digest, read

PROTOCOL = HERE / "ds30-0359-installed-control-protocol.md"
CANDIDATE = Path("/dev/shm/leo-v3-0359-composed-saved-result01")
CANDIDATE_PIN = "8cf7d2053ae88597c390739990c849e33c755412d86303eafd7cae5170251166"


def compare_cost(candidate, installed, installed_setup, shared):
    result = {}
    for metric in ("elapsed_s", "cpu_s"):
        a, b = candidate["clock"][metric], installed[metric]
        a_setup, b_setup = candidate["cost"][metric]["setup"], installed_setup[metric]
        a_charged, b_charged = a + a_setup, b + b_setup
        result[metric] = dict(candidate=a, installed=b, through_exit_ratio=b/a,
                              candidate_setup=a_setup, installed_setup=b_setup,
                              candidate_admission_charged=a_charged, installed_admission_charged=b_charged,
                              admission_charged_ratio=b_charged/a_charged,
                              shared_original_local_setup=shared[metric],
                              ratio_with_shared_original_setup=(b_charged+shared[metric])/(a_charged+shared[metric]))
    return result


def launch(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from empty_bootstrap import checked, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    started = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs installed output")
    archived = json.loads(checked(BASE / "result.json", PRIOR_PIN))
    candidate = json.loads(checked(CANDIDATE / "result.json", CANDIDATE_PIN))
    if (not candidate["qualified"] or candidate["prediction_sha256"] != digest(CANDIDATE / "prediction-seal.json")
            or read(CANDIDATE / "prediction-seal.json") != output_seal(CANDIDATE)
            or read(BASE / "prediction-seal.json") != output_seal(BASE)
            or digest(BASE / "prediction-seal.json") != SEAL_PIN):
        raise ValueError("Need the immutable completed candidate and historical controls")
    prior = archived["admission"]
    machine, release = host(), verified_v3(NAMED_V3)
    if (machine != prior["machine"] or machine != candidate["admission"]["machine"]
            or release != prior["installed_release"] or release != candidate["admission"]["installed_release"]):
        raise ValueError("The paired installed patch level or host configuration changed")
    original.ready(check_assignment=False, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    bound, req = load_job(resident_path(READY / "job.json"), JOB_PIN)
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    if len(refs) != 47 or sum(ref.byte_size for ref in refs) != 83_998_561:
        raise ValueError("The exact staged causal archive changed")
    cache = resident([*(ref.path for ref in refs), *map(Path, bound["packets"])])
    path = HERE / "clean_saved_publication.py"
    argv = list(prior["commands"]["installed"])
    if Path(argv[5]).name != path.name or argv[6:9] != ["installed", str(READY / "job.json"), JOB_PIN]:
        raise ValueError("The historical installed invocation does not bind this same job")
    source = digest(path)
    if digest(Path(argv[5])) != source:
        raise ValueError("The same saved controller must invoke the unchanged installed route")
    argv[5], argv[-1] = str(path), str(root / "installed")
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    (root / "installed").mkdir()
    copytree(BASE / "fonts", root / "fonts")
    write(root / "installed/binding.json", {"input": bound})
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    setup = clock(started)
    startup, usage = now(), resource.getrusage(resource.RUSAGE_CHILDREN)
    help_result = subprocess.run([*argv[:2], "15s", *argv[3:6], "--help"], env=env, capture_output=True, text=True, check=False)
    smoke = clock(startup)
    end = resource.getrusage(resource.RUSAGE_CHILDREN)
    smoke["cpu_s"] += end.ru_stime + end.ru_utime - usage.ru_stime - usage.ru_utime
    write(root / "admission.json", dict(command=argv, source_sha256=source, commit=revision, protocol_sha256=digest(PROTOCOL),
          job_sha256=JOB_PIN, candidate_sha256=CANDIDATE_PIN, original_control_sha256=PRIOR_PIN, machine=machine,
          installed_release=release, resident=cache, setup=setup, smoke=smoke, help_exit=help_result.returncode,
          help_stdout=help_result.stdout, help_stderr=help_result.stderr, waveform_reads=0, installed_children=1))
    help_result.check_returncode()
    paid = measure(argv, env, root / "installed/candidate")
    write(root / "installed/clock.json", paid)
    write(root / "prediction-seal.json", output_seal(root))


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from empty_bootstrap import checked
    from prospective_0316_solver import inspect
    from reports.ALGO08.v3.ds30_0359_predictive_score import image_identity

    seal = root / "prediction-seal.json"
    if read(seal) != output_seal(root):
        raise ValueError("The fresh installed prediction changed")
    archived = json.loads(checked(BASE / "result.json", PRIOR_PIN))
    candidate = json.loads(checked(CANDIDATE / "result.json", CANDIDATE_PIN))
    clock, admission = read(root / "installed/clock.json"), read(root / "admission.json")
    order = [candidate["clock"]["started_unix_ns"], clock["started_unix_ns"]]
    if order[0] >= order[1] or not candidate["qualified"]:
        raise ValueError("Expected the qualified clean candidate first, then the fresh installed worker")
    result = dict(qualified=False, case="DS30-0359", prediction_sha256=digest(seal), clock=clock, admission=admission,
                  candidate_first=True, chronological_starts=order, waveform_reads=0, measured_installed_children=1)
    if clock["exit_code"]:
        write(root / "result.json", result | {"status": "failed"})
        return
    directory = root / "installed/candidate"
    bound, req = load_job(READY / "job.json", JOB_PIN)
    receipt = read(directory / "worker.json")["receipt"]
    current = inspect(directory, "fresh-installed", receipt, clock, req, native_sha=req["native_sha256"],
                      windows=bound["issued"], admitted=bound["admitted"], audit_name="worker.json")
    old = archived["jobs"]["installed"]["publication"]
    images = image_identity(old["figures"], current["figures"])
    checks = dict(terminal=old["terminal"] == current["terminal"],
                  calibration=old["science"]["arms"] == current["science"]["arms"],
                  owners=old["selected_rows"] == current["selected_rows"] and all(len(rows) == 3640 for rows in current["selected_rows"].values()),
                  grid=old["sidecars"]["grid"] == current["sidecars"]["grid"],
                  path=old["sidecars"]["path"] == current["sidecars"]["path"], figures=len(images) == 8 and all(images.values()),
                  candidate_matches_actual_arms=candidate["candidate"]["science"]["arms"] == current["science"]["arms"])
    overhead = {key: admission["setup"][key] + admission["smoke"][key] for key in ("elapsed_s", "cpu_s")}
    phases = read(directory / "joint-research-receipt.json")
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks, images=images,
          installed=current, historical_clock=archived["jobs"]["installed"]["clock"], candidate_clock=candidate["clock"],
          cost=compare_cost(candidate, clock, overhead, archived["admission"]["cold_setup"]),
          publication={key: phases[key] for key in ("publication_cpu_s", "publication_elapsed_s", "solve")},
          previous_publication=archived["publication_clocks"], candidate_publication=candidate["publication"]))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    (launch if args.action == "launch" else score)(args.root)
