"""Verify closed DS30-0218 observations and compare their signed residuals."""

import argparse
from collections import Counter
from hashlib import sha256
from importlib import import_module
import json
from math import fsum, isclose, isfinite, sqrt
import os
from pathlib import Path
import re
import sys
from time import perf_counter, process_time


CASE = "DS30-0218"
ARMS = ("c0", "fitted_c")
ROLES = ("conditional", "predictive")
MODES = ("ordinary", "corrected")
HERTZ = "fractional_tracking_cfo_hz"
ADC = 10_000_000
PERIOD = 1 / 4.4e-6
BIN_HZ = ADC / (44 * 512)
HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
OBSERVER = "f6e912af1ed5e3fa4f82427569a195ca4b69110c839456cd0ca398363ea4b1c3"
FEATURE = "65a9934437d2d495b269f7377dd4d82ebe4d4e1e6f6b8e3e89717f89a25e8843"
OVERLAY = "2ecadcd736ea59184333280626e8c48de7afa2aed4ad95974bd1c5a564895c35"
CONFIG = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
PRESENTATION = "5dd6dbc63a4078e4b7fffcf10237d4f92429a1ea07d585eb3a49d0eca02cae2b"
RELEASE_PINS = {
    "leo/presentation/localization_v3.py": PRESENTATION,
    "leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "leo/analysis/localization_v3/history_position.py": "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0",
    "leo/analysis/localization_v3/event_position.py": "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f",
    "leo/analysis/localization_v3/marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    "leo/analysis/localization_v3/predictive_linear.py": "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
    "leo/analysis/glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
    "leo/analysis/graph_tracklets.py": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "leo/analysis/polynomial_tracklets.py": "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922",
    "leo/analysis/research/retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
}


def checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Unverified saved input {path}")
    return body


def read(path, pin):
    return json.loads(checked(path, pin))


def digest(doc):
    body = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + sha256(body.encode()).hexdigest()


def clock():
    return process_time(), perf_counter()


def elapsed(start):
    cpu, wall = clock()
    return dict(cpu_s=cpu-start[0], elapsed_s=wall-start[1])


def finite_hz(value):
    return type(value) in (int, float) and isfinite(value)


def original_winners(native):
    source = native["source"]
    if source["sample_rate_hz"] != ADC or source["probe_ms"] != 20.:
        raise ValueError("Expected the released signed ADC and 20 ms factor timestamp convention")
    receivers = sorted({row["receiver_id"] for row in source["probes"]})
    start = native["clock_anchor"]["sample_counter"]
    rows, all_ids = [], set()
    for row in source["probes"]:
        rx, counter = row["receiver_id"], row["valid_start_counter"]
        identity = f"{source['session_id']}:{rx}:{counter}"
        oid = "sha256:" + sha256(identity.encode()).hexdigest()
        if oid in all_ids or counter < start or row["channel"] not in range(1, 9):
            raise ValueError("Invalid or repeated native opportunity")
        all_ids.add(oid)
        winner = max((c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True),
                     key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None)
        if winner is None:
            continue
        if not all(finite_hz(x) for x in (winner[HERTZ], row["actual_rf_hz"], winner["fractional_margin"])):
            raise ValueError("Nonfinite native CFO, RF or margin")
        rows.append(dict(observation_id=oid, receiver=receivers.index(rx)+1, native_receiver_id=rx,
                         channel=int(row["channel"]), time_s=(counter-start)/ADC + 20.*.0005,
                         measured_cfo_hz=float(winner[HERTZ]), actual_rf_hz=float(row["actual_rf_hz"]),
                         fractional_margin=float(winner["fractional_margin"])))
    return sorted(rows, key=lambda row: (row["receiver"], row["channel"], row["time_s"], row["observation_id"]))


def edited_winners(original, edits):
    available = {row["observation_id"]: row["measured_cfo_hz"] for row in original}
    if not edits.keys() <= available.keys():
        raise ValueError("The edit ledger refers to a missing original winner")
    for oid, edit in edits.items():
        old, forecast, updated = (edit[key] for key in ("original_hz", "forecast_hz", "updated_hz"))
        if not all(finite_hz(v) for v in (old, forecast, updated)):
            raise ValueError("Nonfinite edit on the signed CFO axis")
        if old != available[oid] or abs(forecast-old) > BIN_HZ or updated != old+(forecast-old)/2:
            raise ValueError("Edit violates the frozen half-blend Hz or branch convention")
    return [dict(row, measured_cfo_hz=edits[row["observation_id"]]["updated_hz"])
            if row["observation_id"] in edits else row for row in original]


def numeric_rows(export, witness, expected):
    if export["decision"] == "withheld":
        if export["rows"] or witness["owner_rows"] or witness["detail"]["arms"] not in (None, {}):
            raise ValueError("Withheld publication carries unexpected selected residuals")
        return {}
    if set(export["rows"]) != set(ARMS) or set(witness["owner_rows"]) != set(ARMS):
        raise ValueError("Complete publication is missing an enrolled calibration arm")
    result = {}
    for arm in ARMS:
        rows = export["rows"][arm]
        identities = [[r["observation_id"], r["norad"], r["role"]] for r in rows]
        by_id = {r["observation_id"]: r for r in rows}
        summary = witness["detail"]["arms"][arm]
        if (not rows or identities != witness["owner_rows"][arm] or len(by_id) != len(rows)
                or summary["associated_points"] != len(rows) or digest({oid:n for oid,n,_ in identities})
                != summary["owner_sha256"] or not by_id.keys() <= expected.keys()):
            raise ValueError("A selected row is missing, repeated, or differs from its ordered owner")
        for oid, row in by_id.items():
            measured, r, predicted = (row[key] for key in ("measured_cfo_hz", "residual_hz", "prediction_hz"))
            if (not all(finite_hz(v) for v in (measured, r, predicted)) or row["role"] not in ROLES
                    or measured != expected[oid] or predicted != measured-r):
                raise ValueError("Selected residual violates its exact signed CFO representation, role or units")
        rms = sqrt(fsum(row["residual_hz"]**2 for row in rows)/len(rows))
        if not isclose(rms, summary["residual_rms_hz"], rel_tol=1e-13, abs_tol=1e-10):
            raise ValueError("Selected residuals fail the published all-owner RMS")
        result[arm] = by_id
    return result


def read_cell(root, mode, pins):
    plan = read(root / "plan.json", pins["plan"])
    timing = read(root / "clock.json", pins["clock"])
    scope = read(root / "masked-cfo-observation-witness.json", pins["observation"])
    run = read(root / "receipt.json", pins["receipt"])
    export_clock = read(root / "owner-residual-export-clock.json", pins["export_clock"])
    export = read(root / "owner-residuals.json", export_clock["residuals_sha256"])
    receipt = run["receipt"]
    native, decision = plan["original_native_sha256"], receipt["decision"]
    expected = dict(schema="leo.research.selected-owner-residuals.v1", role=mode, decision=decision,
                    plan_sha256=pins["plan"], native_sha256=native, terminal_sha256=receipt["terminal_sha256"],
                    ordinary_receipt_sha256=pins["receipt"], observation_witness_sha256=pins["observation"],
                    publication_witness_sha256=run["witness"], presentation_source_sha256=PRESENTATION,
                    observer_source_sha256=OBSERVER)
    if (timing["exit_code"] or plan["case"] != CASE or run["case"] != CASE or plan["probe"]
            or plan["enabled"] != (mode == "corrected") or plan["change"]["edits"]
            or plan["sources"].get("held_cfo_features.py") != FEATURE
            or plan["sources"].get("masked_cfo_saved.py") != OVERLAY
            or plan["change"]["derived_native_sha256"] != native or not run["graph_replayed"]
            or run["plan_sha256"] != pins["plan"] or run["input"] != native or run["handoffs"] != 1
            or run["waveform_reads"] or run["receiver_rerun"] or run["selector_rerun"]
            or any(scope[key] != value for key, value in dict(
                stage_plan_sha256=pins["plan"], enabled=mode == "corrected", decision=decision,
                native_sha256=native, original_native_sha256=native, waveform_reads=0, forecast_cache_reads=0,
                feature_source_sha256=FEATURE, approved_track_config_sha256=CONFIG).items())
            or any(export[key] != value for key, value in expected.items())):
        raise ValueError("Both cells require their exact pre-enrolled normal signed publication and observer")
    saved = root / "substituted"
    witness = read(saved / "exact-named-raw-witness.json", run["witness"])
    terminal = read(saved / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json", receipt["terminal_sha256"])
    detail = witness["evidence"]["detail"]
    if (terminal["native_sha256"] != native or detail["input_sha256"] != native
            or detail["terminal_sha256"] != receipt["terminal_sha256"] or terminal["region"] != receipt["region"]
            or detail["region"] != receipt["region"] or detail["state"] != decision
            or decision == "withheld" and (not terminal.get("reason") or detail["reason"] != terminal["reason"])
            or (decision, terminal["decision"]) not in (("complete", "ok"), ("withheld", "withheld"))):
        raise ValueError("The observer terminal and publication evidence disagree")
    actual = read(root / "derived-native.json", native)
    change = plan["change"]
    if (digest(actual) != native or change["recipe_sha256"] != actual["provenance"]["detector_sha256"]
            or change["recipe"]["sparse_native_sha256"] != native
            or change["recipe"]["edit_sha256"] != digest([])):
        raise ValueError("The verified original detector or no-edit native handoff changed")
    published, = (saved / "fast-scan-automatic-work").glob("*/detections.json")
    checked(published, native)
    return dict(plan=plan, scope=scope, run=run, export=export, terminal=terminal, witness=witness["evidence"],
                native=actual, residual_sha256=export_clock["residuals_sha256"])


def rederive(native, original, scope):
    attempts = scope.get("attempts", [])
    if not attempts:
        if scope["decision"] != "withheld" or scope.get("feature_calls", 0):
            raise ValueError("Only a true withholding before any CFO overlay may omit the edit map")
        return None
    if scope["feature_calls"] != 1:
        raise ValueError("Expected exactly one frozen feature derivation")
    started = clock()
    sys.path.insert(0, str(RELEASE / "src"))
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    for name in ("leo.analysis.localization_v3.tracks", "leo.analysis.glrt_frequency_input",
                 "leo.analysis.graph_tracklets", "leo.analysis.polynomial_tracklets"):
        module = import_module(name)
        if Path(module.__file__).resolve() != RELEASE / "src" / (name.replace(".", "/") + ".py"):
            raise ValueError("The edit readback must use the installed stock Graph and winner source")
    sys.path.insert(0, str(HERE))
    feature = import_module("held_cfo_features")
    if Path(feature.__file__).resolve() != HERE / "held_cfo_features.py":
        raise ValueError("The original frozen edit feature module is required")
    config = TrackConfig(**read(RELEASE / "assets/tracks.json", CONFIG)["config"])
    if config.alias_spacing_hz != PERIOD or feature.BIN_HZ != BIN_HZ or feature.ALIAS != PERIOD:
        raise ValueError("The released Graph alias spacing and edit units changed")
    rebuilt, _ = tracks.winning_observations(native)
    if rebuilt != original:
        raise ValueError("Saved observation ID or CFO representation differs from the installed extractor")
    result = feature.derive(native, config)
    edits = result.edits
    adjusted = edited_winners(original, edits)
    changed = sum(e["original_hz"] != e["updated_hz"] for e in edits.values())
    if (digest(edits) != scope["edit_sha256"] or len(edits) != scope["eligible"]
            or result.masked_graph != scope["masked_graph"] or result.gates != scope["eligible_gates"]
            or result.eligibility != scope["nomination_gates"]
            or adjusted != feature.apply_to_winners(native, original, result)):
        raise ValueError("Cannot reproduce the complete edit map recorded by the timed observation overlay")
    for attempt in attempts:
        expected = dict(original_rows_sha256=digest(original), consumed_rows_sha256=digest(adjusted),
                        edited_winners=changed, winners=len(original), detector_sha256=native["provenance"]["detector_sha256"])
        if any(attempt[key] != value for key, value in expected.items()):
            raise ValueError("A verified corrected Graph did not consume the exact signed CFO edits")
    return dict(edits=edits, digest=digest(edits), changed=changed, readback=elapsed(started))


def rms_sse(rows):
    square = fsum(r*r for r in rows)
    return dict(n=len(rows), rms_hz=sqrt(square/len(rows)) if rows else None, sse_hz2=square)


def fixed_state(before, edits):
    delta = {oid: edit["updated_hz"]-edit["original_hz"] for oid, edit in edits.items()}
    scope = set(before)
    eligible = scope & delta.keys()
    changed = {oid for oid in eligible if delta[oid] != 0}

    def stats(ids):
        pairs = [(before[oid]["residual_hz"], delta.get(oid, 0.)) for oid in sorted(ids)]
        initial = rms_sse([r for r, _ in pairs])
        final = rms_sse([r+d for r, d in pairs])
        return dict(ordinary=initial, fixed=final, delta_sse_hz2=fsum(2*r*d+d*d for r,d in pairs),
                    eligible=len(ids & eligible), changed=len(ids & changed))

    return dict(all=stats(scope), by_original_role={role: stats({oid for oid in scope if before[oid]["role"] == role})
                for role in ROLES}, changed=stats(changed), null_edit=stats(eligible-changed),
                unedited=stats(scope-eligible))


def rebuilt(before, after, edits):
    common = before.keys() & after.keys()
    added, dropped = after.keys() - before.keys(), before.keys() - after.keys()
    changed = {oid for oid, e in edits.items() if e["original_hz"] != e["updated_hz"]}
    norad_changed = {oid for oid in common if before[oid]["norad"] != after[oid]["norad"]}
    role_changed = {oid for oid in common if before[oid]["role"] != after[oid]["role"]}

    def stats(ids, rows):
        return rms_sse([rows[oid]["residual_hz"] for oid in sorted(ids)])

    def paired(ids):
        a, b = stats(ids, before), stats(ids, after)
        return dict(ordinary=a, corrected=b, changed_edits=len(ids & changed),
                    delta_sse_hz2=b["sse_hz2"]-a["sse_hz2"])

    return dict(common=paired(common), same_norad_and_role=paired(common-norad_changed-role_changed),
                common_unedited=paired(common-changed), common_changed_norad=paired(norad_changed),
                common_changed_role=paired(role_changed), role_transitions=dict(Counter(
                    f"{before[oid]['role']}->{after[oid]['role']}" for oid in common)),
                ordinary_only=dict(stats(dropped, before), changed_edits=len(dropped & changed)),
                corrected_only=dict(stats(added, after), changed_edits=len(added & changed)))


def compare(ordinary, corrected, original, edit_readback):
    edits = {} if edit_readback is None else edit_readback["edits"]
    if corrected["export"]["decision"] == "complete" and edit_readback is None:
        raise ValueError("Complete corrected publication is missing the verified applied edit ledger")
    maps = [{row["observation_id"]: row["measured_cfo_hz"] for row in rows}
            for rows in (original, edited_winners(original, edits))]
    before, after = (numeric_rows(cell["export"], cell["witness"], values) for cell, values in
                     zip((ordinary, corrected), maps, strict=True))
    fixed_reason = "ordinary_withheld" if not before else (
        "no_observed_corrected_overlay" if edit_readback is None else None)
    return {arm: dict(fixed_state=fixed_state(before[arm], edits) if fixed_reason is None else None,
                      fixed_unavailable=fixed_reason,
                      actual_rebuilt=rebuilt(before[arm], after[arm], edits) if before and after else None,
                      ordinary_selected=rms_sse([row["residual_hz"] for row in before[arm].values()]) if before else None,
                      corrected_selected=rms_sse([row["residual_hz"] for row in after[arm].values()]) if after else None)
            for arm in ARMS}


def run(root, authority, pin):
    if (2 in os.sched_getaffinity(0) or not root.is_relative_to("/dev/shm") or root.resolve() != root):
        raise ValueError("Use the original direct tmpfs cells and a CPU affinity excluding CPU 2")
    if not any(authority.resolve().is_relative_to(path) for path in ("/dev/shm", "/srv/postgres-nvme")):
        raise ValueError("Require the closed timing and receipt map on tmpfs or NVMe")

    def deny_inputs(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix == ".tle" or "fast-scan-recordings" in path.parts
                    or path.name in ("evaluation-reference.json", "reference-audit.json")):
                raise RuntimeError("The residual scorer never opens a TLE, raw recording or site reference")

    sys.addaudithook(deny_inputs)
    for path, digest_ in RELEASE_PINS.items():
        checked(RELEASE / "src" / path, digest_)
    for name, expected in (("masked_cfo_0218_owner_residuals.py", OBSERVER),
                           ("held_cfo_features.py", FEATURE), ("masked_cfo_saved.py", OVERLAY)):
        checked(HERE / name, expected)
    pins = read(authority, pin)
    if set(pins) != set(MODES) or any(set(pins[mode]) != {"plan", "clock", "observation", "receipt", "export_clock"}
                                    or not all(re.fullmatch(r"[0-9a-f]{64}", v) for v in pins[mode].values()) for mode in MODES):
        raise ValueError("Require the predeclared two-role closed digest set")
    ordinary, corrected = (read_cell(root / mode, mode, pins[mode]) for mode in MODES)
    a, b = ordinary["plan"], corrected["plan"]
    if (any(a[k] != b[k] for k in ("original", "original_archive", "original_native_sha256", "sources", "worker", "stage"))
            or ordinary["native"] != corrected["native"] or ordinary["terminal"]["region"] != corrected["terminal"]["region"]
            or not a["original"]["verified_field_pair_sha256"] or not a["original"]["raw_attempt_sha256"]
            or a["original"]["raw_outcome"] != ordinary["export"]["decision"]
            or ordinary["scope"].get("feature_calls", 0)):
        raise ValueError("The saved pair changed its authenticated original field input, offer or ordinary state")
    native = ordinary["native"]
    original = original_winners(native)
    edit_readback = rederive(native, original, corrected["scope"])
    return dict(case=CASE, source=sha256(Path(__file__).read_bytes()).hexdigest(), closure_sha256=pin,
                plan_pins=pins, original_native_sha256=a["original_native_sha256"], original_field=a["original"],
                ordinary=dict(decision=ordinary["export"]["decision"], reason=ordinary["terminal"].get("reason"),
                              residual_sha256=ordinary["residual_sha256"]),
                corrected=dict(decision=corrected["export"]["decision"], reason=corrected["terminal"].get("reason"),
                               residual_sha256=corrected["residual_sha256"]),
                arms=compare(ordinary, corrected, original, edit_readback), waveform_reads=0, survey_reads=0,
                edit_readback=None if edit_readback is None else dict(
                    eligible=len(edit_readback["edits"]), **{k:v for k,v in edit_readback.items() if k != "edits"}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("closure_pins", type=Path)
    cli.add_argument("--pin", required=True)
    args = cli.parse_args()
    print(json.dumps(run(args.root, args.closure_pins, args.pin), sort_keys=True, indent=2, allow_nan=False))
