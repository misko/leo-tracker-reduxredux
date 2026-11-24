"""Reduce original stock/lean initializer evidence without preparing a solver."""

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
STOCK = Path("/opt/leo-algo08/algo08v3/payload/tools")
INSTALLED = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo")
CHARTED = Path("/tmp/leo-v3-integrated-original-batch/reports/ALGO08/v3")
CONTROL = Path("/dev/shm/leo-v3-history-risk-0004-pair01")
HERE = Path(__file__).resolve().parent
SOURCE_PINS = {
    STOCK / "algo08_position.py": "cd5c728e7f81b675b796d69713ca66e601a54534bdbf1d606dc8ecf16c4c138c",
    STOCK / "pipeline_eval/variants/v5_core.py": "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407",
    STOCK / "pipeline_eval/variants/v5_screen_winner.py": "f276b8ee2f4c059d571da874b2fbef6f6b13d08078e30fd93950428f8c10fb70",
    STOCK / "pipeline_eval/variants/algo08_stock_finish.py": "89dbecd98b182562830623c93b96e05f3880b9b791cd8bc87ec66e618ccb5a11",
    INSTALLED / "analysis/localization_v3/position.py": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
    INSTALLED / "analysis/localization_v3/discovery.py": "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a",
    INSTALLED / "presentation/position_path.py": "e3ca8039ae43cc168f9e9361dd1e7c89b41d3c80d4eecbd0b67eb996582905d6",
    CHARTED / "cold_finalist_race.py": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
    CHARTED / "combined_successor.py": "7c8a28b3e0008e370375eb10356a2a3f22db05c7fa2c90346440f1a0c760b228",
    CHARTED / "two_centre_seeds.py": "3f6867740f7df3e1278d56d7b35075541fd694c76e759ac175a4037c8de74897",
}
CASES = {
    "0220": ("d307ff5f4a02fe144eb1547574728a46bf19b4365d971687c471adea65aa4755",
             "41f1d38215156a95deebf06bfe10237f477daa9c5b07d4eca8b09b3fdc4e137a",
             "982156b3591877e1f875d11dd7fc9e13618cb6fc5db013d37051a955ec83ff4b",
             "4d73fca4e001f27faf92106bb0180f7f7bfc31d093f6a11e734061de4b8bee2a",
             "fdb6cf95336e4c0e43e53333f8cbc8217fbc566670dad71013ddebbc56e19cbe"),
    "0086": ("407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439",
             "e107c4c60c2db6fdeea0f75419835cef2605b16f90456ef14b27d5e9b9d90fde",
             "915ddc6e1c49e4725bef885ca418e7aff3e4a938464a4c2a9a1e58e14e3d06a9",
             "36c964fe7e2cf12ed2d322bf85dc52f82f3f67877fbeb929ce35873f63b2bcf5",
             "e0e41ceb1380f5879d390e4a7af14dad5b1a1fdb836f701c8360a853c17e1952"),
}


def checked(path, digest):
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Archived source or receipt changed: {path}")
    return body


def document(path, digest):
    return json.loads(checked(path, digest))


def score_links(stock, lean):
    """Numerical links leave assignment and phase identities unresolved."""
    if len(stock) != 3 or len(lean) != 3 or not all(isfinite(x) for x in (*stock, *lean)):
        raise ValueError("Expected two complete ordered three-finalist score vectors")
    bits = [float(score).hex() for score in lean]
    return [[index+1 for index, value in enumerate(bits) if value == float(score).hex()] for score in stock]


def score_evidence(stock, cold):
    if stock["fallback"] or stock["ranks"] != [0, 1, 2] or stock["early_fits"] != 6 or stock["finish_fits"] != 3:
        raise ValueError("The ordinary stock two-refresh screen is incomplete")
    a, b = stock["screen_c0_scores"], cold["scores"]
    links = score_links(a, b)
    if a.index(min(a)) != stock["winning_rank"] or b.index(min(b))+1 != cold["branch"]:
        raise ValueError("An archived winner differs from the original finite-score selector")
    return dict(stock_two_refresh_scores=a, lean_two_refresh_scores=b, stock_rank_zero_based=stock["winning_rank"],
                lean_chosen_branch_one_based=cold["branch"], lean_round_two_links_by_stock_rank=links,
                stock_winner_score_hex=float(a[stock["winning_rank"]]).hex(),
                stock_winner_linked_branches=links[stock["winning_rank"]])


def scout_choices(trace):
    rows = trace["requested"]
    if len({row["index"] for row in rows}) != len(rows) or not rows or any(
            len(row["per_radio"]) != 2 or not all(isfinite(x) for x in row["per_radio"]) for row in rows):
        raise ValueError("Malformed scout cost rows")
    minimax = min(rows, key=lambda r: (max(r["per_radio"]), sum(r["per_radio"]), r["index"]))["index"]
    if minimax != trace["picked"]:
        raise ValueError("The archived scout does not reproduce its released decision")
    return dict(minimax=minimax, mean=min(rows, key=lambda r: (sum(r["per_radio"]), r["index"]))["index"],
                per_radio=[min(rows, key=lambda r: (r["per_radio"][i], r["index"]))["index"] for i in range(2)],
                paid_centres=trace["paid_centres"], scout_rows=rows, scout_to_signature_link_available=False)


def rank_rows(signature):
    rows = {name: [idx, norad, alias] for name, idx, norad, alias in signature}
    if len(rows) != len(signature):
        raise ValueError("Duplicate component in signed assignment")
    return rows


def field_case(label, pins):
    pair_pin, admit_pin, witness_pin, worker_pin, path_pin = pins
    name = "DS30-"+label
    original = FIELD / "cases" / name
    pair = document(original / "pair.json", pair_pin)
    stock_pin = pair["attempt_result_sha256"]["installed"]
    named = document(original / "installed/attempt-000001/result.json", stock_pin)
    base = Path(f"/tmp/leo-v3-field-stock-saved-{label}-01")
    admit = document(base / "admission.json", admit_pin)
    output = base / "candidate"
    witness = document(output / "exact-named-raw-witness.json", witness_pin)
    worker = document(output / "crossover-worker.json", worker_pin)
    (position_path,) = output.glob("fast-scan-standard-v2/*/*/position-path.json")
    path = document(position_path, path_pin)["document"]
    receipt = worker["receipt"]
    binding = path["binding"]
    if (not pair["verified_pair"] or pair["generation"] != 1 or admit["case"] != name
            or admit["installed_result_sha256"] != stock_pin or worker["waveform_reads"]
            or worker["verified_handoffs"] != 1 or named["native_sha256"] != admit["native_sha256"]
            or binding["input_sha256"] != admit["native_sha256"] or binding["terminal_sha256"] != receipt["terminal_sha256"]
            or named["raw_identity"] != admit["raw_authority"] or receipt["region"] != named["evidence"]["receipt"]["region"]):
        raise ValueError("The archived stock and lean screens differ in saved input or offer")
    risk = witness["ports"]["history_risk"]
    attempt, = risk["lean_attempts"]
    cold, two = attempt["cold"], risk["two_centre_rank"]
    details = score_evidence(named["evidence"]["receipt"]["screened_nomination"], cold)
    signatures, completed = two["finalist_signatures"], cold["completed"]
    if len(signatures) != 3 or [row["branch"] for row in completed] != [1, 2, 3]:
        raise ValueError("The lean path must carry all three observed branches")
    branches = []
    for signature, phase in zip(signatures, completed, strict=True):
        rows = rank_rows(signature)
        labels = sorted({row[0] for row in rows.values()})
        if (len(phase["posterior"]) != len(labels) or phase["labels"] != labels
                or not all(isfinite(v) for v in (*phase["posterior"], *phase["point"]))
                or phase["score"] != cold["scores"][phase["branch"]-1]):
            raise ValueError("Saved phase labels differ from their signed finalist")
        branches.append(dict(branch=phase["branch"], signature=rows, posterior_label_order=labels,
                             continuation_east_north_km=phase["point"],
                             continuation_phase_s=[min(15., max(-15., v)) for v in phase["posterior"]]))
    chosen = branches[cold["branch"]-1]["signature"]
    linked_delta = {}
    for idx in details["stock_winner_linked_branches"]:
        linked = branches[idx-1]["signature"]
        linked_delta[idx] = [[key, chosen.get(key), linked.get(key)] for key in sorted(chosen.keys() | linked.keys())
                             if chosen.get(key) != linked.get(key)]
    if attempt["decision"] == "fallback":
        named_screen = named["evidence"]["receipt"]["screened_nomination"]
        saved_screen = receipt["screened_nomination"]
        if any(saved_screen[k] != named_screen[k] for k in ("screen_c0_scores","winning_rank","completed_c0_score")):
            raise ValueError("Routed fallback and deployed ordinary screen differ")
    return details | dict(native_sha256=admit["native_sha256"], route=attempt["decision"], reason=attempt.get("reason"),
                           branches=branches, chosen_versus_scalar_linked_branch_signatures=linked_delta,
                           stock_assignment_identity_available=False, stock_continuation_state_available=False,
                           actual_rank_calls=witness["ports"]["rank"], scout=scout_choices(two),
                           final_path_round_fields=sorted(path["stages"][0]["arms"]["c0"]["rounds"][0]),
                           final_path_phase_vector_available=False, parent_pair_sha256=pair_pin,
                           witness_sha256=witness_pin, position_path_sha256=path_pin)


def older_control():
    route_pin = "873d97f662f93f0ed9625b6400f9187569db9c3b9b5c6d86196c1d4f182ae220"
    named_pin = "528fb35edc0eb896878b7e03312e3dd92d4782df80ba0447d5934c87b33d5793"
    routed_pin = "6bcff923caddf9bf7380cbe11a991fe70b60702b85808d0bcede052836b4494c"
    slice_pin = "5e91cd497cb61a875e26ee19f950bf82406cf42fecdf0623c13e17cd39408ae2"
    (solve,) = document(CONTROL / "routed/risk-route.json", route_pin)["solves"]
    (attempt,) = solve["lean_attempts"]
    named = document(CONTROL / "named/candidate/worker.json", named_pin)
    routed = document(CONTROL / "routed/candidate/worker.json", routed_pin)
    if named["native_sha256"] != routed["native_sha256"] or not (named["no_waveform"] and routed["no_waveform"]):
        raise ValueError("Historical same-input cold comparison lost custody")
    handoff = document(HERE / "measurements/nomination-handoff-0004-slice.json", slice_pin)
    checkpoints = handoff["nomination_handoff"]
    screen = named["receipt"]["screened_nomination"]
    if (checkpoints["prefixes_reused"] != 3 or checkpoints["rank_reuses"] != 1
            or handoff["released_screen"]["screen_c0_scores"] != screen["screen_c0_scores"]):
        raise ValueError("The historical exact checkpoint control differs")
    return score_evidence(screen, attempt["cold"]) | dict(route=attempt["decision"], reason=attempt["reason"],
        guarded_existing_exact_checkpoint_reuse=checkpoints["prefixes_reused"], route_sha256=route_pin,
        stock_worker_sha256=named_pin, archived_checkpoint_sha256=slice_pin)


def audit():
    for path, checksum in SOURCE_PINS.items():
        checked(path, checksum)
    cases = {"DS30-"+name: field_case(name, pins) for name, pins in CASES.items()}
    cases["DS30-0004"] = older_control()
    return dict(cases=cases, source_sha256={str(path): digest for path, digest in SOURCE_PINS.items()},
                survey_reads=0, waveform_reads=0, orbit_body_reads=0, solver_workers=0, new_proposal=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump(audit(), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
