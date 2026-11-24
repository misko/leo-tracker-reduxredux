"""Check South worker output and only then join the sealed simulated reference."""

from pathlib import Path
import sys

from nomination_handoff_south import HERE, MODES, ROOT, digest, read


ARMS = ("c0", "fitted_c")


def decision(decision_name, contained):
    if decision_name not in ("complete", "withheld"):
        raise ValueError("Expected a genuine geographic publication decision")
    if decision_name == "complete":
        return "fix" if contained else "false_fix"
    return "false_withhold" if contained else "withheld"


def score(root):
    sys.path[:0] = [str(ROOT), str(ROOT/"src")]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from held_adaptive_0160_score import verified
    from isolated_salvage_south import TRUTH_SHA
    from leo.contracts.digests import canonical_digest
    from nomination_handoff_south import PROTOCOL, source_pins
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    admission = read(root/"admission.json")
    seal = root/"prediction-seal.json"
    if (read(seal) != output_seal(root) or admission["roles"] != list(MODES) or admission["source_pins"] != source_pins()
            or admission["adapter"] != digest(HERE/"nomination_handoff_south.py") or admission["protocol"] != digest(PROTOCOL)):
        raise ValueError("Score only the complete and frozen South replay")
    request = read(root/"request.json")
    clocks = {mode: read(root/mode/"clock.json") for mode in MODES}
    runs = {mode: verified(root/mode/"candidate", timing, "worker.json", request) for mode, timing in clocks.items()}
    site_key = HERE.parent/"regional-release/scoring-key.json"
    import json

    truth, = {tuple(row["truth"]) for row in json.loads(checked(site_key, TRUTH_SHA))["answers"].values()
              if row["recording"] == Path(request["recording"]).name}
    offer = read(Path(request["offer_file"]))
    clearance = face_clearance_km(offer, truth)
    if not -0.101 < clearance < -0.099:
        raise ValueError("The scored reference does not belong to the originally sealed South omission")
    pubs = {}
    for mode, run in runs.items():
        receipt = run["worker"]["receipt"]
        images, rows, terminal = run["products"]["images"], run["rows"], run["terminal"]
        if (receipt["region"] != offer or terminal["region"] != offer or set(terminal["arms"]) != set(ARMS)
                or (receipt["window_count"], receipt["counts"]["processed"]) != (1200, 1200)):
            raise ValueError("Wrong signed offer, arm inventory or original stereo visit scope")
        if receipt["decision"] == "complete":
            if len(images) != 8 or not run["sample"]["complete"] or not run["path"]["stages"]:
                raise ValueError("A fallback result must still publish the full evidence")
            for arm in ARMS:
                if canonical_digest({oid: norad for oid, norad, _ in rows[arm]}) != run["science"]["owners"][arm]:
                    raise ValueError("The ordered row trace does not bind the published owners")
        elif images or rows or any(a["latlon"] is not None or a.get("rf_rms_hz") is not None for a in terminal["arms"].values()):
            raise ValueError("A withheld fix has no numerical or image publication")
        pubs[mode] = dict(scored_decision=decision(receipt["decision"], clearance >= 0), terminal=terminal, images=images,
            sides={k: canonical_digest(run[k]) for k in ("sample", "path") if run[k]},
            grid_points=run["sample"]["evaluated_points"] if run["sample"] else None,
            science=run["science"], ordered_owner_count={arm: len(rows.get(arm, [])) for arm in ARMS},
            error_km={arm: distance_km(truth, data["latlon"]) if data["latlon"] else None for arm, data in terminal["arms"].items()},
            clocks=clocks[mode] | {k: run["trace"][k] for k in ("publication_elapsed_s", "publication_cpu_s", "solve")})
    (routed,) = read(root/"routed/risk-route.json")["solves"]
    installed = runs["installed"]
    former = admission["historical_installed"]["near-omitted"]
    historical = {"arms": installed["terminal"]["arms"] == former["arms"], "owners": installed["science"]["owners"] == former["owners"],
                  "orbit_policy": installed["terminal"]["orbit_policy"] == former["orbit_policy"]}
    write(root/"result.json", dict(scope="same signed 20 ms South simulated saved packet to publication and exit", offer=offer,
          simulated_receiver=truth, clearance_km=clearance, historical_installed=admission["historical_installed"],
          historical_installed_parity=historical, score_key=TRUTH_SHA, prediction_sha256=digest(seal), admission=admission,
          pubs=pubs, owner_delta={arm: owner_delta(installed["rows"].get(arm, []), runs["routed"]["rows"].get(arm, [])) for arm in ARMS},
          route=routed, render=read(root/"routed/render-usage.json"),
          orbit_recovery=read(root/"routed/live-corner.json"), ports=read(root/"routed/candidate/ports.json"),
          waveform_reads=0, backing_reads=0))
