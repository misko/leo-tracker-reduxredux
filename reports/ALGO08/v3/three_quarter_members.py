"""Project authentic per-lane strongest factors onto fixed original member quartets."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
MANIFEST = "a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8"
HELD = "sha256:ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"
SPARSE = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
FACTORIAL = "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58"
WEAK = "ace7652af6fa0945f28dd161d1b16ecb293f0ca7c8bdf8340dfeff610c87fd9c"
ARMS = ("c0", "fitted_c")

sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / "src")]
from leo.contracts.digests import canonical_digest as digest, canonical_json_bytes as encoded  # noqa: E402
from alternate_original_members import report_adapter  # noqa: E402
from compressed_size_triage import packet  # noqa: E402
from continued_cfo_trial import rebinding  # noqa: E402
from installed_receiver_field_budget import CASES, field_pair, gates  # noqa: E402


def checked(path, pin=None):
    data = path.read_bytes()
    if pin is not None and sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed source changed at {path.name}")
    return data


def read(path, pin=None):
    return json.loads(checked(path, pin))


def write(path, document):
    with path.open("xb") as stream:
        stream.write(encoded(document))


def accession():
    path = ROOT / "reports/2026_11_20_ds30_fast/dataset/manifest.json.gz"
    data = gzip.decompress(checked(path))
    if sha256(data).hexdigest() != MANIFEST:
        raise ValueError("Signed accession manifest changed")
    return {row["dataset_label"]: row for row in json.loads(data)["members"]}


def membership(original):
    """Walk signed global offsets while restarting the quartet at each segment and short member."""
    raw = original["raw_recording"]
    ordered = list(raw["segments"])
    groups = [(key, list(rows)) for key, rows in groupby(raw["chunks"], key=lambda row: row["segment_manifest"])]
    if [key for key, _ in groups] != [segment["path"] for segment in ordered]:
        raise ValueError("The member roster differs from signed segment order")
    global_start, result = 0, []
    for segment, (_, chunks) in zip(ordered, groups, strict=True):
        local, phase = 0, 0
        for index, chunk in enumerate(chunks):
            count = chunk["window_count"]
            if (chunk["chunk_index"] != index or chunk["first_sequence"] != local or not 0 < count <= 64
                    or chunk["observed_index_sha256"] != chunk["index_sha256"]
                    or chunk["observed_payload_bytes"] != chunk["compressed_bytes"]):
                raise ValueError("Non-consecutive signed member or invalid capture witness")
            omit = count == 64 and phase == 3
            result.append(dict(chunk, ordinal=len(result), manifest_sha256=segment["sha256"],
                               first_visit=global_start, stop_visit=global_start+count, omit=omit))
            local += count
            global_start += count
            phase = (phase + 1) % 4 if count == 64 else 0
    if global_start != original["window_count"]:
        raise ValueError("Signed member extents must account for every issued visit")
    return result


def preheld(native, claim, *, expected_native=None):
    """Undo only an explicitly attested no-op selector identity and verify the measured parent bytes."""
    recipe = dict(claim["receiver_recipe"])
    held = recipe.pop("held_native_8ms")
    sparse_rule = ["full"] + ["short_primary"] * 7
    probes = native["source"]["probes"]
    if (claim["choice"]["route"] != "unfiltered" or claim["refinement_calls"] != 0
            or sum(len(row["candidates"]) for row in probes) != claim["observed"]
            or claim["observed"] != claim["selected"] or recipe["aperture_samples"] != [200_000, 80_000]
            or recipe["shortened_sha256"] != SPARSE or recipe["rule"] != sparse_rule
            or held["measurement"] != "original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement"
            or claim["detector_recipe_sha256"] != HELD or digest(claim["receiver_recipe"]) != HELD
            or claim["native_sha256"] != digest(native) or digest(recipe) != claim["parent_detector_sha256"]
            or expected_native is not None and claim["native_sha256"] != expected_native):
        raise ValueError("No authenticated independent strongest-margin tape for this original outcome")
    original = rebinding(native, probes, recipe)
    if digest(original) != claim["parent_native_sha256"] or rebinding(original, probes, claim["receiver_recipe"]) != native:
        raise ValueError("Recorded native handoff cannot be reproduced from the frozen no-op selector")
    return original, recipe


def anchors(native):
    probes = native["source"]["probes"]
    by_stream, by_visit = Counter(), {}
    last = -1
    for a, b in zip(probes[::2], probes[1::2], strict=True):
        visit = a["visit_index"]
        if (visit <= last or a["receiver_id"] != 0
                or dict(a, candidates=[], receiver_id=1) != dict(b, candidates=[])):
            raise ValueError("Original issued lanes must be ordered stereo")
        last = visit
        stream = a["edge"], a["channel"], a["actual_rf_hz"]
        slot = by_stream[stream]
        by_stream[stream] += 1
        full = slot % 8 == 0
        for p in (a, b):
            factors = p["candidates"]
            if len(factors) > 1 or any(not item["passed_fractional_margin_gate"] or
                                     not full and item["candidate_rank"] != 0 for item in factors):
                raise ValueError("A selected measurement is not an original strongest lane")
        by_visit[visit] = (stream, slot, full)
    provenance = native["provenance"]
    invalid = {row["visit"] for row in provenance["excluded_windows"]}
    if (len(by_visit) != provenance["processed_windows"] or len(invalid) != provenance["invalid_capture"]
            or len(native["delivery_clocks"]) != provenance["window_count"] or set(by_visit) & invalid
            or set(by_visit) | invalid != set(range(provenance["window_count"]))):
        raise ValueError("Original admission must account for all signed visits")
    return by_visit, by_stream


def project(original, receiver, members, original_anchor, *, scope):
    omitted = {v for row in members if row["omit"] for v in range(row["first_visit"], row["stop_visit"])}
    provenance, source = original["provenance"], original["source"]
    discarded = sorted(omitted)
    retained = [row for row in source["probes"] if row["visit_index"] not in omitted]
    invalid = [row for row in provenance["excluded_windows"] if row["visit"] not in omitted]
    if len(retained) // 2 + len(invalid) + len(omitted) != provenance["window_count"]:
        raise ValueError("Retained, capture-invalid and omitted visits must exhaust the original recording")
    selected_recipe = dict(receiver, three_quarter_original_members=dict(
        eighth_admitted_stereo_anchor="uses original admitted stream counters including omitted indices",
        member_rule="fourth consecutive 64-visit original member, within each disjoint segment quartet",
        selector="independent strongest verified fractional margin, lower-rank tie break",
        schedule_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    sampled = rebinding(original, retained, selected_recipe)
    retained_apertures = [(v, x[2]) for v, x in original_anchor.items() if v not in omitted]
    sampled["provenance"].update(processed_windows=len(retained) // 2, invalid_capture=len(invalid),
        excluded_windows=invalid,
        research_sampling=dict(kind="saved-original-strongest-member-mask", original_packet_sha256=digest(original),
          original_inventory_sha256=source["input_manifest_sha256"], members_sha256=digest(members),
          skipped_acquisition_windows=discarded, receiver_slots=[0, 1], retained_apertures_sha256=digest(retained_apertures),
          archived_factor_scope=scope))
    if sampled["delivery_clocks"] != original["delivery_clocks"] or sampled["clock_anchor"] != original["clock_anchor"]:
        raise ValueError("The original clock cannot be compacted")
    return sampled, selected_recipe, omitted


def member_auth(members, intake):
    wanted = ("manifest_sha256", "chunk_index", "first_sequence", "window_count", "compressed_bytes", "uncompressed_bytes",
              "compressed_sha256", "uncompressed_sha256", "index_sha256")
    witnessed = ("manifest_sha256", "chunk_index", "first_sequence", "windows", "encoded", "decoded",
                 "member_sha256", "raw_sha256", "index_sha256")
    for expected, actual in zip(members, intake, strict=True):
        if not actual["complete_encoded_auth"] or tuple(expected[k] for k in wanted) != tuple(actual[k] for k in witnessed):
            raise ValueError("Published acquisition does not authenticate the signed indexed member roster")


def owner_losses(native, witness, public, omitted):
    session = native["source"]["session_id"]
    visits = {"sha256:"+sha256(f"{session}:{p['receiver_id']}:{p['valid_start_counter']}".encode()).hexdigest(): p["visit_index"]
              for p in native["source"]["probes"] if p["candidates"]}
    losses = {}
    for arm in ARMS:
        rows = witness["evidence"]["owner_rows"][arm]
        owners = {r[0]: r[1] for r in rows}
        if len(owners) != len(rows) or digest(owners) != public["evidence"]["owners"][arm] or not owners.keys() <= visits.keys():
            raise ValueError("Historical owners are not from the sealed terminal and same chosen lane roster")
        losses[arm] = dict(total=len(owners), omitted=sum(visits[o] in omitted for o in owners))
    return losses


def cost_model(record, physical, budget, intake):
    """Favorable elapsed projections at separate measured boundaries, without charging the same stage twice."""
    native_count = {"full": budget["measured_native_anchors"],
                    "short_primary": budget["full_eligible_lanes"]-budget["measured_native_anchors"]}
    counted_fraction = {role: physical["dropped_lanes"][role] / count if count else 0
                        for role, count in native_count.items()}
    measured = budget["measured_mixed_native_process_cpu_s"]
    native_credit = sum(measured.get(role, 0) * fraction for role, fraction in counted_fraction.items())
    byte_fraction = physical["encoded_omitted"] / physical["encoded_total"]
    payload_cpu = sum(row["native_read_cpu_ns"]+row["hash_cpu_ns"] for row in intake) / 1e9
    payload_credit_cpu = sum(row["native_read_cpu_ns"]+row["hash_cpu_ns"]
                             for row, take in zip(intake, physical["member_omit"], strict=True) if take) / 1e9
    also_prefetch_cpu = budget["measured_prefetch_thread_cpu_s"] * byte_fraction
    measured_split_credit = native_credit + min(
        payload_credit_cpu + also_prefetch_cpu, max(budget["measured_mixed_acquisition"]["cpu_s"]-sum(measured.values()), 0))
    remit = budget["measured_mixed_acquisition"]["elapsed_s"]
    observed = record["successor_s"]
    solve = (budget["measured_mixed_solve"] or {}).get("elapsed_s", 0)
    factor_fraction = physical["factors_omitted"] / max(physical["factors_total"], 1)
    average_acquire_credit = remit * max(byte_fraction, *counted_fraction.values())
    return dict(measured_payload_cpu_s=payload_cpu, measured_omitted_payload_cpu_s=payload_credit_cpu,
                mean_native_credit_cpu_s=native_credit, byte_scaled_prefetch_credit_cpu_s=also_prefetch_cpu,
                mean_share_acquisition_credit_wall_s=average_acquire_credit,
                arithmetic_disjoint_credit_cpu_s=measured_split_credit,
                stage_scaled_no_solver_credit_s=observed-average_acquire_credit,
                stage_scaled_factor_linear_s=observed-average_acquire_credit-solve*factor_fraction,
                stage_scaled_free_solver_s=observed-average_acquire_credit-solve,
                needed_solve_credit_s=max(0, observed-average_acquire_credit-record["installed_s"]/2),
                measured_solve_wall_s=solve)


def case_data(root, original, left, right):
    case = right["case"]
    budget = field_pair(root, left, right)
    native, output, result = packet(root, right)
    release = read(output / "unified-short-bootstrap.json", budget["successor_runtime_sha256"])
    if (right["raw_identity_sha256"] != original["raw_recording"]["identity_sha256"]
            or result["raw_identity"]["window_count"] != original["window_count"]):
        raise ValueError("The field control has a different physical accession")
    intake = read(output / "legacy-original-acquisition.json", budget["successor_intake_sha256"])["members"]
    members = membership(original)
    member_auth(members, intake)
    eligible = release["held_anchor_route"]["choice"]["route"] == "unfiltered"
    if not eligible:
        return dict(case=case, installed_s=left["elapsed_s"], successor_s=right["elapsed_s"],
                    matched_original_counterfactual=False, reason="history-filtered saved original"), None
    parent, recipe = preheld(native, release["held_anchor_route"], expected_native=result["native_sha256"])
    visit_anchor, streams = anchors(parent)
    duty = release["receiver_audit"]["native"]
    proved_streams = {(r["edge"], r["channel"], r["rf_hz"]): r["admitted"] for r in duty["streams"]}
    if (dict(streams) != proved_streams or 2*sum(x[2] for x in visit_anchor.values()) != duty["native_calls"]["full"]):
        raise ValueError("The saved independently rebuilt anchor counters differ from the actual receiver")
    reduced, shape, omit = project(parent, recipe, members, visit_anchor, scope=case)
    raw_probes = parent["source"]["probes"]
    dropped = {role: 2*sum(v in omit and (x[2] == (role == "full")) for v,x in visit_anchor.items())
               for role in ("full", "short_primary")}
    original_invalid = parent["provenance"]["invalid_capture"]
    selected = Counter(p["channel"] for p in raw_probes if p["candidates"] and p["visit_index"] in omit)
    omitted = [m for m in members if m["omit"]]
    physical = dict(members=len(members), members_omitted=len(omitted), member_omit=[m["omit"] for m in members],
                    windows=original["window_count"], omitted_visits=len(omit), original_admitted=len(visit_anchor),
                    retained_admitted=reduced["provenance"]["processed_windows"],
                    omitted_original_invalid=original_invalid-reduced["provenance"]["invalid_capture"],
                    encoded_total=sum(m["compressed_bytes"] for m in members), encoded_omitted=sum(m["compressed_bytes"] for m in omitted),
                    decoded_omitted=sum(m["uncompressed_bytes"] for m in omitted),
                    all_index_bytes=sum(m["index_bytes"] for m in members), dropped_lanes=dropped,
                    factors_total=sum(len(r["candidates"]) for r in raw_probes), factors_omitted=sum(selected.values()),
                    factors_omitted_by_channel=selected)
    record = dict(case=case, installed_s=left["elapsed_s"], successor_s=right["elapsed_s"],
                  outcomes=[left["outcome"], right["outcome"]], matched_original_counterfactual=True, physical=physical,
                  parent_native_sha256=digest(parent), historical_final_native_sha256=digest(native),
                  proposed_native_sha256=digest(reduced), receiver_recipe_sha256=digest(shape),
                  members_sha256=digest(members), result_pins=[left["attempt_result_sha256"], right["attempt_result_sha256"]])
    if right["outcome"] == "complete":
        witness = read(output / "exact-named-raw-witness.json", budget["successor_solve_sha256"])
        record["owner_support"] = owner_losses(native, witness, result, omit)
    record["model"] = cost_model(record, physical, budget, intake)
    return record, (members, parent, reduced, shape)


def audit(root, output):
    original = accession()
    by_case = {(row["case"], row["algorithm"]): row for row in
               map(json.loads, (root / "rows.jsonl").read_bytes().splitlines()) if row["verified_pair"]}
    records = []
    output.mkdir(mode=0o700)
    for case in CASES:
        left, right = (by_case[case, arm] for arm in ("installed", "successor"))
        result, papers = case_data(root, original[case], left, right)
        records.append(result)
        if case in ("DS30-0086", "DS30-0019") and papers:
            members, _, reduced, recipe = papers
            write(output / (case + "-members.json"), members)
            write(output / (case + "-native.json"), reduced)
            write(output / (case + "-recipe.json"), recipe)
    model = {key: gates(records, [row.get("model", {}).get(key, row["successor_s"]) for row in records])
             for key in ("stage_scaled_no_solver_credit_s", "stage_scaled_factor_linear_s", "stage_scaled_free_solver_s")}
    write(output / "audit.json", dict(fixed_cases=CASES, records=records, gates=model,
          actual=gates(records, [row["successor_s"] for row in records]),
          protocol_sha256=sha256((HERE/"three-quarter-members-protocol.md").read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--field", type=Path, default=FIELD)
    options = cli.parse_args()
    audit(options.field, options.output)
