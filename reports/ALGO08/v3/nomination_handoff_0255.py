"""Check the frozen nomination handoff on the already sealed DS30-0255 pair."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from nomination_handoff_trial import elapsed, now
from solver_exception_0022 import digest


BASE = Path("/dev/shm/leo-v3-unseen-saved-0255-result01")
BASE_PIN = "e8c0b5cea1efa3940e8c5ca8c9301405234c48aeb645d073a22ae2908f20f280"
HANDOFF_PIN = "28de1e1061c174d8d83ada8441ae0ee242e22e9c5113c07f48371e26142636ef"


def saved():
    from empty_bootstrap import checked

    result = json.loads(checked(BASE / "result.json", BASE_PIN))
    if not all(result["checks"].values()) or result["admission"]["assignment"]["selected"] != "DS30-0255":
        raise ValueError("Require the original complete matched holdout")
    return result


def slice_trial(output):
    import empty_bootstrap as boot
    from aperture_trial import solve, write
    from clean_saved_publication import load_job
    from dense_geographic_trial import host
    from exact_named_route import exact_ports, resident_path
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    starting = now()
    _, spec, _, publication, _ = boot.load_runtime()
    import cold_finalist_race as race
    from leo.analysis.localization_v3 import position
    from mixture_finish import digest as noise_digest
    from nomination_handoff import NominationHandoff, RACE_SOURCE, capture_race
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner

    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh private tmpfs witness")
    boot.checked(HERE / "nomination_handoff.py", HANDOFF_PIN)
    boot.checked(Path(race.__file__), RACE_SOURCE)
    original = saved()
    if host() != original["admission"]["machine"]:
        raise ValueError("Use the same low-priority one-core Gauss environment")
    bound, req = load_job(BASE / "job.json", original["admission"]["job_sha256"])
    packet = json.loads(boot.checked(Path(req["native_file"]), req["native_sha256"]))
    offer = json.loads(boot.checked(Path(req["offer_file"]), req["offer_sha256"]))
    named = original["jobs"]["installed"]["publication"]["worker"]["receipt"]["screened_nomination"]
    old = original["candidate_traces"]["risk-route.json"]["solves"][0]["lean_attempts"][0]
    if old["reason"] != "repair_original_joint_pair_gate" or old["cold"]["scores"] != named["screen_c0_scores"]:
        raise ValueError("The actual fallback must have the exactly matched archived ordered scores")
    trace = dict(source_admission=elapsed(starting), before=BASE_PIN, named_screen=named,
                 sources={path.name: digest(path.read_bytes()) for path in (
                     Path(__file__), HERE / "nomination_handoff.py", Path(race.__file__))})
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, verified_tle=Counter())
    original_solve = algo08_position.solve
    spec["startup"] = "stock"

    def observe(document, reader, assets, region):
        prepared_at = now()

        def checkpoint(prepared, search, native_bound, _stages, *, selected_evidence):
            trace["paid_preparation"] = elapsed(prepared_at)
            if prepared["status"] != "inputs_prepared":
                raise ValueError("Expected the exact active saved scan")
            handoff = NominationHandoff(v5_core, v5_screen_winner, v5_core.ranked_initial_nodes, trace)
            started = now()
            _, _, _, work = capture_race(race, handoff)("race", prepared, search, native_bound)
            trace["producer"] = elapsed(started)
            trace["cold"] = work
            if work["scores"] != old["cold"]["scores"] or handoff.checkpoint is None:
                raise ValueError("The real producer did not yield all three exact archived prefixes")
            fit, counts = position.fit, Counter()

            def measured(*args, **kwargs):
                counts["winner_updates"] += 1
                return fit(*args, **kwargs)

            started = now()
            with handoff.fallback(), patch.object(position, "fit", measured):
                scan = v5_core.scan_context(prepared, search, noise_digest(prepared["noise"]), native_bound, "previous")
                initial, _ = v5_core.initial_selection(scan)
            trace["resumed_screen"] = elapsed(started)
            trace["winner_updates"] = counts["winner_updates"]
            trace["nomination_gate_accepted_tracks"] = initial["choices"][0]["arms"]["c0"]["metrics"]["accepted_tracks"]
            if (counts["winner_updates"] != 3 or handoff.counts["scan_reuses"] != 1
                    or handoff.counts["rank_reuses"] != 1 or handoff.counts["prefixes_reused"] != 3):
                raise ValueError("The live identity guard declined the named replay")
            return dict(status="nomination_slice", reason=None, arms={arm: dict(latlon=None) for arm in ("c0", "fitted_c")})

        with exact_ports(bound, req, audit), patch.object(v5_core, "infer", checkpoint):
            return original_solve(document, reader, assets, region)

    try:
        with patch.object(algo08_position, "solve", observe):
            result = solve(publication, spec, packet, Path(bound["archive"]), offer)
        screen = result["screened_nomination"]
        trace["measured_screen"] = screen
        if any(screen[key] != named[key] for key in ("screen_c0_scores", "completed_c0_score", "winning_rank", "ranks", "fallback")):
            raise ValueError("The resumed original nomination differs from the sealed installed screen")
        historical = original["candidate_traces"]["ports"]["rank"][0]["cpu_ns"] / 1e9
        historical += original["jobs"]["routed"]["publication"]["worker"]["receipt"]["screened_nomination"]["initial_screen_cpu_s"]
        trace["scope_estimate_cpu_s"] = historical - trace["resumed_screen"]["cpu_ns"] / 1e9
        trace["qualified"] = True
    except Exception as error:
        trace["qualified"] = False
        trace["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        trace["total"] = elapsed(starting)
        trace["rank"] = audit["rank"]
        write(output, trace)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    slice_trial(cli.parse_args().output)
