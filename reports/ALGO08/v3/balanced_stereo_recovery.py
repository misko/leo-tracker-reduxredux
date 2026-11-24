"""Replay North with one unconditional recovery for empty selected history."""

import argparse
from functools import partial
from hashlib import sha256
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from unittest.mock import patch

from . import balanced_stereo as baseline


HERE = Path(__file__).resolve().parent
PREVIOUS = "4c8733f75118a6a433e1babf7530d034f545d13cf30bb332fbf7dc1cf37cb438"
PROTOCOL = HERE/"balanced-stereo-recovery-protocol.md"


def should_recover(witness):
    return witness["choice"]["route"] == "history" and witness["selected"] == 0 and witness["observed"] > 0


def preserve_paid(paid, chosen, witness):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    if not should_recover(witness):
        return chosen, witness
    rows = paid["source"]["probes"]
    if len(rows) != len(chosen["source"]["probes"]) or sum(len(row["candidates"]) for row in rows) != witness["observed"]:
        raise ValueError("The fallback must reuse the already measured unfiltered factors")
    policy = dict(witness["receiver_recipe"], empty_history_recovery=dict(
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        previous_route="history", previous_selection=witness["native_sha256"],
        condition="exactly zero history factors and nonempty measured alternatives"))
    recovered = rebinding(paid, rows, policy)
    native, detector = canonical_digest(recovered), canonical_digest(policy)
    source = recovered["source"]
    bind_native(recovered, source["session_id"], source["input_manifest_sha256"], detector[7:], expected=native)
    choice = dict(witness["choice"], paid_unfiltered_recovery=True, original_route="history", route="unfiltered")
    return recovered, dict(witness, choice=choice, receiver_recipe=policy, native_sha256=native,
                           detector_recipe_sha256=detector, selected=witness["observed"])


def run(root):
    import anchor_cycle_route
    from anchor_exposure import PINS, bind, packet
    from dense_geographic_trial import host
    from eight_ms_held_fit import RECEIVER_RECIPE_PINS, select
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.storage import fast_scan
    from north_held_anchor_pair import tmpfs
    from preloaded_saved_worker import enrolled
    from whole_stereo_8ms_trial import launch, pins, seal
    from whole_stereo_blocks import load_checked

    machine = host()
    repo = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={repo}", "-C", str(repo)]
    if (subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip()
            or Path(fast_scan.__file__).resolve() != repo/"src/leo/storage/fast_scan.py"):
        raise ValueError("Freeze the recovery and use the checkout's no-create verification port")
    case = "north"
    previous = load_checked(HERE/"measurements/balanced-stereo.json.gz", PREVIOUS)["scores"][case]
    old_plan = previous["plan"]
    request, archive, offer, libraries, *_ = enrolled(case)
    source, native_pin = PINS[case]["8ms"]
    for path in (root.parent, source, request["saved_inventory"], archive, offer, *libraries.values()):
        tmpfs(path)
    original = packet(source, native_pin)
    meta = load_checked(Path(source)/"full-short-recipe.json", RECEIVER_RECIPE_PINS[case])
    root.mkdir()
    directory = root/case
    directory.mkdir()
    start_cpu, start_wall = process_time(), perf_counter()
    decisions = baseline.schedule(original)
    paid, recipe, events, counts = baseline.project(original, meta["recipe"], decisions)
    choose = partial(baseline.paid_route, donors=baseline.donor_budget(decisions))
    with patch.object(anchor_cycle_route, "select_route", choose):
        selected, witness = select(paid, recipe)
    old_witness = old_plan["masked_witness"]
    if (old_witness["native_sha256"] != witness["native_sha256"] or old_witness["parent_native_sha256"] != canonical_digest(paid)
            or canonical_digest(events) != canonical_digest(old_plan["events"]) or counts != old_plan["schedule"]
            or not should_recover(witness) or previous["decision"] != "withheld"):
        raise ValueError("The original false withhold must be reproduced before the diagnostic")
    recovered, new_witness = preserve_paid(paid, selected, witness)
    bind(paid, recovered)
    path = directory/"detections.json"
    fast_scan.immutable_json(path, recovered)
    checked(path, new_witness["native_sha256"][7:])
    planning = dict(cpu_s=process_time()-start_cpu, elapsed_s=perf_counter()-start_wall)
    binding = dict(host=machine, sources=pins(), commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                   protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(), prior_receipt_sha256=PREVIOUS,
                   recovery_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), order=[case])
    baseline.write(root/"binding.json", binding)
    plan = dict(case=case, identity=old_plan["identity"], admit=True, schedule=counts, planning=planning,
                previous_native_sha256=witness["native_sha256"], parent_paid_native_sha256=canonical_digest(paid),
                masked_witness=new_witness, prior_events_sha256=canonical_digest(events))
    baseline.write(directory/"plan.json", plan)
    launch(root, case)
    seal(root, case)
    result = baseline.qualify(root, case)
    baseline.write(root/"result.json", dict(binding=binding, plan=plan, score=result, qualified=result["qualified"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
