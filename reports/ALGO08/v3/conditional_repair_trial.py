"""Time one resident saved worker, seal its output, then join position truth."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from empty_bootstrap import RELEASE, checked
from nomination_handoff_0255 import BASE, BASE_PIN, HANDOFF_PIN, saved


CONTROL = Path("/dev/shm/leo-v3-nomination-handoff-0419-local01/result.json")
CONTROL_PIN = "0e2bec8d6b8083976c9f0491dc65599d32a2c159e2a3d162eb3d9d4bc7dee7e9"
HANDOFF = Path("/dev/shm/leo-v3-nomination-handoff-0255-result01/result.json")
HANDOFF_RESULT = "192ee623532d238f589737a46d0472ec6ddd11fa14aa109468236426b45278ec"
PROTOCOL_PIN = "3fdffe916e8cf2eee0bb6d58d1c94dd4b4dfa3863f2969699414d20a740f4ce2"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def source_pins():
    checked(HERE / "conditional-repair-fallback-protocol.md", PROTOCOL_PIN)
    checked(HERE / "nomination_handoff.py", HANDOFF_PIN)
    paths = (Path(__file__), HERE / "blind_joint_repair.py", HERE / "conditional_repair_fallback.py")
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in paths}


def worker(root, job, job_pin):
    import clean_saved_publication as publication
    from solver_exception_live import worker as publish

    admission = read(root.parent / "admission.json")
    if admission["source_sha256"] != source_pins() or admission["job_sha256"] != job_pin:
        raise ValueError("The frozen worker or saved input changed")

    def binding(*args):
        from conditional_repair_fallback import binding as conditional_binding

        return conditional_binding(*args)

    with patch.object(publication, "routed", partial(publication.routed, route_binding=binding)):
        publish(job, job_pin, root)


def launch(root):
    from aperture_trial import write
    from causal_body_publication_trial import measure
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from empty_bootstrap import clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from visit_frame_raw_0016 import resident

    started = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a fresh private tmpfs result")
    prior = saved()
    previous = json.loads(checked(HANDOFF, HANDOFF_RESULT))
    if not previous["qualified"] or host() != previous["admission"]["machine"]:
        raise ValueError("Require the qualified handoff on the original low-priority Gauss slot")
    job, job_pin = BASE / "job.json", prior["admission"]["job_sha256"]
    bound, request = load_job(job, job_pin)
    _, refs = checked_catalogue(bound, request, TleArchiveReader, canonical_digest)
    residency = resident([ref.path for ref in refs] + [Path(request["native_file"])])
    root.mkdir(mode=0o700)
    target = root / "routed"
    target.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(BASE / "fonts", root / "fonts")
    write(target / "binding.json", {"input": bound})
    command = ["/usr/bin/timeout", "--kill-after=2s", "75s", str(RELEASE / "venv/bin/python"),
               "-IB", __file__, "worker", str(target), str(job), job_pin]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    write(root / "admission.json", dict(command=command, machine=host(), source_sha256=source_pins(),
          protocol_sha256=PROTOCOL_PIN, job_sha256=job_pin, resident=residency, planned_children=1,
          controls=dict(installed=BASE_PIN, handoff=HANDOFF_RESULT, accepting=CONTROL_PIN), setup=clock(started)))
    write(root / "clock.json", measure(command, env, target / "candidate"))
    write(root / "prediction-seal.json", output_seal(root))


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from prospective_0316_solver import inspect, owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from unseen_saved_holdout_score import REFERENCE_PIN, reference

    book, clock = (read(root / name) for name in ("admission.json", "clock.json"))
    if book["source_sha256"] != source_pins() or read(root / "prediction-seal.json") != output_seal(root):
        raise ValueError("The scientific worker or its sealed output changed")
    prior = saved()
    previous = json.loads(checked(HANDOFF, HANDOFF_RESULT))
    control = json.loads(checked(CONTROL, CONTROL_PIN))
    (contrast,) = control["candidate_traces"]["risk-route.json"]["solves"][0]["lean_attempts"]
    if contrast["decision"] != "complete" or contrast.get("fallback_clocks") is not None:
        raise ValueError("The archived control did not complete its normal lean route")
    receipt = dict(schema="leo.research.conditional-repair-fallback.v1", reference_sha256=REFERENCE_PIN,
                   admission=book, clock=clock, prediction_seal_sha256=sha256(
                       (root / "prediction-seal.json").read_bytes()).hexdigest(), original_waveform_reads=0,
                   fresh_children=1, controls={"installed_0255": prior["jobs"]["installed"]["clock"],
                   "handoff_0255": previous["clock"], "archived_0419": {
                       "clock": control["jobs"]["routed"]["clock"], "decision": contrast["decision"],
                       "pair_passes": contrast["pair_passes"], "repair": contrast.get("repair")}})
    if clock["exit_code"]:
        write(root / "result.json", receipt | {"qualified": False, "reason": "candidate failed"})
        return
    request = read(BASE / "request.json")
    folder = root / "routed/candidate"
    terminal = read(folder / "worker.json")["receipt"]
    publication = inspect(folder, "conditional fallback", terminal, clock, request,
                          native_sha=request["native_sha256"], windows=request["issued"],
                          admitted=request["admitted"], audit_name="worker.json")
    (solve,) = read(root / "routed/risk-route.json")["solves"]
    (attempt,) = solve["lean_attempts"]
    baseline = prior["jobs"]["installed"]["publication"]
    truth = reference()
    geographic = {}
    for label, published in (("installed", baseline), ("handoff", previous["publication"]), ("candidate", publication)):
        geographic[label] = {arm: dict(latlon=row["latlon"], horizontal_error_m=1000 * distance_km(truth, row["latlon"]),
                                     rf_rms_hz=row["rf_rms_hz"]) if row["latlon"] is not None else None
                             for arm, row in published["science"]["arms"].items()}
    owners = {arm: owner_delta(baseline["selected_rows"][arm], publication["selected_rows"].get(arm, [])) for arm in ARMS}
    checks = dict(same_input=all(publication["terminal"][key] == baseline["terminal"][key]
                                 for key in ("native_sha256", "region", "session_id")),
                  conditional_route=attempt["decision"] == "complete" and attempt.get("conditional_repair_fallback", {}).get(
                      "status") == "qualified_for_standard_evidence" and "fallback_clocks" not in attempt,
                  same_fix_status=terminal["decision"] == "complete",
                  no_increase_in_error=all(geographic["candidate"].get(arm) is not None and
                                           geographic["candidate"][arm]["horizontal_error_m"] <=
                                           geographic["installed"][arm]["horizontal_error_m"] for arm in ARMS),
                  no_conflicting_shared_owner=all(not row["reassigned_norad"] and not row["changed_roles"]
                                                  for row in owners.values()),
                  faster=all(clock[key] < receipt["controls"]["installed_0255"][key]
                             for key in ("elapsed_s", "cpu_s")))
    write(root / "result.json", receipt | dict(qualified=all(checks.values()), checks=checks, geographic=geographic,
          owners=owners, attempt=attempt, media=publication["figures"], sidecars=publication["sidecars"]))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("job", type=Path, nargs="?")
    parser.add_argument("job_pin", nargs="?")
    args = parser.parse_args()
    if args.mode == "worker":
        worker(args.root, args.job, args.job_pin)
    else:
        (launch if args.mode == "launch" else score)(args.root)
