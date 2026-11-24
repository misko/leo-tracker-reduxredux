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


def worker(root):
    from active_preparation_trial import bind_preparation
    from continued_cfo_trial import work
    from historical_orbit_index import guarded_preparation

    audit = {}
    with bind_preparation(guarded_preparation, audit):
        work(root)
    with (root/"orbits-indexed.json").open("x") as out:
        json.dump(audit, out, sort_keys=True, allow_nan=False)
        out.write("\n")


def run(root):
    from empty_bootstrap import RELEASE, checked, load_runtime

    load_runtime()
    from aperture_trial import read, write
    from full_short_physical import environment
    from historical_orbit_index import case_inputs
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from regional_history_score import scientific
    from short_raw_diagnostic import measure, pairs

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
    clock = measure([python, "-IB", __file__, root, "--worker"], env, target)
    write(root/"candidate-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    prior = json.loads(checked(REFERENCE/"result.json", REFERENCE_PIN))
    audit = read(root/"orbits-indexed.json")
    actual = read(target/"continued-cfo-worker.json")
    prior_trace, candidate_trace = [read(path/"selective/joint-research-receipt.json") for path in (REFERENCE, root)]
    receipt = actual["receipt"]
    science = pairs.evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    media = artifacts(target, receipt)
    products = scientific(target)
    if (actual["handoffs"] != 1 or actual["waveform_calls"] or receipt["decision"] != "complete"
            or products != scientific(REFERENCE/"selective") or products["grid_points"] != 179
            or any(science[field] != prior["science"][field] for field in ("receipt", "arms", "owners", "scientific_digests"))
            or canonical_digest(media["images"]) != canonical_digest(prior["images"]["images"])
            or canonical_digest(candidate_trace["selected_rows"]) != prior["owner_roles_sha256"]):
        raise ValueError("The saved index changed the signed fix, ordered owners or verified media")
    publication = {name: {k: run[k] for k in ("publication_cpu_s", "publication_elapsed_s")}
                   for name, run in (("reference", prior_trace), ("candidate", candidate_trace))}
    write(root/"result.json", dict(binding_sha256=BINDING_PIN, reference_sha256=REFERENCE_PIN, processes=dict(
        reference=prior["process"], candidate=clock), audit=audit, publication=publication,
        solves=dict(reference=prior_trace["solve"], candidate=candidate_trace["solve"]), science=products,
        arms=science["arms"], geography=prior["geography"], media=media, candidate_waveform_reads=0,
        candidate_handoffs=1, source_sha256=sha256((HERE/"historical_orbit_index.py").read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--worker", action="store_true")
    args = cli.parse_args()
    (worker if args.worker else run)(args.root)
