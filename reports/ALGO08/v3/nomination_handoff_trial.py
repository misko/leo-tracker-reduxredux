"""Exercise one real causal nomination handoff up to the installed final gate."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
PAIR = Path("/dev/shm/leo-v3-history-risk-0004-pair01")
PINS = {
    "routed/binding.json": "d78341a9d8a638033808ff15b2ac9fd8c19b727b2a895a3add07db8fb3e1860a",
    "routed/risk-route.json": "873d97f662f93f0ed9625b6400f9187569db9c3b9b5c6d86196c1d4f182ae220",
    "named/candidate/worker.json": "528fb35edc0eb896878b7e03312e3dd92d4782df80ba0447d5934c87b33d5793",
}


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(tick):
    return dict(cpu_ns=process_time_ns()-tick[0], elapsed_ns=perf_counter_ns()-tick[1])


def run(output):
    import empty_bootstrap as boot
    from aperture_trial import solve, write
    from exact_named_route import exact_ports, resident_path
    from history_risk_0004 import ARCHIVE, AUTHORITY, CUTOFF, NATIVE_PIN, OFFER_PIN, deny_original

    sys.addaudithook(deny_original)
    start = now()
    _, spec, sources, publication, _ = boot.load_runtime()
    from leo.analysis.localization_v3 import position
    from leo.contracts.digests import canonical_digest
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner
    from cold_finalist_race import refine
    from mixture_finish import digest
    from nomination_handoff import NominationHandoff

    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Expected a fresh tmpfs witness")
    baseline, routed, named = (json.loads(boot.checked(resident_path(PAIR/key), pin)) for key, pin in PINS.items())
    bound = baseline["input"]
    req = json.loads(resident_path(Path(bound["request"])).read_bytes())
    native = json.loads(boot.checked(resident_path(Path(req["native_file"])), NATIVE_PIN))
    offer = json.loads(boot.checked(resident_path(Path(req["offer_file"])), OFFER_PIN))
    archive = resident_path(Path(bound["archive"]))
    if (req["local_archive"]["snapshots_sha256"] != ARCHIVE or req["causal_cutoff_utc_ns"] != CUTOFF
            or canonical_digest(native) != "sha256:"+NATIVE_PIN
            or native["source"]["raw_recording_authority_digest"] != AUTHORITY
            or bound["portable"] is not None or Path(req["local_archive"]["root"]) != archive):
        raise ValueError("The original signed detector, offer or request-specific catalogue changed")
    released = named["receipt"]["screened_nomination"]
    old = routed["solves"][0]["lean_attempts"][0]
    if old["reason"] != "repair_rejection_cap" or old["cold"]["scores"] != released["screen_c0_scores"]:
        raise ValueError("The archived routes do not agree at exact original nomination")
    trace = dict(original_references=PINS, original_archive=ARCHIVE, input_sha256=NATIVE_PIN, offer_sha256=OFFER_PIN,
                 existing_clocks={k: old[k] for k in ("cold_clocks", "candidate_pre_evidence_clocks", "fallback_clocks")},
                 released_screen=released, source_admission=elapsed(start))
    trace["source_pins"] = {p.name: sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), HERE/"nomination_handoff.py", HERE/"cold_finalist_race.py", HERE/"nomination-handoff-protocol.md")}
    trace["installed_sources"] = list(sources)
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, verified_tle=Counter())
    ordinary = algo08_position.solve
    spec["startup"] = "stock"  # Already installed by the checked bootstrap.

    def observe(document, reader, assets, region):
        ready = now()

        def stop_after_nomination(prepared, search, native_bound, _stages, *, selected_evidence):
            trace["preparation"] = elapsed(ready)
            if prepared["status"] != "inputs_prepared":
                raise ValueError("The expected saved scan was unavailable")
            started = now()
            handoff = NominationHandoff(v5_core, v5_screen_winner, v5_core.ranked_initial_nodes, trace)
            trace["port_setup"] = elapsed(started)
            started = now()
            with handoff.producer():
                _, _, _, work = refine("race", prepared, search, native_bound, checkpoint=handoff.capture)
            trace["cold_producer"] = elapsed(started)
            trace["cold_prefix"] = work
            if work["scores"] != old["cold"]["scores"] or handoff.checkpoint is None:
                raise ValueError("The new actual exact producer did not reproduce the sealed ordered cold scores")
            fit = position.fit
            updates = []

            def measured(problem, anchor, **options):
                began = now()
                result = fit(problem, anchor, **options)
                updates.append(dict(anchor=anchor.copy(), reference=problem.reference.copy(),
                                    score=result["score"], position=result["parameters"], time=elapsed(began)))
                return result

            clock = now()
            with handoff.fallback(), patch.object(position, "fit", measured):
                scan = v5_core.scan_context(prepared, search, digest(prepared["noise"]), native_bound, "previous")
                initial, branches = v5_core.initial_selection(scan)
            trace["named_resume"] = elapsed(clock)
            trace["named_winner_updates"] = updates
            gate = initial["choices"][0]["arms"]["c0"]["metrics"]
            trace["nomination"] = dict(branches=branches, accepted_tracks=gate["accepted_tracks"],
                                       total_tracks=len(gate["tracks"]), ordered_gate_sha256=canonical_digest(
                                           [[r["component"], bool(r["compatible"])] for r in gate["tracks"]]))
            if (len(updates) != 3 or handoff.counts["rank_reuses"] != 1 or handoff.counts["prefixes_reused"] != 3):
                raise ValueError("The original named resume failed to reuse exactly the ranked prefix")
            trace["rank"] = audit["rank"]
            return dict(status="nomination_slice", reason=None, arms={a: dict(latlon=None) for a in ("c0", "fitted_c")})

        with exact_ports(bound, req, audit), patch.object(v5_core, "infer", stop_after_nomination):
            return ordinary(document, reader, assets, region)

    try:
        with patch.object(algo08_position, "solve", observe):
            trial = solve(publication, spec, native, archive, offer)
        metrics = trial["screened_nomination"]
        trace["measured_screen"] = metrics
        fields = "screen_c0_scores", "completed_c0_score", "winning_rank", "ranks", "fallback"
        if any(metrics[key] != released[key] for key in fields):
            raise ValueError("Reconstructed original nomination diverged from the fresh named control")
    except Exception as error:
        trace["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write(output, trace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
