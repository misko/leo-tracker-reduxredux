"""Audit the fixed-state residual change identifiable from two saved CFO trials."""

from collections import Counter
from hashlib import sha256
import json
from math import fsum, isfinite, sqrt
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARMS = ("c0", "fitted_c")
HERTZ = "fractional_tracking_cfo_hz"
ORIGINAL = Path("/dev/shm/leo-v3-cfo-epoch-0019-saved01")
BLEND = Path("/dev/shm/leo-v3-held-shrink-0019-ram01/output")
TRANSFER = Path("/dev/shm/leo-v3-held-shrink-0274-stage02")
SEALS = {
    "original19": "ac8d1e2a7d35415e4d0e7c1541f888c5f136d2aa2976c48eaacdd1bdfe2ab1bf",
    "blend19": "57a3ddb682be7959bff5dc159c00c9b3df4f72e67b9e9ec18e946fd5c87a75fe",
    "original274": "2fcf522f59dc6739aa51671005d82041c343109bd600575a198651164c58d745",
    "blend274": "47027dc87154c476cd72844080bdc99ba86e9f1d14cc45ab8be46019461efcc0",
}
ORIGINAL_0019 = "1acd2fcf8104fe990eaf40c82848e723de2da0c74f1ac1f29f59c659442d8d0d"


def digest(document):
    body = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(body.encode()).hexdigest()


def read(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved binding changed for {path}")
    return json.loads(data)


def signed_edits(original, derived, ledger):
    """Bind edits by session, radio and hardware counter, retaining all other factors."""
    left, right = (doc["source"] for doc in (original, derived))
    fields = ("session_id", "sample_rate_hz", "probe_ms", "raw_recording_authority_digest",
              "input_manifest_sha256", "capture_start_utc_ns", "capture_end_utc_ns")
    if (any(left[k] != right[k] for k in fields)
            or any(original[k] != derived[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter"))):
        raise ValueError("The exact capture or time basis changed")
    by_id = {edit["observation_id"]: edit for edit in ledger}
    if len(by_id) != len(ledger):
        raise ValueError("Duplicate edited observation")
    delta, winners, seen = {}, set(), set()
    for before, after in zip(left["probes"], right["probes"], strict=True):
        session = left["session_id"]
        radio, counter = before["receiver_id"], before["valid_start_counter"]
        oid = "sha256:" + sha256(f"{session}:{radio}:{counter}".encode()).hexdigest()
        if oid in seen:
            raise ValueError("Duplicate native observation identity")
        seen.add(oid)
        if any(c["passed_fractional_margin_gate"] is True for c in before["candidates"]):
            winners.add(oid)
        if oid not in by_id:
            if before != after:
                raise ValueError("Unedited control differs from the ordinary probe")
            continue
        edit = by_id[oid]
        (old,), (new,) = (before["candidates"], after["candidates"])
        if (oid not in winners or (edit["radio"], edit["counter"], edit["visit"]) != (
                radio, counter, before["visit_index"])
                or (edit["original_hz"], edit["updated_hz"]) != (old[HERTZ], new[HERTZ])
                or before | {"candidates": [old | {HERTZ: new[HERTZ]}]} != after):
            raise ValueError("Changed probe differs from the sealed CFO-only edit")
        delta[oid] = new[HERTZ] - old[HERTZ]
    if delta.keys() != by_id.keys() or any(not isfinite(d) or d == 0 for d in delta.values()):
        raise ValueError("The presealed signed edit ledger is incomplete")
    return delta, winners, len(left["probes"]) - len(delta)


def owner_rows(witness, arm, winners):
    evidence = witness["evidence"]
    rows = evidence["owner_rows"][arm]
    result = {oid: (norad, role) for oid, norad, role in rows}
    summary = evidence["detail"]["arms"][arm]
    owner_digest = digest({oid: norad for oid, (norad, _) in result.items()})
    if (owner_digest != summary["owner_sha256"] or owner_digest != evidence["owner_maps"][arm]
            or len(result) != len(rows) or len(result) != summary["associated_points"]
            or not result.keys() <= winners
            or {role for _, role in result.values()} - {"conditional", "predictive"}):
        raise ValueError("Selected owner evidence does not bind exact native winners and roles")
    return result


def fixed_bound(count, rms, deltas):
    edit_square = fsum(d*d for d in deltas)
    norm, edit_norm = rms * sqrt(count), sqrt(edit_square)
    cross = 2 * norm * edit_norm
    return dict(ordinary_SSE_hz2=norm**2, edit_SSE_hz2=edit_square,
                fixed_RMS_interval_hz=[abs(norm-edit_norm)/sqrt(count), (norm+edit_norm)/sqrt(count)],
                fixed_SSE_change_interval_hz2=[edit_square-cross, edit_square+cross],
                fixed_RMS_hz=None, fixed_SSE_change_hz2=None, edited_owned_original_RMS_hz=None,
                edited_owned_fixed_RMS_hz=None, edited_owned_SSE_change_hz2=None)


def overlap(ordinary, derived, edited):
    common = ordinary.keys() & derived.keys()
    removed, added = ordinary.keys() - derived.keys(), derived.keys() - ordinary.keys()
    return dict(ordinary_owned=len(ordinary), derived_owned=len(derived), common=len(common),
                dropped=len(removed), added=len(added), common_same_norad_and_role=sum(
                    ordinary[oid] == derived[oid] for oid in common),
                common_norad_changed=sum(ordinary[oid][0] != derived[oid][0] for oid in common),
                common_role_changed=sum(ordinary[oid][1] != derived[oid][1] for oid in common),
                edited_common=len(common & edited), edited_dropped=len(removed & edited),
                edited_added=len(added & edited), unedited_common=len(common - edited))


def predictive_rms(roster, captured, manifest_rms, terminal_arm):
    curve_owners = [(oid, arc["norad"], role) for role, key in
                    (("conditional", "curves"), ("predictive", "predictive"))
                    for arc in captured[key].values() for oid in arc["ids"]]
    selected = {(oid, *label) for oid, label in roster.items()}
    conditional = sum(role == "conditional" for _, role in roster.values())
    fit = captured["fit"]
    if (len(curve_owners) != len(selected) or set(curve_owners) != selected
            or fit["latlon"] != terminal_arm["latlon"] or fit["rf_rms_hz"] != terminal_arm["rf_rms_hz"]
            or conditional == len(selected)):
        raise ValueError("The terminal conditional RMS is not bound to the published role partition")
    predictive = len(selected) - conditional
    square = (len(selected) * manifest_rms**2 - conditional * terminal_arm["rf_rms_hz"]**2) / predictive
    return dict(conditional=conditional, predictive=predictive, predictive_RMS_hz=sqrt(square))


def load_publication(root, receipt, witness_pin, native_pin):
    witness = read(root / "exact-named-raw-witness.json", witness_pin)
    terminal = read(root / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json",
                    receipt["terminal_sha256"])
    detail = witness["evidence"]["detail"]
    if (terminal["native_sha256"] != native_pin or detail["input_sha256"] != native_pin
            or detail["terminal_sha256"] != receipt["terminal_sha256"]
            or detail["region"] != terminal["region"] or set(terminal["arms"]) != set(ARMS)
            or receipt["decision"] != "complete" or terminal["decision"] != "ok"):
        raise ValueError("Saved numerical publication changed")
    return witness, terminal


def capsule(root, seal_pin, case):
    seal = read(root / "prediction-seal.json", seal_pin)
    plan = read(root / "plan.json", seal["plan_sha256"])
    run = read(root / "receipt.json", seal["receipt"])
    timing = read(root / "clock.json", seal["clock"])
    if (run["case"] != case or plan["case"] != case or timing["exit_code"] or seal["survey_reads"]
            or seal["waveform_reads"] or run["waveform_reads"] or not run["graph_replayed"]
            or run["handoffs"] != 1 or run["plan_sha256"] != seal["plan_sha256"]
            or run["input"] != plan["change"]["derived_native_sha256"]):
        raise ValueError("Malformed sealed saved handoff")
    native = read(root / "derived-native.json", run["input"])
    publication = load_publication(root / "substituted", run["receipt"], run["witness"], run["input"])
    return native, publication, plan, run


def run_case(case):
    if case == "DS30-0019":
        sealed = read(ORIGINAL / "prediction-seal.json", SEALS["original19"])
        ordinary_receipt = read(ORIGINAL / "ordinary-recovered.json", sealed["products"]["ordinary"]["receipt_sha256"])
        ordinary = read(ORIGINAL / "native.json", ORIGINAL_0019)
        old = load_publication(ORIGINAL / "ordinary", ordinary_receipt["terminal"],
                               ordinary_receipt["witness_sha256"], "sha256:" + ORIGINAL_0019)
        new_native, new, plan, run = capsule(BLEND, SEALS["blend19"], case)
        ordinary_witness = ordinary_receipt["witness_sha256"]
    else:
        ordinary, old, _, ordinary_receipt = capsule(TRANSFER / "ordinary-capsule/output", SEALS["original274"], case)
        new_native, new, plan, run = capsule(TRANSFER / "half-blend-capsule/output", SEALS["blend274"], case)
        ordinary_witness = ordinary_receipt["witness"]
    if digest(ordinary) != plan["original_native_sha256"]:
        raise ValueError("The treatment refers to a different ordinary packet")
    delta, winners, unedited = signed_edits(ordinary, new_native, plan["change"]["edits"])
    if (digest(plan["change"]["edits"]) != plan["change"]["recipe"]["edit_sha256"]
            or len(delta) != {"DS30-0019": 366, "DS30-0274": 499}[case]
            or old[0]["source_sha256"] != new[0]["source_sha256"]):
        raise ValueError("The frozen edit ledger or the scientific publication source changed")
    arms = {}
    for arm in ARMS:
        rosters = [owner_rows(witness, arm, winners) for witness, _ in (old, new)]
        used = rosters[0].keys() & delta.keys()
        all_rms = [witness["evidence"]["detail"]["arms"][arm]["residual_rms_hz"] for witness, _ in (old, new)]
        captured = [witness["ports"]["history_risk"]["lean_final_fit"]["arms"][arm] for witness, _ in (old, new)]
        fits = [item["fit"] for item in captured]
        terminal_arms = [terminal["arms"][arm] for _, terminal in (old, new)]
        arms[arm] = dict(
            owned_edits=len(used), edited_by_role=dict(Counter(rosters[0][oid][1] for oid in used)),
            exact_signed_residual_matches=0, unedited_ordinary_owned=len(rosters[0])-len(used),
            unchanged_control_shift_hz=0.,
            membership=overlap(*rosters, set(delta)),
            fixed=fixed_bound(len(rosters[0]), all_rms[0], (delta[oid] for oid in sorted(used))),
            rebuilt_all_owned_RMS_hz=all_rms,
            rebuilt_conditional_RMS_hz=[row["rf_rms_hz"] for row in terminal_arms],
            rebuilt_role_aggregates=[predictive_rms(*values) for values in
                                     zip(rosters, captured, all_rms, terminal_arms, strict=True)],
            rebuilt_fit_changed_position=fits[0]["position"] != fits[1]["position"],
            rebuilt_fit_changed_receiver_coefficients=fits[0]["rf_nuisance"] != fits[1]["rf_nuisance"],
            rebuilt_fit_c_hz_per_ghz=[fit["rf_nuisance"][8] for fit in fits] if arm == "fitted_c" else [0., 0.],
        )
    graph = [witness["ports"]["graph"]["graph"] for witness, _ in (old, new)]
    return dict(case=case, original_native=plan["original_native_sha256"], derived_native=run["input"],
                evidence_witnesses=[ordinary_witness, run["witness"]], edits=len(delta),
                unedited_opportunities_identical=unedited, original_winners=len(winners),
                rebuilt_graph_tracks=[g["tracks"] for g in graph], rebuilt_graph_assigned=[g["assigned"] for g in graph],
                arms=arms, status="signed_residual_vectors_absent")


if __name__ == "__main__":
    result = dict(cases={case: run_case(case) for case in ("DS30-0019", "DS30-0274")}, seals=SEALS,
                  protocol=sha256((HERE / "held-cfo-fixed-residual-protocol.md").read_bytes()).hexdigest())
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
