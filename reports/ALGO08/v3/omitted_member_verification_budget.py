"""Price exact verify-only members on the sealed DS30-0086 saved comparison."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


CASE = "DS30-0086"
PINS = dict(score="5e0f037d9d64cdcf2b89439422a91f2b3519b9edf4e712d67f31da10837c6829",
            audit="f71799db7d0cef7194f9e9d11f13002e1cfe1c7af93a9f0badff6b12398c76f5",
            mask="e0eacff4b10617b5c99791dcddcc38cef4ff6273ae83d7d373af058198a2f573",
            intake="2df05acf26b3ae28d97c662125c74fb2fadbd7cb269cb100600c42eefcee3c5f",
            runtime="d21da2bd2e7b37428a696f24079a1753297228d1e3bba1fe8ad20c3df07c6c27",
            donor="8ae7c207eedec32b14581c0915c2cfcf6e856e7067b0b4f2f31a2aa9245902b5")


def read(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed receipt changed: {path.name}")
    return json.loads(body)


def clocks(rows):
    values = {phase: {name: sum(row[phase][name + "_ns"] for row in rows) / 1e9 for name in ("wall", "cpu")}
              for phase in ("metadata", "complete_encoded_auth", "plan_and_history")}
    for stage, prefix in (("native_decode", "native_read"), ("decoded_hashes", "hash")):
        values[stage] = {name: sum(row[f"{prefix}_{name}_ns"] for row in rows) / 1e9 for name in ("wall", "cpu")}
    return values


def donors(fixture, members):
    result = []
    for pair in fixture["runs"]:
        arms = {row["arm"]: row["overlap"] for row in pair}
        raw, drained = arms["released"], arms["native"]
        rows = drained["members"]
        if (drained["fallbacks"] or drained["materialized_rows"] or drained["retained_metadata_rows"] != 128
                or raw["materialized_rows"] != 128 or len(rows) != 2
                or any(row["decoded_bytes"] != 102_400_000 or row["checksum"] != 1 or row["windows"] != 64 for row in rows)):
            raise ValueError("A donor must fully verify two omitted ordinary signed members")
        scale = members / len(rows)
        result.append(dict(order=[row["arm"] for row in pair], scale=scale,
                           fixture_released_tail_cpu_s=raw["cpu_ns"] / 1e9,
                           fixture_native_tail_cpu_s=drained["cpu_ns"] / 1e9,
                           fixture_native_tail_wall_s=drained["wall_ns"] / 1e9,
                           transferred_cpu_s=drained["cpu_ns"] / 1e9 * scale,
                           transferred_wall_s=drained["wall_ns"] / 1e9 * scale,
                           transferred_decode_hash_only_cpu_s=sum(r["decode_cpu_ns"] + r["hash_cpu_ns"] for r in rows) / 1e9 * scale,
                           transferred_paired_cpu_saving_s=(raw["cpu_ns"] - drained["cpu_ns"]) / 1e9 * scale))
    return result


def projection(full, target, omitted_wall, prefetch_worker_cpu, donor):
    # Adding worker CPU gives the replacement every possible advantage in
    # this accounting: those worker seconds may overlap the main envelope.
    generous_credit = omitted_wall + prefetch_worker_cpu
    return dict(required_extra_saving_s=full - target, omitted_wall_credit_s=omitted_wall,
                extra_byte_scaled_prefetch_cpu_s=prefetch_worker_cpu, generous_old_stage_credit_s=generous_credit,
                replacement_budget_s=target - full + generous_credit,
                if_all_recorded_omitted_main_work_free_s=full-omitted_wall,
                modeled_wall_with_donor_decode_hash_alone_s=full-generous_credit+donor["transferred_decode_hash_only_cpu_s"],
                modeled_wall_with_donor_full_verification_cpu_s=full-generous_credit+donor["transferred_cpu_s"],
                modeled_wall_with_donor_full_verification_wall_s=full-generous_credit+donor["transferred_wall_s"])


def study(campaign, audit_root, score_path, fixture_path):
    score = read(score_path, PINS["score"])
    audit = read(audit_root / "audit.json", PINS["audit"])
    (record,) = [row for row in audit["records"] if row["case"] == CASE]
    mask = read(audit_root / f"{CASE}-members.json", PINS["mask"])
    case = campaign / "cases" / CASE
    installed, successor = (read(case / arm / "attempt-000001/result.json", pin)
                           for arm, pin in zip(("installed", "successor"), record["result_pins"], strict=True))
    folder = case / "successor/attempt-000001/publication"
    intake = read(folder / "legacy-original-acquisition.json", PINS["intake"])
    runtime = read(folder / "unified-short-bootstrap.json", PINS["runtime"])
    if (installed["raw_identity"] != successor["raw_identity"] or runtime["native_sha256"] != successor["native_sha256"]
            or intake["finished_raw_authority"] != successor["raw_identity"]["raw_authority_sha256"]
            or score["source_sha256"] != "sha256:" + PINS["audit"]
            or score["case"] != CASE or not record["matched_original_counterfactual"]):
        raise ValueError("The saved comparison and old field telemetry must identify one original recording")
    entries = intake["members"]
    measured_keys = ("manifest_sha256", "chunk_index", "first_sequence", "windows", "encoded", "decoded",
                     "member_sha256", "index_sha256", "raw_sha256")
    planned_keys = ("manifest_sha256", "chunk_index", "first_sequence", "window_count", "compressed_bytes",
                    "uncompressed_bytes", "compressed_sha256", "index_sha256", "uncompressed_sha256")
    for item, measured in zip(mask, entries, strict=True):
        if tuple(item[k] for k in planned_keys) != tuple(measured[k] for k in measured_keys):
            raise ValueError("A modeled member differs from the authentic verified traversal")
    omitted = [measured for item, measured in zip(mask, entries, strict=True) if item["omit"]]
    if not omitted or any(not row["chunk_index"] or row["windows"] != 64 for row in omitted):
        raise ValueError("The byte-priced replacement expects only complete, originally prefetched omitted members")
    totals = {key: sum(row[key] for row in omitted) for key in ("encoded", "decoded", "windows")}
    p = record["physical"]
    if (totals["encoded"], totals["decoded"], totals["windows"], len(omitted)) != (
            p["encoded_omitted"], p["decoded_omitted"], p["omitted_visits"], p["members_omitted"]):
        raise ValueError("Omitted member totals differ from the sealed science projection")
    prefetch = runtime["prefetch"]
    if (prefetch["fallback"] or prefetch["submitted"] != prefetch["hits"]
            or sum(row["encoded"] for row in entries if row["chunk_index"]) != prefetch["hit_bytes"]):
        raise ValueError("Recorded lookahead does not account for every speculative member")
    own = clocks(omitted)
    worker_share = prefetch["worker_cpu_ns"] / 1e9 * totals["encoded"] / prefetch["hit_bytes"]
    donor = donors(read(fixture_path, PINS["donor"]), len(omitted))
    full = score["modeled_0086_raw_wall_s"]["all_payload_authentication"]
    target = installed["elapsed_s"] / 2
    projections = [projection(full, target, sum(s["wall"] for s in own.values()), worker_share, source) for source in donor]
    return dict(case=CASE, source_pins=PINS, published_score_projection=full,
                explicit_unverified_omission_projection_s=score["modeled_0086_raw_wall_s"]["explicit_member_omission"],
                model_half_target_s=target, original_pair_result_pins=record["result_pins"], historical_native_work=runtime["receiver_audit"]["native"],
                omitted=dict(count=len(omitted), **totals, measured_main_stage_envelopes=own, old_prefetch=prefetch),
                retained_count=len(entries)-len(omitted), native_drain_donors=donor, counterfactuals=projections,
                historical_saved_solve=score["original_saved_solve"], masked_saved_solve=score["matched_solve"],
                fresh_waveform_bytes=0, fresh_raw_children=0)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("campaign", "audit", "score", "fixture"):
        p.add_argument(field, type=Path)
    a = p.parse_args()
    print(json.dumps(study(a.campaign, a.audit, a.score, a.fixture), sort_keys=True, allow_nan=False))
