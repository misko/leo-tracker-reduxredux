"""Apply the frozen installed carrier metric to the authenticated DS30-0212 pair."""

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import masked_cfo_0218_installed_agreement as metric


CASE = "DS30-0212"
PAIR = metric.PAIR.parent / CASE
CELLS = Path("/dev/shm/leo-v3-mask-cfo-next-two01") / CASE
FIXED = "67762a27e92251bf01d9fe7a4e6e0c616f55e3cef7bc7970f02de85dd5c926db"
BASE_METRIC = "86b720ec97a74a21c4dc2d92621aa9531657bdbaa779fab2bb88c86c8f626c24"
CASE_EDITED = 153
residual = metric.residual


def lost_groups(before, after, edits):
    lost = {oid: before[oid] for oid in sorted(before.keys() - after.keys())}
    groups = Counter()
    ledger = []
    for oid, row in lost.items():
        edit = edits.get(oid)
        changed = edit is not None and edit["original_hz"] != edit["updated_hz"]
        groups[changed, row["norad"], row["role"]] += 1
        ledger.append([oid, changed, row["norad"], row["role"]])
    return dict(total=len(lost), changed=sum(entry[1] for entry in ledger),
                owner_rows_sha256=residual.digest(ledger), groups=[
                    dict(cfo_changed=changed, ordinary_norad=norad, ordinary_role=role, n=n)
                    for (changed, norad, role), n in sorted(groups.items())])


def main():
    if os.sched_getaffinity(0) != {3}:
        raise ValueError("Require CPU 3 for the saved numerical audit")
    threads = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    if any(os.environ.get(key) != "1" for key in threads):
        raise ValueError("Require one numerical thread for the masked Graph")

    def metadata_only(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if (path.suffix in (".tle", ".iq", ".sigmf-data") or "fast-scan-recordings" in path.parts
                    or path.is_relative_to("/mnt/qnap01")
                    or path.name in ("evaluation-reference.json", "reference-audit.json", "score.json")
                    or path.is_relative_to(PAIR.parent) and not path.is_relative_to(PAIR)):
                raise RuntimeError("Only sealed numerical metadata for DS30-0212 is eligible")

    sys.addaudithook(metadata_only)
    sources = {**metric.PINS, "masked_cfo_0218_installed_agreement.py": BASE_METRIC}
    for name, pin in sources.items():
        residual.checked(metric.HERE / name, pin)
    for name, pin in residual.RELEASE_PINS.items():
        residual.checked(residual.RELEASE / "src" / name, pin)

    import signed_cfo_time_readout as signed
    from reports.ALGO08.v3 import held_short_cfo_shrink as held

    if held.odd.WINDOWS != ((250, 2), (2250, 6)) or held.odd.PERIOD != 40_000/3:
        raise ValueError("The frozen CFO and physical-arrival windows changed")
    fixed = residual.read(metric.HERE / "measurements/masked-cfo-0212-fixed-residuals.json", FIXED)
    pins = residual.read(CELLS / "verification-pins.json", fixed["closure_sha256"])
    if fixed["case"] != CASE or pins != fixed["plan_pins"]:
        raise ValueError("The selected residuals do not match both sealed saved cells")
    with patch.object(residual, "CASE", CASE):
        ordinary, corrected = (residual.read_cell(CELLS / mode, mode, pins[mode]) for mode in residual.MODES)
    mixed = ordinary["native"]
    if (corrected["native"] != mixed or any(cell["plan"]["original"] != fixed["original_field"]
             or cell["export"]["decision"] != "complete" for cell in (ordinary, corrected))):
        raise ValueError("Both complete cells must share the authenticated original winner packet")
    original = residual.original_winners(mixed)
    ordinary_digest = residual.digest(original)
    if ordinary["scope"].get("attempts") or ordinary["scope"].get("feature_calls", 0):
        raise ValueError("The ordinary cell must have a disabled correction overlay")
    replay = residual.rederive(mixed, original, corrected["scope"])
    if (replay is None or replay["changed"] != CASE_EDITED or len(replay["edits"]) != CASE_EDITED
            or replay["digest"] != fixed["edit_readback"]["digest"]):
        raise ValueError("The readout must include all 153 sealed nonzero edits")
    edits = replay["edits"]
    updated = residual.edited_winners(original, edits)
    if residual.compare(ordinary, corrected, original, replay) != fixed["arms"]:
        raise ValueError("The winner and owner readback differs from the sealed fixed-residual result")
    owners, after = (residual.numeric_rows(cell["export"], cell["witness"], {
        row["observation_id"]: row["measured_cfo_hz"] for row in winners})
        for cell, winners in zip((ordinary, corrected), (original, updated), strict=True))

    with patch.object(metric, "PAIR", PAIR):
        installed, installed_pin, attempts = metric.load_pair(fixed, mixed, signed)
    mixed_opportunities, full_opportunities = (signed.opportunities(packet) for packet in (mixed, installed))
    signed.bind_pair(installed, mixed, full_opportunities, mixed_opportunities)
    from leo.analysis.localization_v3.tracks import winning_observations

    extracted, _ = winning_observations(installed)
    by_opportunity = {oid: item["factor"][residual.HERTZ] for oid, item in full_opportunities.items()
                      if item["factor"] is not None}
    measured = {row["observation_id"]: row["measured_cfo_hz"] for row in extracted}
    if extracted != residual.original_winners(installed) or measured != by_opportunity:
        raise ValueError("The original installed winner extraction changed")
    records = metric.matched_rows(edits, mixed_opportunities, full_opportunities, held.aligned_errors)
    result = metric.view(records, owners, held.evaluate, held.odd.WINDOWS, signed.ALIAS)
    grouped = {arm: lost_groups(owners[arm], after[arm], edits) for arm in residual.ARMS}
    for arm in residual.ARMS:
        sealed = fixed["arms"][arm]
        lost = sealed["actual_rebuilt"]["ordinary_only"]
        if (grouped[arm]["total"] != lost["n"] or grouped[arm]["changed"] != lost["changed_edits"]
                or result["by_ordinary_arm"][arm]["owned"]["eligible"] != sealed["fixed_state"]["changed"]["ordinary"]["n"]):
            raise ValueError("The owner population differs from the sealed receipts")
    protocol = metric.HERE / "masked-cfo-0212-installed-agreement-protocol.md"
    return dict(case=CASE, installed_native_sha256=installed_pin, mixed_native_sha256=fixed["original_native_sha256"],
                paired_field_attempts=attempts, pair_sha256=fixed["original_field"]["verified_field_pair_sha256"],
                closure_sha256=fixed["closure_sha256"], fixed_receipt_sha256=FIXED, plan_pins=pins,
                edit_sha256=replay["digest"], edit_readback_cost=replay["readback"],
                original_winners_sha256=ordinary_digest, corrected_winners_sha256=residual.digest(updated),
                coverage_records_sha256=residual.digest(records), result=result, ordinary_only_owners=grouped,
                source_pins=sources, protocol_sha256=sha256(protocol.read_bytes()).hexdigest(),
                waveform_reads=0, orbit_reads=0, survey_reads=0, receiver_runs=0, solver_runs=0)


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True, indent=2, allow_nan=False))
