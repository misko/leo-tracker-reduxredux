"""Run the one post-holdout saved candidate only after strict nomination admission."""

import argparse
from functools import partial
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from nomination_handoff_0255 import BASE, BASE_PIN, HANDOFF_PIN, saved
from unseen_saved_holdout import ROOT, digest, runtime_sources


def read(path):
    return json.loads(path.read_bytes())


def remediation_pins():
    paths = (Path(__file__), HERE / "nomination_handoff.py", HERE / "nomination_handoff_0255.py",
             HERE / "cold_finalist_race.py")
    return runtime_sources() | {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def accepted_scope(slice_result, prior):
    if not slice_result["qualified"] or slice_result["before"] != BASE_PIN:
        raise ValueError("The unchanged live nomination identity guards did not qualify")
    seen = slice_result["nomination_handoff"]
    if (seen["scan_reuses"], seen["rank_reuses"], seen["prefixes_reused"]) != (1, 1, 3):
        raise ValueError("Expected all ordered prefixes and the exact named consumer")
    cold = prior["candidate_traces"]["risk-route.json"]["solves"][0]["lean_attempts"][0]["cold_clocks"]["cpu_s"]
    estimated = slice_result["scope_estimate_cpu_s"] + cold - slice_result["producer"]["cpu_ns"] / 1e9
    if estimated < 1:
        raise ValueError("The verified nomination scope offers less than one CPU second")
    return estimated


def worker(job, pin, output):
    from empty_bootstrap import checked
    import clean_saved_publication as generic
    from nomination_handoff import routed_binding
    from solver_exception_live import worker as orbit_worker

    checked(HERE / "nomination_handoff.py", HANDOFF_PIN)
    book = read(output.parent / "admission.json")
    if book["source_pins"] != remediation_pins() or book["job_sha256"] != pin:
        raise ValueError("The sealed post-holdout scientific runtime changed")
    with patch.object(generic, "routed", partial(generic.routed, route_binding=routed_binding)):
        orbit_worker(job, pin, output)


def launch(root, slice_path, slice_pin):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    started = boot.now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private post-holdout tmpfs output")
    prior = saved()
    trial = json.loads(boot.checked(resident_path(slice_path), slice_pin))
    if trial["sources"]["nomination_handoff.py"] != HANDOFF_PIN:
        raise ValueError("The measured slice used a different handoff")
    estimate = accepted_scope(trial, prior)
    checked_inputs = prior["admission"]
    machine, timed_sources = host(), runtime_sources()
    if machine != checked_inputs["machine"] or set(timed_sources) != set(checked_inputs["sources"]):
        raise ValueError("The prior paired worker scope or machine changed")
    changes = {name for name, pin in timed_sources.items() if pin != checked_inputs["sources"][name]}
    if changes != {"reports/ALGO08/v3/clean_saved_publication.py"}:
        raise ValueError(f"More than the optional routing bind changed: {changes}")
    job = BASE / "job.json"
    pin = checked_inputs["job_sha256"]
    binding = json.loads(boot.checked(job, pin))["binding"]
    _, refs = checked_catalogue(binding, read(Path(binding["request"])), TleArchiveReader, canonical_digest)
    causal = resident([ref.path for ref in refs])
    root.mkdir(mode=0o700)
    target = root / "routed"
    target.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(BASE / "fonts", root / "fonts")
    write(target / "binding.json", {"input": binding})
    cmd = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(boot.RELEASE / "venv/bin/python"), "-IB",
           __file__, "worker", str(target), str(job), pin]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "admission.json", dict(command=cmd, machine=machine, original_holdout_sha256=BASE_PIN,
          source_pins=remediation_pins(), job_sha256=pin, resident=causal, slice_sha256=slice_pin,
          setup=boot.clock(started), slice=trial, scope_estimate_cpu_s=estimate, planned_children=1))
    write(root / "clock.json", measure(cmd, env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("pin")
    opts = parser.parse_args()
    if opts.mode == "worker":
        worker(opts.evidence, opts.pin, opts.root)
    else:
        launch(opts.root, opts.evidence, opts.pin)
