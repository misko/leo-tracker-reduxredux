"""Run one named-inference history-support diagnostic on staged DS30-0160."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
STAGED = Path("/dev/shm/leo-v3-saved-0160-pair-01")
CORRECTED = Path("/dev/shm/leo-v3-saved-0160-confirm-01/cumulative")
ROSTER = Path("/dev/shm/leo-v3-history-retry-roster-20261123.json")
REQUEST = STAGED / "request.json"
INVENTORY = STAGED / "stock/fast-scan-inputs/fast-cc3dc7e24fa661a1627e25f9cea0ac60.json"
REFERENCE = STAGED / "stock/joint-research-receipt.json"
PINS = {
    REQUEST: "c3b6e328f03f79e9d0b0989fabb3ab246394a03c98dd2ca7c2ca4f3a608e3d2e",
    INVENTORY: "cc3dc7e24fa661a1627e25f9cea0ac6038c18c93b69a32fa2f2475cf9f1b8860",
    REFERENCE: "ebf1a80ae206a9c32cae2374e49b050faa1d0087413b313a3189a541d7e4ed08",
    STAGED / "stock/saved-0160-worker.json": "8e08a9af8f911a2b212be56249e07b0d78db471a14f8f295424d0aaa1ccefae5",
    STAGED / "stock-clock.json": "6462606e312e928aff3e4a175ccc580b16bd43a80a57f1628b88cf4ce844d9fa",
    CORRECTED / "joint-research-receipt.json": "73e54beda2194af4807b06b4d26e60f58afea4acc73b64cf479d7b1e33456666",
    CORRECTED / "saved-0160-worker.json": "dcff021b1ea2c21379c2c2307eb59eed66dbb5eda48ac33c9f95135797fc0943",
    ROSTER: "ab0c76a69e466964c9bc24b488c5e4954d6bf836a4fc4328076d3faae8ca2fe7",
}


def evidence():
    from empty_bootstrap import checked

    return {path: json.loads(checked(path, digest)) for path, digest in PINS.items()}


def worker(output):
    import empty_bootstrap as staged
    from aperture_trial import write
    from named_history_once import named_solve
    from prospective_0160_solver import FIX_PINS, SETTINGS
    from prospective_0316_solver import worker as ordinary_worker

    load_runtime = staged.load_runtime
    with ExitStack() as stack:
        def observed_runtime():
            nonlocal audit
            result = load_runtime()
            audit = stack.enter_context(named_solve(True, staged.RELEASE, staged.PAYLOAD))
            return result

        audit = None
        stack.enter_context(patch.object(staged, "load_runtime", observed_runtime))
        ordinary_worker(REQUEST, "stock", output, source_pins=FIX_PINS, inventory_file=INVENTORY, **SETTINGS)
    if audit is None:
        raise ValueError("The named saved worker did not bind local orbit recovery")
    write(output / "named-history-once.json", audit)


def validate(output, clock, original):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from publication_media_checks import verify_position_sidecars
    from tools.pipeline_eval.qualification.paired_publication import evidence as read_publication

    audit = read(output / "named-history-once.json")
    own = read(output / "saved-0160-worker.json")
    joint = read(output / "joint-research-receipt.json")
    before = original[REFERENCE]
    case = own["receipt"]
    run = case["run_id"]
    name = "fast-scan-automatic-work"
    reference = STAGED / "stock"
    proof, before_proof = (
        read_publication(folder, receipt, started, read_only=True)
        for folder, receipt, started in ((output, case, clock["started_unix_ns"]),
                                         (reference, before["receipt"], original[STAGED / "stock-clock.json"]["timing"]["started_unix_ns"]))
    )
    both = {"c0", "fitted_c"}
    if (case["decision"] != "complete" or set(proof["arms"]) != both
            or any(proof[key] != before_proof[key] for key in ("arms", "owners", "raw_authority", "scientific_digests", "artifacts"))
            or case["terminal_sha256"] != before["receipt"]["terminal_sha256"]
            or joint["selected_rows"] != before["selected_rows"] or set(joint["selected_rows"]) != both
            or any(not joint["selected_rows"][arm] for arm in both) or not own["no_waveform"] or own["handoffs"] != 1
            or own["solve"]["orbit_policy"] != "history_support"):
        raise ValueError("Named recovery modified calibration, owners, terminal or captures")
    if (audit["solves"] != 1 or audit["original_policy"] != "stock" or audit["published_policy"] != "history_support"
            or not audit["events"] or any(not event["failed_previous_norads"] for event in audit["events"])
            or any([row["status"] for row in audit[stage]] != ["returned"] for stage in ("prepare", "infer"))):
        raise ValueError("Named recovery did not remove the full fallback attempt")
    figures, before_figures = (artifacts(folder, receipt)["images"] for folder, receipt in
                               ((output, case), (reference, before["receipt"])))
    if len(figures) != 8 or figures != before_figures or canonical_digest(figures) != canonical_digest(joint["evidence"]["images"]):
        raise ValueError("The candidate did not independently verify all eight exact named figures")
    available, archived = (FastStandardAnalysisStore(folder) for folder in (output, reference))
    if any(available.artifact(run, figure) != archived.artifact(run, figure) for figure in figures):
        raise ValueError("Full named PNG payload changed")
    sidecars = verify_position_sidecars(reference, output, run, before_figures, figures)
    grid = available.position_grid(run)
    terminals = [read(folder / name / run / "terminal.json") for folder in (output, reference)]
    if not grid["complete"] or grid["evaluated_points"] != 179 or terminals[0] != terminals[1]:
        raise ValueError("Final named terminal or grid changed")
    return dict(stage_audit=audit, worker=own, science=proof, sidecars=sidecars, figures=figures,
                ordered_owner_counts={arm: len(joint["selected_rows"][arm]) for arm in sorted(both)},
                ordered_owner_sha256=canonical_digest(joint["selected_rows"]), grid_points=grid["evaluated_points"])


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    original = evidence()
    if subprocess.check_output(["findmnt", "-T", str(root.parent), "-no", "FSTYPE"], text=True).strip() != "tmpfs":
        raise ValueError("Named diagnostic needs a new tmpfs root")
    root.mkdir()
    (root / "tmp").mkdir()
    observed = root / "once"
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", Path(__file__), "worker", observed]
    bound = dict(machine=machine, scored_only_as_development=True, launches=1,
                 sources={path.name: sha256(path.read_bytes()).hexdigest() for path in (
                     Path(__file__), HERE / "named_history_once.py", HERE / "named-history-once-protocol.md",
                     HERE / "prospective_0160_solver.py", HERE / "prospective_0316_solver.py", HERE / "joint_publication.py",
                 )}, inputs={str(path): digest for path, digest in PINS.items()}, command=list(map(str, command)))
    binding = root / "binding.json"
    write(binding, bound)
    clock = measure(command, env, observed)
    write(root / "clock.json", clock)
    if clock["exit_code"] != 0:
        raise ValueError("The independently timed named diagnostic failed; see the saved clock and stderr")
    result = validate(observed, clock, original)
    write(root / "result.json", dict(case="DS30-0160", no_waveforms=True, only_named_candidate_run=True,
              binding_sha256=sha256(binding.read_bytes()).hexdigest(), candidate=dict(clock=clock, result=result),
              archived_named=dict(clock=original[STAGED / "stock-clock.json"]["timing"],
                                  solve=original[STAGED / "stock/saved-0160-worker.json"]["solve"]),
              corrected_cumulative=original[CORRECTED / "saved-0160-worker.json"]["solve"]))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "run"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    (worker if args.mode == "worker" else run)(args.output)
