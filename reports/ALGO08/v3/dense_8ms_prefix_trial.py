"""One authorized saved publication using the corrected dense control's worker."""

from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PLAN_SHA = "f27a310ca77245d0d310ca80a63ff118ab87750e819c7adbe94cef6be89ec003"
MEMBER = Path("/dev/shm/leo-v3-dense-8ms-anchors-result01/result.json")
MEMBER_SHA = "6a31858c0320cdcd21300d665b6916f8a8514f16f2e254bf181293ec13ead5b0"
CONTROL = Path("/dev/shm/leo-exact-solver-0008-result01")
CONTROL_SOURCES = Path("/dev/shm/leo-v3-exact-solver-0008/reports/ALGO08/v3")
CONTROL_PINS = {
    "binding.json": "cfbf388f8bf90f34f8ced8ad6d3d1ca128075b43e528cf7b09684c71ea120070",
    "result.json": "f4750387b41c8247e6195a162a5653f11c2fd2281b23faa857cddbb1bc29255a",
    "candidate/joint-research-receipt.json": "c1f7486fb931e782049f6191d6751354cbb908cc739a05248c058e5ef2e9ac3a",
}
RECEIVER = "research-dense-first-192-signed-8ms"


def member_gains(member):
    timing = [{mode: member["results"][f"{order}-{mode}"]["scope"]["timing"]
               for mode in ("mixed12", "mixed8")} for order in (1, 2)]
    if (member["waveform_visits_per_arm"] != 64 or not member["exact_original_iq_and_earlier_primary_controls"]
            or member["binding"]["orders"] != [["mixed12", "mixed8", "primary8"], ["primary8", "mixed8", "mixed12"]]
            or any(row["mixed8"][clock] >= row["mixed12"][clock] for row in timing for clock in ("cpu_ns", "wall_ns"))):
        raise ValueError("Both reversed original member timings must independently improve")
    return timing


def saved_receiver_pin(current, request):
    if current != request or current["receiver"] != RECEIVER:
        raise ValueError("Dynamic receiver use is confined to the admitted saved packet")
    return current["detector"][7:]


def gates(plan):
    from empty_bootstrap import checked

    intervention = json.loads(checked(plan / "plan.json", PLAN_SHA))
    member = json.loads(checked(MEMBER, MEMBER_SHA))
    binding, full, joint = (json.loads(checked(CONTROL / name, digest)) for name, digest in CONTROL_PINS.items())
    timing = member_gains(member)
    if (full["receipt"]["receipt"]["decision"] != "complete" or full["waveform_reads"]
            or len(full["figures"]) != 8 or full["actual"]["solve"]["grid_points"] != 179
            or [len(rows) for rows in joint["selected_rows"].values()] != [4367, 4367]
            or binding["archive"] != intervention["archive"] or binding["authority"] != intervention["raw_authority"]
            or binding["inventory"] != intervention["original_inventory"]
            or binding["cutoff_utc_ns"] != intervention["original_cutoff"]
            or binding["offer_sha256"] != intervention["original_offer_sha256"]):
        raise ValueError("The one dense saved fitting gate has not been met")
    checked(CONTROL_SOURCES / "exact_solver_0008.py", full["source_sha256"])
    for name, pin in (binding["pins"]["sources"] | joint["source_sha256"]).items():
        if not name.startswith("installed/"):
            checked(CONTROL_SOURCES / name, pin)
    for name, path in binding["libraries"].items():
        checked(Path(path), binding["pins"]["libraries"][name])
    checked(Path(binding["projection"]), binding["pins"]["projection"])
    checked(Path(binding["region"]), binding["offer_sha256"])
    checked(Path(binding["saved_inventory"]), binding["inventory"][7:])
    packet = plan / "detections.json"
    checked(packet, intervention["native_sha256"][7:])
    binding.update(packet=str(packet), native=intervention["native_sha256"], receiver=RECEIVER,
                   detector=intervention["detector_sha256"], plan=str(plan), member_sha256=MEMBER_SHA,
                   corrected_control_sha256=CONTROL_PINS["result.json"], member_timing=timing)
    return binding


def worker(job, output):
    import cumulative_grid_projection as standard
    import exact_solver_0008 as corrected

    request = json.loads(job.read_bytes())
    if request != gates(Path(request["plan"])):
        raise ValueError("The saved-worker binding changed before publication")

    def detector(current, _specification, _mixed_recipe):
        return saved_receiver_pin(current, request)

    with patch.object(standard, "saved_detector", detector):
        corrected.worker(job, output)


def launch(plan, root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    host()
    if root.parent.resolve(strict=True) != Path("/dev/shm") or not plan.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("The saved transfer requires a fresh tmpfs root and sealed local plan")
    binding = gates(plan)
    root.mkdir()
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    for file in (CONTROL / "fonts").glob("fontlist-*.json"):
        (root / "fonts" / file.name).hardlink_to(file)
    job = root / "binding.json"
    write(job, binding)
    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    command = ["/usr/bin/timeout", "--kill-after=2s", "80s", RELEASE / "venv/bin/python", "-IB",
               __file__, "worker", job, root / "candidate"]
    result = measure(command, env, root / "candidate")
    write(root / "clock.json", dict(timing=result, command=list(map(str, command))))


def score(root):
    import gzip
    from aperture_trial import read, write
    from cumulative_grid_projection import proof_fields
    from dense_8ms_prefix import ARCHIVE, PINS
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from mixed_named_finish_0008 import sidecars
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from triage_bounds import calibration_comparison

    request, clock = read(root / "binding.json"), read(root / "clock.json")["timing"]
    if request != gates(Path(request["plan"])):
        raise ValueError("The prelaunch gates changed")
    summary = dict(clock=clock, request=request, prefix_only=True, receiver_description="original 20 ms anchors, authentic"
                   " 8 ms shorts on issued visits 0–191, original 12 ms shorts thereafter, original EOF route")
    if clock["exit_code"]:
        write(root / "result.json", dict(summary, decision="worker_failed"))
        return
    publication = root / "candidate"
    worker, joint, exact = (read(publication / name) for name in (
        "cumulative-grid-worker.json", "joint-research-receipt.json", "exact-options.json"))
    original, control = (json.loads(checked(CONTROL / key, CONTROL_PINS[key]))
                         for key in ("candidate/joint-research-receipt.json", "result.json"))
    receipt = worker["receipt"]
    if (not worker["staged_inventory"] or worker["handoffs"] != 1 or worker["waveform_calls"]
            or receipt != joint["receipt"] or receipt["counts"] != original["receipt"]["counts"]
            or receipt["region"] != original["receipt"]["region"] or receipt["session_id"] != request["session"]):
        raise ValueError("The candidate publication lost its bound original scope")
    checked(native_packet(publication), request["native"][7:])
    science = evidence(publication, receipt, clock["started_unix_ns"], read_only=True)
    if science["raw_authority"] != request["authority"]:
        raise ValueError("The candidate publication lost original recording authority")
    figures = artifacts(publication, receipt)["images"]
    report = dict(summary, decision=receipt["decision"], science=science, figures=figures, worker=worker,
                  exact=exact, route=joint["route_details"], historical_worker_input_label=joint["input"],
                  early_proof=[proof_fields(proof) for proof in joint["early_regional"]],
                  control_clock=control["timing"], control_arms=control["receipt"]["arms"])
    if receipt["decision"] == "complete":
        _, report["sidecars"] = sidecars(FastStandardAnalysisStore(publication), receipt["run_id"], figures)
        arms = {key: owner_delta(original["selected_rows"][key], joint["selected_rows"][key])
                for key in ("c0", "fitted_c")}
        report["owners"] = arms
        report["owners_sha256"] = canonical_digest(joint["selected_rows"])
        report["figure_parity"] = {name: canonical_digest(row) == canonical_digest(control["figures"][name])
                                   for name, row in figures.items()}
        named = json.loads(gzip.decompress(checked(ARCHIVE / "dense-full-short-raw.json.gz",
                                                   PINS["dense-full-short-raw.json.gz"])))["baseline"]
        comparison = calibration_comparison(dict(named=named, control=control["receipt"], candidate=science), "DS30-0008")
        report["geography"] = comparison
    write(root / "result.json", report)


if __name__ == "__main__":
    sys.path[:0] = [str(CONTROL_SOURCES), str(HERE)]
    mode, first, *extra = sys.argv[1:]
    if mode == "worker":
        worker(Path(first), Path(extra[0]))
    elif mode == "launch":
        launch(Path(first), Path(extra[0]))
    elif mode == "score":
        score(Path(first))
    else:
        raise ValueError("Specify launch, worker or score")
