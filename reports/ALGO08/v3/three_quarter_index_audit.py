"""Verify original stereo cadence using only already local signed index bodies."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from three_quarter_members import FACTORIAL, WEAK, FIELD, accession, anchors, checked, digest, membership, read, write  # noqa: E402


STAGES = {
    "DS30-0016": Path("/dev/shm/leo-v3-guarded-selective-0016-stage01"),
    "DS30-0049": Path("/tmp/leo-v3-ds30-0049-complete-idle01"),
}


def check_index_scope(original, parent, stage, stop):
    from alternate_original_raw import omitted_index
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.contracts.multirate_window_recording import ShortWindowIndexV2
    from leo.scanner.fast_scan_analysis import valid_window_support

    policy = FastScanPolicyV2()
    admitted, _ = anchors(parent)
    published = {row["visit_index"]: dict(row, candidates=[]) for row in parent["source"]["probes"]
                 if row["receiver_id"] == 0}
    invalid = {row["visit"]: row for row in parent["provenance"]["excluded_windows"]}
    hashes, verified, witnessed = [], [], {}
    truths, wrong_retained = Counter(), Counter()
    shift = Counter()
    manifests = {}
    for member in membership(original):
        if member["stop_visit"] > stop:
            break
        named = Path(member["segment_manifest"])
        folder = stage / named.parent.parent.name / named.parent.name
        header = folder / "manifest.json"
        if header.resolve(strict=True) != header or not stage.is_dir():
            raise ValueError("The original manifests must be independent local files")
        if header not in manifests:
            manifests[header] = read(header, member["manifest_sha256"])
        manifest = manifests[header]
        targets = {row["target_id"]: row for row in manifest["configuration"]["targets"]}
        if manifest["receiver_ids"] != [0, 1] or manifest["sample_rate_hz"] != 10_000_000:
            raise ValueError("Expected the original stereo 10 MS/s recording")
        index = folder / member["index_relative_path"]
        if index.resolve(strict=True) != index:
            raise ValueError("The index is not the fixed local file")
        rows = omitted_index(index, member, ShortWindowIndexV2)
        verified.append(dict(index_sha256=member["index_sha256"], manifest_sha256=member["manifest_sha256"],
                             original_member=member["ordinal"], omitted=member["omit"], bytes=member["index_bytes"]))
        for visit, row in enumerate(rows, member["first_visit"]):
            a, target = row.acquisition, targets[row.target_id]
            if a["global_visit"] != visit or visit != len(hashes):
                raise ValueError("The archived visit sequence changed")
            clock = json.loads(a["retune_receipt"])
            if (clock["host_delivery_clock"] != parent["delivery_clocks"][visit]
                    or visit == 0 and clock["utc_clock_bracket"] != parent["clock_anchor"]):
                raise ValueError("Original clock bracket or signed sample timing changed")
            hashes.append(row.iq_sha256)
            observed = valid_window_support(a, manifest["sample_rate_hz"], (row.sample_count, row.receiver_count, 2), (0, 1), policy)
            if not observed:
                if visit not in invalid or (invalid[visit]["sample_start"], invalid[visit]["sample_end"], invalid[visit]["iq_sha256"]) != (
                        a["sample_start"], a["sample_end"], row.iq_sha256):
                    raise ValueError("Raw admission metadata and archived invalid rows disagree")
                continue
            stream = (target["edge"], target["channel"], float(a["actual_if_center_hz"]+target["lnb_lo_hz"]))
            slot = truths[stream]
            truths[stream] += 1
            full = slot % 8 == 0
            expected = dict(visit_index=visit, receiver_id=0, probe_index=0, probe_start_ms=0, channel=stream[1],
                            edge=stream[0], actual_rf_hz=stream[2], valid_start_counter=a["sample_start"],
                            payload_start_sample=visit * policy.window_samples, candidates=[])
            if admitted[visit] != (stream, slot, full) or published[visit] != expected:
                raise ValueError("Original index identity, aperture or opportunity differs from the field packet")
            witnessed[visit] = [*stream, slot, full]
            if not member["omit"]:
                compacted = wrong_retained[stream] % 8 == 0
                shift["retained_apertures_changed_by_recount"] += compacted != full
                wrong_retained[stream] += 1
    if len(hashes) != stop or set(witnessed) != {visit for visit in admitted if visit < stop}:
        raise ValueError("Complete local attested index coverage changed")
    complete = stop == parent["provenance"]["window_count"]
    source = parent["source"]
    raw = digest([source["input_manifest_sha256"], hashes]) if complete else None
    if complete and raw != source["raw_recording_authority_digest"]:
        raise ValueError("Index-only raw authority reconstruction disagrees with historical acquisition")
    return dict(issued=stop, admitted=len(witnessed), full_anchor_stereo_visits=sum(r[-1] for r in witnessed.values()),
                complete_raw_authority=raw, original_admitted_schedule_sha256=digest(witnessed), index_receipts=verified,
                invalid=stop-len(witnessed), shift_if_recounting=shift, waveform_opens=0)


def main(output):
    root = Path(__file__).resolve().parent
    roster = accession()
    weak = json.loads(gzip.decompress(checked(root/"measurements/ds30-0016-full-primary-transfer.json.gz", WEAK)))
    weak = weak["detector_packets"]["charted"]["document"]
    four = json.loads(gzip.decompress(checked(root/"measurements/ds30-0049-receiver-factorial.json.gz", FACTORIAL)))
    case = FIELD / "cases/DS30-0049"
    native, = (case / "successor/attempt-000002/publication/fast-scan-automatic-work").glob("*/detections.json")
    result = read(case / "successor/attempt-000002/result.json", "dd123ba20c9c7ecfcec3736469c1b85e11fa0eeb6b49455c0df3faddc05aa5fa")
    prefix = read(native, result["native_sha256"])
    saved = four["selection.json"]["document"]["cells"]["8-primary/strongest"]["probes"]
    if saved != [row for row in prefix["source"]["probes"] if row["visit_index"] < 384]:
        raise ValueError("Independent native-at-aperture factor tape differs from authentic field publication")
    scopes = [("DS30-0016", 808, weak), ("DS30-0049", 384, prefix)]
    write(output, {case: check_index_scope(roster[case], doc, STAGES[case], stop) for case, stop, doc in scopes})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    main(cli.parse_args().output)
