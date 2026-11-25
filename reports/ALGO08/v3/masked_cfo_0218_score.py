"""Verify the original ordinary publication before scoring a sealed CFO replay."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from held_shrink_0019_score import verify_publication  # noqa: E402
from masked_cfo_0218 import CAMPAIGN, CASE, status  # noqa: E402
from masked_cfo_saved import saved  # noqa: E402
from sparse8_cfo_epoch_trial import geography, scientific_grid  # noqa: E402


def read_cell(root, pins, *, enabled):
    plan = saved.document(root/"plan.json", pins["plan"])
    clock = saved.document(root/"clock.json", pins["clock"])
    scope = saved.document(root/"masked-cfo-observation-witness.json", pins["observation"])
    run = saved.document(root/"receipt.json", pins["receipt"])
    if (clock["exit_code"] != 0 or plan["case"] != CASE or plan["enabled"] != enabled or plan["probe"]
            or scope["stage_plan_sha256"] != pins["plan"] or scope["enabled"] != enabled
            or scope["decision"] != run["receipt"]["decision"] or run["handoffs"] != 1
            or run["waveform_reads"] or scope["waveform_reads"] or scope["forecast_cache_reads"]
            or run["input"] != plan["original_native_sha256"] or scope["native_sha256"] != run["input"]):
        raise ValueError("Each compared cell needs an exited, correctly bound saved publication")
    return plan, clock, scope, run


def graph_fields(witness):
    graph = witness["ports"]["graph"].get("graph", {})
    return {key:graph[key] for key in ("assigned", "tracks", "calls", "edge_lanes", "edges") if key in graph}


def require_equal(actual, expected):
    differences = sorted(key for key in actual.keys() | expected.keys() if actual.get(key) != expected.get(key))
    if differences:
        raise ValueError(f"Ordinary saved science differs from the official raw successor: {differences}")


def verify(root, verification_pins):
    if not status()["verified_pair"]:
        raise ValueError("The original paired scientific results are still unavailable")
    case = CAMPAIGN/"cases"/CASE
    pair = saved.document(case/"pair.json")
    roles = {role: saved.document(case/role/f"attempt-{pair['generation']:06d}"/"result.json",
                                  pair["attempt_result_sha256"][role]) for role in ("installed","successor")}
    raw = roles["successor"]
    ordinary = read_cell(root/"ordinary", verification_pins["ordinary"], enabled=False)
    corrected = None
    if "corrected" in verification_pins:
        corrected = read_cell(root/"corrected", verification_pins["corrected"], enabled=True)
    for plan, _, _, run in (ordinary,) if corrected is None else (ordinary,corrected):
        if (plan["original"]["raw_attempt_sha256"] != pair["attempt_result_sha256"]["successor"]
                or plan["original"]["verified_field_pair_sha256"] != saved.identifier(case/"pair.json")
                or run["input"] != raw["native_sha256"] or plan["original_archive"] != raw["raw_identity"]["archive_sha256"]):
            raise ValueError("Saved cell differs from the enrolled official original raw result")
    raw_publication = case/"successor"/f"attempt-{pair['generation']:06d}"/"publication"
    raw_receipt = raw["evidence"]["receipt"]
    raw_witness_pin = ordinary[0]["original"]["original_witness"]
    local = root/"ordinary/substituted"
    local_run = ordinary[3]
    local_receipt = local_run["receipt"]
    offer = raw_receipt["region"]
    saved.start_runtime().load_runtime()
    terminal, science, _ = verify_publication(local, local_receipt, local_run["witness"], raw["native_sha256"], offer)
    if raw_receipt["decision"] == "complete":
        old_terminal, old_science, _ = verify_publication(raw_publication, raw_receipt, raw_witness_pin,
                                                        raw["native_sha256"], offer)
        before = saved.document(raw_publication/"exact-named-raw-witness.json", raw_witness_pin)
        after = saved.document(local/"exact-named-raw-witness.json", local_run["witness"])
        require_equal(
            dict(terminal=terminal, owners=science["owner_rows"], images=science["images"], path=science["sidecars"]["path"],
                 grid=scientific_grid(local), graph=graph_fields(after), source=after["source_sha256"]),
            dict(terminal=old_terminal, owners=old_science["owner_rows"], images=old_science["images"],
                 path=old_science["sidecars"]["path"], grid=scientific_grid(raw_publication), graph=graph_fields(before),
                 source=before["source_sha256"]),
        )
    else:
        require_equal(dict(decision=local_receipt["decision"], reason=terminal.get("reason")),
                      dict(decision=raw_receipt["decision"], reason=raw["evidence"]["reason"]))
    scored = dict(case=CASE, exact_ordinary_scientific_parity=True, ordinary_exit=ordinary[1],
                  raw_clocks={role:row["process"] for role,row in roles.items()}, original_native_sha256=raw["native_sha256"])
    if corrected is None:
        print(saved.write(root/"ordinary-parity.json", scored))
        return
    _, clock, overlay, run = corrected
    result, evidence, figures = verify_publication(root/"corrected/substituted", run["receipt"], run["witness"],
                                                    raw["native_sha256"], offer)
    scored.update(corrected_exit=clock, corrected_decision=run["receipt"]["decision"], correction=overlay, media=figures)
    # Only now are both prediction and parity sealed. Open the official
    # held survey for the accuracy join.
    from tools.pipeline_eval.scoring import distance_km

    site = geography(CASE)
    def arm_result(arms):
        return {arm: None if row["latlon"] is None else dict(error_m=1000*distance_km(site,row["latlon"]),
                                                            conditional_rf_hz=row["rf_rms_hz"])
                for arm,row in arms.items()}
    scored["arms"] = {
        "installed": arm_result(roles["installed"]["evidence"]["arms"]),
        "ordinary": arm_result(terminal["arms"]),
        "corrected": arm_result(result["arms"]),
    }
    if run["receipt"]["decision"] == "complete":
        for arm in saved.ARMS:
            next_row = scored["arms"]["corrected"][arm]
            next_row.update(owners=len(evidence["owner_rows"][arm]),
                            all_owned_rf_hz=evidence["detail"]["arms"][arm]["residual_rms_hz"])
    print(saved.write(root/"score.json", scored))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("verification_pins", type=Path)
    cli.add_argument("--pin", required=True)
    args = cli.parse_args()
    verify(args.root, saved.document(args.verification_pins, args.pin))
