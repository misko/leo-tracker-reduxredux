"""Run the guarded cold source index through one saved selective publication."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REFERENCE = Path("/dev/shm/leo-v3-continued-refine-results-03")
BINDING_PIN = "d3a1c17592f6f4f626cb4fa994633be171d5d32ab8da7eb7126095b8b9e6aaef"
REFERENCE_PIN = "116ffb08ed230a21d6209a050a42a0293ea2e3ed94cdd72a807f8a49adb1b7e7"
CLOCK_PIN = "d2285d8e9c2acc2da3d3e433cbe155d730e11758ef33b7c3a221d01f7d02e7eb"
TIMING_FIELDS = {
    "curved_design": {"direct_assembly_ns", "history_selection_ns", "normal_selection_ns"},
    "endpoint_reuse": {"endpoint_cpu_s"},
    "graph_path": {"pack_ns", "search_ns"},
    "posterior_grid_handoff": {"curved_cpu_ns", "gram_or_check_cpu_ns", "predictive_kernel_cpu_ns"},
}


def compared_receipt(receipt):
    result = dict(receipt)
    for scope, names in TIMING_FIELDS.items():
        result[scope] = {key: value for key, value in receipt[scope].items() if key not in names}
    result["sparse_rank_projection"] = [{key: value for key, value in row.items() if key != "shifted_cpu_s"}
                                        for row in receipt["sparse_rank_projection"]]
    return result


def worker(root):
    from active_preparation_trial import bind_preparation
    from continued_cfo_trial import work
    from historical_orbit_index import guarded_preparation

    audit = {}
    with bind_preparation(guarded_preparation, audit):
        work(root)
    audit["adapter_sha256"] = sha256((HERE/"historical_orbit_index.py").read_bytes()).hexdigest()
    with (root/"orbits-indexed.json").open("x") as out:
        json.dump(audit, out, sort_keys=True, allow_nan=False)
        out.write("\n")


def run(root, *, worker_path=None):
    from empty_bootstrap import RELEASE, checked, load_runtime

    load_runtime()
    from tools import pipeline_eval
    from tools.pipeline_eval import qualification

    # The scored worker stays isolated. The launcher also needs the local,
    # read-only tools used to verify earlier publications and external clocks.
    research = HERE.parents[2]/"tools/pipeline_eval"
    pipeline_eval.__path__.append(str(research))
    qualification.__path__.append(str(research/"qualification"))
    from aperture_trial import write
    from full_short_physical import environment
    from historical_orbit_index import case_inputs
    from short_raw_diagnostic import measure

    root = root.resolve()
    if root.parent != Path("/dev/shm"):
        raise ValueError("Expected fresh output under tmpfs")
    binding = checked(REFERENCE/"binding.json", BINDING_PIN)
    req = json.loads(binding)
    _, archive, offer, _ = case_inputs("DS30-0016")
    if Path(req["archive"]) != archive or json.loads(Path(req["offer"]).read_bytes()) != offer.document():
        raise ValueError("Selective archive and offer differ from the enrolled causal inputs")
    checked(Path(req["saved"]["packet"]), req["saved"]["native_sha256"][7:])
    checked(Path(req["saved_inventory"]), req["inventory"][7:])
    checked(REFERENCE/"result.json", REFERENCE_PIN)
    checked(REFERENCE/"worker-clock.json", CLOCK_PIN)
    root.mkdir()
    (root/"binding.json").write_bytes(binding)
    (root/"tmp").mkdir()
    env = environment(root)
    env.update(TMPDIR=str(root/"tmp"), XDG_CACHE_HOME=str(root/"tmp"))
    python = RELEASE/"venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    target = root/"selective"
    clock = measure([python, "-IB", worker_path or __file__, root, "--worker"], env, target)
    write(root/"candidate-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    score(root)


def score(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from regional_history_score import one, scientific

    checked(root/"binding.json", BINDING_PIN)
    clock = read(root/"candidate-clock.json")
    if clock["exit_code"]:
        raise ValueError("The retained saved child did not finish")
    prior = json.loads(checked(REFERENCE/"result.json", REFERENCE_PIN))
    target = root/"selective"
    audit = read(root/"orbits-indexed.json")
    actual = read(target/"continued-cfo-worker.json")
    prior_trace, candidate_trace = [read(path/"selective/joint-research-receipt.json") for path in (REFERENCE, root)]
    receipt = actual["receipt"]
    detail = FastStandardAnalysisStore(target).detail(receipt["run_id"])
    terminal = json.loads(checked(one(target, "terminal.json"), receipt["terminal_sha256"][7:]))
    media = artifacts(target, receipt)
    products = scientific(target)
    if (actual["handoffs"] != 1 or actual["waveform_calls"] or receipt["decision"] != "complete"
            or products != scientific(REFERENCE/"selective") or products["grid_points"] != 179
            or compared_receipt(receipt) != compared_receipt(prior["science"]["receipt"])
            or terminal["arms"] != prior["science"]["arms"]
            or detail["raw_authority"] != prior["science"]["raw_authority"]
            or {arm: value["owner_sha256"] for arm, value in detail["arms"].items()} != prior["science"]["owners"]
            or canonical_digest(media["images"]) != canonical_digest(prior["images"]["images"])
            or canonical_digest(candidate_trace["selected_rows"]) != prior["owner_roles_sha256"]):
        raise ValueError("The saved index changed the signed fix, ordered owners or verified media")
    publication = {name: {k: run[k] for k in ("publication_cpu_s", "publication_elapsed_s")}
                   for name, run in (("reference", prior_trace), ("candidate", candidate_trace))}
    write(root/"result.json", dict(binding_sha256=BINDING_PIN, reference_sha256=REFERENCE_PIN, processes=dict(
        reference=prior["process"], candidate=clock), audit=audit, publication=publication,
        solves=dict(reference=prior_trace["solve"], candidate=candidate_trace["solve"]), science=products,
        arms=terminal["arms"], geography=prior["geography"], media=media, candidate_waveform_reads=0,
        candidate_handoffs=1, candidate_terminal_receipt=receipt,
        scoring_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def preflight():
    from functools import partial
    from unittest.mock import patch

    from empty_bootstrap import load_runtime

    load_runtime()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position
    from tools.pipeline_eval.variants import algo08_causal_reuse as installed
    from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_exterior_veto

    from historical_orbit_index import WEAK, installed_guard, preparation_port

    original = partial(installed.prepare, algo08_position.prepare_native_scan, statistics={})
    archive = TleArchiveReader(WEAK/"tle")
    with patch.object(algo08_position, "prepare_native_scan", original), bound_exterior_veto(archive, terminal_only=True):
        accepted = preparation_port(algo08_position.prepare_native_scan, installed.prepare)
    if not installed_guard() or accepted != "regional":
        raise ValueError("The source-pinned regional preparation ABI did not activate")
    print("Accepted installed regional preparation and exporter")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--worker", action="store_true")
    cli.add_argument("--score-sealed", action="store_true")
    cli.add_argument("--preflight", action="store_true")
    args = cli.parse_args()
    if args.preflight:
        preflight()
    elif args.score_sealed:
        from empty_bootstrap import load_runtime

        load_runtime()
        score(args.root)
    else:
        (worker if args.worker else run)(args.root)
