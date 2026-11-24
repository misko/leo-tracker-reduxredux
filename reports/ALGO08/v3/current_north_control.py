"""Time the original deployed command once and seal it against its previous North result."""

import argparse
import json
from pathlib import Path
import subprocess

from aperture_trial import RELEASE, read, write
from dense_geographic_trial import host
from empty_bootstrap import checked
from full_short_physical import CACHE_LIB, CACHE_SHA, environment
from joint_held_north_raw import REFERENCE_PINS, cache_snapshot_for_run, references, validate_workload
from north_held_anchor_pair import publication_evidence, tmpfs
from raw_cfo_north_trial import workload
from short_raw_diagnostic import measure


def comparison(old, new):
    def images(result):
        return {name: (record["sha256"], record["rgba_sha256"], tuple(record["size"]))
                for name, record in result["figures"].items()}

    return dict(native=old["native_sha256"] == new["native_sha256"],
                opportunities=old["opportunity_sha256"] == new["opportunity_sha256"],
                grid_points=old["grid_points"] == new["grid_points"],
                arms=old["verified"]["arms"] == new["verified"]["arms"],
                owners=old["verified"]["owners"] == new["verified"]["owners"],
                terminal=old["verified"]["receipt"]["terminal_sha256"] == new["verified"]["receipt"]["terminal_sha256"],
                images=images(old) == images(new))


def run(root):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    old_binding, results = references()
    machine = host()
    tmpfs(root.parent)
    root.mkdir()
    request, manifests = workload(root)
    assignment = old_binding["assignment"]
    validate_workload(request, assignment, machine, old_binding["machine"])
    for path in (request["recording"], request["archive"]["root"]):
        tmpfs(path)
    original = old_binding["commands"]["stock"]
    command = [str(NAMED_V3), "--recording", request["recording"], "--archive", request["archive"]["root"],
               "--region", request["inside_offer"], "--bulk-root", str(root/"stock")]
    if command[:-1] != original[:-1] or not original[-1].endswith("/stock"):
        raise ValueError("Only the fresh output root can change")
    binary = verified_v3(NAMED_V3)
    checked(CACHE_LIB, CACHE_SHA)
    query, store = load_query(CACHE_LIB), FastScanStore(root)
    for name in ("stock", "fonts"):
        (root/name).mkdir()
    env = environment(root)
    subprocess.run([RELEASE/"venv/bin/python", "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, timeout=30, env=env)
    before = cache_snapshot_for_run(store, request, manifests, query)
    write(root/"binding.json", dict(binary=binary, command=command, reference=REFERENCE_PINS,
                                    machine=machine, before=before, original=original))
    clock = measure(command, env, root/"stock")
    write(root/"clock.json", clock)
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])
    after = cache_snapshot_for_run(store, request, manifests, query)
    write(root/"after.json", after)
    return score(root)


def score(root):
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    binding, results = references()
    clock, old = read(root/"clock.json"), results["stock"]
    receipt = json.loads((root/"stock.stdout").read_text().splitlines()[-1])
    new = publication_evidence(root/"stock", receipt, clock, binding["assignment"])
    new.pop("native")
    new["grid_points"] = FastStandardAnalysisStore(root/"stock").position_grid(receipt["run_id"])["evaluated_points"]
    new["clock"] = clock
    checked_fields = comparison(old, new)
    summary = dict(binding=read(root/"binding.json"), after=read(root/"after.json"),
                   old_clock=old["clock"], new=new, checked_fields=checked_fields)
    write(root/"verified-comparison.json", summary)
    if not all(checked_fields.values()):
        raise ValueError(checked_fields)
    return summary


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    (run if args.action == "run" else score)(args.root)
