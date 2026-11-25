"""Score all sealed 0218 edits against the independent installed full receiver."""

from hashlib import sha256
import json
from math import isfinite, remainder
import os
from pathlib import Path
import sys

import masked_cfo_0218_fixed_residuals as residual


HERE = Path(__file__).resolve().parent
CASE = "DS30-0218"
PAIR = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases") / CASE
CELLS = Path("/dev/shm/leo-v3-0218-prospective01")
SEALED = "1a05fcaa2e2b723ea5c48989acfd49ca90b6f71261d639ab79d7e0aef01be4ec"
CASE_EDITED = 530
FULL = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
PINS = {
    "masked_cfo_0218_fixed_residuals.py": "a9d100ea129cb2aa9b1e065d79a45709d1bd61150c9bf41364cb99cba846846a",
    "held_short_cfo_shrink.py": "2ac33ded7301abb66c49661a4eb9e24c7fdc9582731d0bc66df383c1a9e1d279",
    "signed_cfo_time_readout.py": "cfe5f77de8905c1f7e7b34469d456b841add8cc4ca4221aa5cdfc371985104b9",
    "signed_cfo_time.py": "fff797b026890ab9c843129507b9dc49dd949982fae03e7f41b8fcf121466b3b",
    "odd_short_interpolation.py": "451b931a2c9bbdbd7a4513a22050eb3141d44356d686f2530eb4a051ddae60a3",
    "directed_donor.py": "6dc19f62bb928d34475fac99539e880e9797ed5aa21caffd076b59a4946c410c",
    "held_cfo_features.py": residual.FEATURE,
    "masked_cfo_saved.py": residual.OVERLAY,
}


def load_pair(sealed, mixed, signed):
    pair = residual.read(PAIR / "pair.json", sealed["original_field"]["verified_field_pair_sha256"])
    tokens = pair["attempt_result_sha256"]
    if (not pair["verified_pair"] or not pair["chronological"] or pair["state"] != "observed_pair"
            or pair["actual_order"] != ["installed", "successor"]
            or tokens["successor"] != sealed["original_field"]["raw_attempt_sha256"]):
        raise ValueError("Only the original authenticated independently acquired pair is eligible")
    roots = {name: PAIR / name / f"attempt-{pair['generation']:06d}" for name in pair["actual_order"]}
    runs = {name: residual.read(root / "result.json", tokens[name]) for name, root in roots.items()}
    for name, run in runs.items():
        if (run["process"]["exit_code"] or run["outcome"] != "complete" or run["algorithm"] != name
                or run["generation"] != pair["generation"]):
            raise ValueError("An original acquisition did not close successfully")
    full, sparse = (runs[name] for name in ("installed", "successor"))
    authority = residual.read(PAIR / "authority.json", pair["authority_sha256"])
    if (full["raw_identity"] != authority or sparse["raw_identity"] != authority
            or sparse["native_sha256"] != sealed["original_native_sha256"]):
        raise ValueError("The installed and mixed acquisitions have different capture authority")
    installed = signed.read_native(roots["installed"] / "publication", full["native_sha256"])
    original = signed.read_native(roots["successor"] / "publication", sparse["native_sha256"])
    if (installed["provenance"]["detector_sha256"] != FULL or original != mixed
            or any(installed["source"][key] != mixed["source"][key] for key in ("capture_end_utc_ns", "probe_ms"))
            or mixed["source"]["raw_recording_authority_digest"] != authority["raw_authority_sha256"]):
        raise ValueError("Installed full receiver, mixed packet or signed time units differ")
    return installed, full["native_sha256"], tokens


def matched_rows(edits, mixed, full, alignment):
    rows = {}
    if not edits.keys() <= mixed.keys() or not edits.keys() <= full.keys():
        raise ValueError("An edited observation has no matching authenticated installed opportunity")
    for oid, edit in edits.items():
        a, b = mixed[oid], full[oid]
        if not a["short"] or not a["factor"] or a["counter"] != b["counter"]:
            raise ValueError("Every edit must address the same signed short opportunity")
        values = alignment(a, b, edit)
        if values is not None and not all(isfinite(x) for x in values):
            raise ValueError("The full receiver has a nonfinite signed CFO or physical arrival")
        rows[oid] = values
    return rows


def summarize(rows, evaluate, windows, alias):
    scored = [r for r in rows if r is not None]
    result = evaluate(scored, len(rows)-len(scored))
    result["matched_coverage"] = len(scored)/len(rows) if rows else None
    for hz, time in windows:
        entry = result["windows"][f"{hz}Hz_{time}samples"]
        entry["cfo_before"] = len(scored)-entry["original_cfo_miss"]
        entry["cfo_after"] = entry["cfo_before"]+entry["cfo_restored"]-entry["cfo_spoiled"]
        entry["arrival_pass"] = sum(clock <= time for _, _, clock in scored)
        entry["alias_only_before"] = sum(abs(x) > hz and abs(remainder(x, alias)) <= hz and clock <= time
                                         for x, _, clock in scored)
        entry["alias_only_after"] = sum(abs(y) > hz and abs(remainder(y, alias)) <= hz and clock <= time
                                        for _, y, clock in scored)
    result["more_than_half_alias_spacing_before"] = sum(abs(x) > alias/2 for x, _, _ in scored)
    result["more_than_half_alias_spacing_after"] = sum(abs(y) > alias/2 for _, y, _ in scored)
    return result


def view(rows, owners, evaluate, windows, alias):
    def subset(keys):
        return summarize([rows[key] for key in sorted(keys)], evaluate, windows, alias)

    return dict(all_edits=subset(rows), by_ordinary_arm={arm: dict(
        owned=subset(rows.keys() & owned.keys()), nonowner=subset(rows.keys() - owned.keys()))
        for arm, owned in owners.items()})


def main():
    if os.sched_getaffinity(0) != {3}:
        raise ValueError("Require CPU 3 for the bounded saved metadata readback")
    threads = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    if any(os.environ.get(key) != "1" for key in threads):
        raise ValueError("Require one numerical thread for the pinned edit Graph")

    def no_raw(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix == ".tle" or "fast-scan-recordings" in path.parts
                    or path.name in ("evaluation-reference.json", "reference-audit.json")
                    or "cases" in path.parts and PAIR.parent in path.parents and not path.is_relative_to(PAIR)):
                raise RuntimeError("The sealed agreement reads no orbit, waveform, site or other case")

    sys.addaudithook(no_raw)
    for name, pin in PINS.items():
        residual.checked(HERE / name, pin)
    for name, pin in residual.RELEASE_PINS.items():
        residual.checked(residual.RELEASE / "src" / name, pin)

    import signed_cfo_time_readout as signed
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    if held.odd.WINDOWS != ((250, 2), (2250, 6)) or held.odd.PERIOD != 40_000/3:
        raise ValueError("The frozen signed CFO and hardware-arrival agreement windows changed")
    fixed = residual.read(HERE / "measurements/masked-cfo-0218-prospective-fixed-residuals.json", SEALED)
    pins = residual.read(CELLS / "verification-pins.json", fixed["closure_sha256"])
    if fixed["case"] != CASE or pins != fixed["plan_pins"]:
        raise ValueError("The prospective residual receipt differs from the closed capsule pair")
    ordinary, corrected = (residual.read_cell(CELLS / mode, mode, pins[mode]) for mode in residual.MODES)
    mixed = ordinary["native"]
    if corrected["native"] != mixed or any(cell["plan"]["original"] != fixed["original_field"]
                                           for cell in (ordinary, corrected)):
        raise ValueError("Original signed field input or prospective edited cell changed")
    original = residual.original_winners(mixed)
    edit_readback = residual.rederive(mixed, original, corrected["scope"])
    if (edit_readback is None or edit_readback["changed"] != CASE_EDITED
            or len(edit_readback["edits"]) != CASE_EDITED or edit_readback["digest"] != fixed["edit_readback"]["digest"]):
        raise ValueError("The comparison must contain all 530 originally applied CFO edits")
    edits = edit_readback["edits"]
    installed, installed_pin, attempts = load_pair(fixed, mixed, signed)
    a, b = (signed.opportunities(packet) for packet in (mixed, installed))
    signed.bind_pair(installed, mixed, b, a)

    from leo.analysis.localization_v3.tracks import winning_observations

    extracted, _ = winning_observations(installed)
    by_opportunity = {oid: item["factor"][residual.HERTZ] for oid, item in b.items() if item["factor"] is not None}
    measured = {row["observation_id"]: row["measured_cfo_hz"] for row in extracted}
    if extracted != residual.original_winners(installed) or measured != by_opportunity:
        raise ValueError("The frozen installed receiver winner extractor changed")
    before = {row["observation_id"]: row["measured_cfo_hz"] for row in original}
    owners = residual.numeric_rows(ordinary["export"], ordinary["witness"], before)
    records = matched_rows(edits, a, b, held.aligned_errors)
    result = view(records, owners, held.evaluate, held.odd.WINDOWS, signed.ALIAS)
    if any(result["by_ordinary_arm"][arm]["owned"]["eligible"]
           != fixed["arms"][arm]["fixed_state"]["changed"]["ordinary"]["n"] for arm in residual.ARMS):
        raise ValueError("The ordinary-owned edit set differs from the sealed fixed-state readback")
    return dict(case=CASE, installed_native_sha256=installed_pin, mixed_native_sha256=fixed["original_native_sha256"],
                paired_field_attempts=attempts, pair_sha256=fixed["original_field"]["verified_field_pair_sha256"],
                fixed_receipt_sha256=SEALED, edit_sha256=edit_readback["digest"],
                edit_readback_cost=edit_readback["readback"], source_pins=PINS,
                coverage_records_sha256=residual.digest(records), result=result, raw_reads=0, solver_runs=0,
                protocol_sha256=sha256((HERE/"masked-cfo-0218-installed-agreement-protocol.md").read_bytes()).hexdigest())


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True, indent=2, allow_nan=False))
