"""Compare all-paid and continuation-gated CFO on one resident staged member."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import ModuleType
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
DONOR = Path("/dev/shm/leo-v3-anchored-raw/reports/ALGO08/v3")
STAGE = "bfd63243d80639cc110f6fe6a4deb2beb140e29c471d2b5e79395203ca72ac08"
ANCHOR_ENTRY = "295204e3a5f20bc642a41cbef186e587b985f02062d8789efe7190c3fed3afda"
LIBRARY = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
ORDER = ("all-paid", "continued")


def load(name, pin, transform=None):
    path = DONOR/(name+".py")
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Changed staged authentication driver: {path}")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    source = data.decode() if transform is None else transform(data.decode())
    exec(compile(source, str(path), "exec"), vars(module))
    return module


def staged_seal_after_decision(text):
    replacements = (
        ("def bind(native, session, inventory, pin, **kwargs):",
         "def bind(native, session, inventory, pin, recipe, original, acquired, decision, timings, **kwargs):"),
        ("        recipe = checked_recipe()\n", ""),
        ("        raise ReceiverSealed()", """        evidence.update(original_probes=original, acquired_probes=acquired,
                        held_cycle_decision=decision, policy_clocks=timings)
        raise ReceiverSealed()"""),
        ('        boundary.enter_context(patch.object(installed, "bind_native", bind))\n', ""),
        ("            launch(common)", "            launch(common, bind)"),
    )
    for before, after in replacements:
        if text.count(before) != 1:
            raise ValueError("The source-pinned staged seal port no longer has the expected boundary")
        text = text.replace(before, after, 1)
    return text


def worker(mode, output):
    sys.path.insert(0, str(HERE))
    import continued_cfo
    import held_cycle_refined
    import short_cfo_raw

    load("anchored_cfo_raw", ANCHOR_ENTRY)
    stage = load("anchored_cfo_stage", STAGE, staged_seal_after_decision)
    observed = Counter()
    consider = continued_cfo.ContinuedChanges.consider
    select = held_cycle_refined.select_refined

    def count(gate, probe, short):
        cpu, wall = process_time_ns(), perf_counter_ns()
        allowed = consider(gate, probe, short)
        observed.update(online_cpu_ns=process_time_ns()-cpu, online_elapsed_ns=perf_counter_ns()-wall,
                        probes=1, paid=int(allowed))
        return allowed

    def launch(argv, seal):
        def timed(native, preparation, changes, session, inventory, receipt_path):
            cpu, wall = process_time_ns(), perf_counter_ns()
            final, recipe, detector, decision = select(native, preparation, changes, session, inventory, receipt_path)
            observed.update(eof_cpu_ns=process_time_ns()-cpu, eof_elapsed_ns=perf_counter_ns()-wall)
            acquired = native["source"]["probes"]
            seal(final, session, inventory, detector, recipe, changes.original_rows(acquired), acquired, decision, dict(observed))

        if mode == "continued":
            with (patch.object(continued_cfo, "select_refined", timed),
                  patch.object(continued_cfo.ContinuedChanges, "consider", count)):
                continued_cfo.raw_entry(LIBRARY, argv)
        else:
            with patch.object(held_cycle_refined, "select_refined", timed):
                short_cfo_raw.run_cli(LIBRARY, [*argv, "--select-before-cfo"])

    stage.worker(mode, None, output, launch=launch)


def resident(stage):
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from tools.pipeline_eval.qualification import cache_residency

    assignment = json.loads(stage.installed.checked(stage.STAGED/"scope.json", stage.SCOPE_SHA))
    segment = Path(assignment["entry"]["path"])
    if segment.parent != stage.STAGED or segment.resolve(strict=True) != segment:
        raise ValueError("The bounded recording is no longer on its prior stage")
    chunk = assignment["member"]
    names = (chunk["payload_relative_path"], chunk["index_relative_path"])
    files = tuple(segment/name for name in names)
    if (stage.WINDOWS != 64 or chunk["window_count"] != 64 or
            any(path.resolve(strict=True) != path or path.stat().st_dev != Path("/dev/shm").stat().st_dev for path in files)):
        raise ValueError("The member exceeds the signed tmpfs boundary")
    stage.installed.checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    state = cache_residency.cache_snapshot([(segment, p.name, p.stat().st_size) for p in files],
                                          os.sysconf("SC_PAGE_SIZE"), query)
    if (state["unavailable"] or state["observed_members"] != 2 or
            state["cached_pages"] != state["observed_file_pages"]):
        raise ValueError("The original staged member and index must already be fully resident")
    return state


def compare(a, b, ap, bp):
    from anchor_holds import history_rows
    from held_cycle_refined import CFO

    if (any(a[k] != b[k] for k in ("iq", "vectors", "prefix_inventory", "original_probes")) or
            ap["source"]["raw_recording_authority_digest"] != bp["source"]["raw_recording_authority_digest"] or
            ap["delivery_clocks"] != bp["delivery_clocks"] or ap["clock_anchor"] != bp["clock_anchor"] or
            ap["provenance"]["detector_sha256"] == bp["provenance"]["detector_sha256"]):
        raise ValueError("The two live policies measured different original evidence")
    choice = a["held_cycle_decision"]["choice"]
    if choice != b["held_cycle_decision"]["choice"]:
        raise ValueError("Online continuation contaminated the held-cycle EOF decision")
    original, all_paid, gated = (a["original_probes"], a["acquired_probes"], b["acquired_probes"])
    kept = history_rows(original)
    short = {(row["visit"], row["lane"]) for row in a["vectors"] if row["mode"] == "short_primary"}
    stats = Counter()
    changes = []
    for before, after, actual, support in zip(original, all_paid, gated, kept, strict=True):
        key = before["visit_index"], before["receiver_id"]
        paid = bool(support["candidates"]) and key in short
        expected = after if paid else before
        if actual != expected:
            raise ValueError("A live paid lane did not match its independently projected CFO")
        if len(before["candidates"]) != len(after["candidates"]):
            raise ValueError("The original fixed-epoch phase changed signed membership")
        for x,y in zip(before["candidates"], after["candidates"], strict=True):
            if {k:v for k,v in x.items() if k != CFO} != {k:v for k,v in y.items() if k != CFO}:
                raise ValueError("The original fixed-epoch phase changed another factor field")
            change = x[CFO] != y[CFO]
            if change:
                changes.append(dict(visit=key[0], lane=key[1], paid=paid, unrefined_hz=x[CFO], refined_hz=y[CFO]))
            stats.update(all_paid_edits=int(change), kept_edits=int(change and paid), skipped_edits=int(change and not paid))
        stats.update(all_paid_attempts=int(bool(before["candidates"]) and key in short),
                     selective_attempts=int(paid), original_probes=1)
    if choice["route"] == "history":
        expected = [p if k["candidates"] else dict(p, candidates=[]) for p,k in zip(all_paid, kept, strict=True)]
        control = expected
    else:
        expected = gated
        control = all_paid
    if ap["source"]["probes"] != control or bp["source"]["probes"] != expected:
        raise ValueError("The sealed selected live output does not match its original paid evidence")
    if b["policy_clocks"]["probes"] != stats["original_probes"] or b["policy_clocks"].get("paid", 0) != stats["selective_attempts"]:
        raise ValueError("Online continuation did not advance on every original opportunity")
    for run, label in ((a, "all_paid"), (b, "selective")):
        by_lane = run["receiver_audit"]["native"]["cfo_refinement"]["lanes"]
        if (sum(x["counts"]["attempted"] for x in by_lane) != stats[f"{label}_attempts"] or
                sum(x["counts"]["changed"] for x in by_lane) != stats["all_paid_edits" if label == "all_paid" else "kept_edits"]):
            raise ValueError("Actual native spend differs from the independent signed census")
    return dict(route=choice, counts=stats, changed_lanes=changes,
                selected_factors=sum(len(p["candidates"]) for p in expected),
                selected_payload_equal=ap["source"]["probes"] == bp["source"]["probes"])


def run(root):
    from dense_geographic_trial import host

    machine = host()
    stage = load("anchored_cfo_stage", STAGE)
    root.mkdir()
    timed, scopes, native = {}, {}, {}
    for mode in ORDER:
        cache0 = resident(stage)
        output = root/mode
        prior = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall = perf_counter_ns()
        subprocess.run([sys.executable, "-IB", __file__, "worker", output, "--mode", mode], check=True, timeout=20)
        elapsed = perf_counter_ns()-wall
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cache1 = resident(stage)
        timed[mode] = dict(cache_before=cache0, cache_after=cache1, process_elapsed_ns=elapsed,
                           process_cpu_s=(after.ru_utime-prior.ru_utime)+(after.ru_stime-prior.ru_stime),
                           process_input_blocks=after.ru_inblock-prior.ru_inblock)
        scopes[mode] = json.loads((output/"scope-receipt.json").read_bytes())
        native[mode] = json.loads(stage.installed.checked(output/"detections.json", scopes[mode]["native_sha256"][7:]))
    parity = compare(*(scopes[k] for k in ORDER), *(native[k] for k in ORDER))
    stage.write(root/"result.json", dict(host=machine, clocks=timed, scopes=scopes, comparison=parity,
              stage_worker_sha256=STAGE, measured_member_visits=64, original_storage_reads=0,
              completed_solver=False, timing_boundary="authenticated staged input through selected detector seal and fresh process exit"))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "worker"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--mode", choices=ORDER)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    else:
        worker(args.mode, args.root)
