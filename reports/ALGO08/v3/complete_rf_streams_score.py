"""Join measured owner families to original RF and capture-clock support."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean, pvariance

from . import balanced_stereo as shared


def coverage(owners, factors):
    families = defaultdict(list)
    if len({oid for oid, _, _ in owners}) != len(owners):
        raise ValueError("Duplicate owner in published evidence")
    for oid, family, role in owners:
        row = factors[oid]
        if row["signal"] is None:
            raise ValueError("A published owner has no measured signed factor")
        families[family].append((row, role))
    result = {}
    for family, group in sorted(families.items()):
        rows, roles = zip(*group, strict=True)
        times = [row["time_s"] for row in rows]
        frequencies = [row["rf_hz"] for row in rows]
        result[family] = dict(owners=len(rows), channels=Counter(row["channel"] for row in rows),
                              roles=Counter(roles), receivers=sorted({row["receiver"] for row in rows}),
                              minimum_time_s=min(times), maximum_time_s=max(times),
                              span_s=max(times)-min(times), mean_rf_hz=mean(frequencies), variance_rf_hz2=pvariance(frequencies))
    return result


def audit(root, output):
    from anchor_exposure import PINS, packet
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from quadratic_support import native_rows
    from whole_stereo_8ms import SAVED_PIN, SAVED_SEAL
    from whole_stereo_blocks import load_checked

    scored = shared.read(root/"result.json")
    controls = load_checked(SAVED_SEAL, SAVED_PIN)["runs"]
    for case, row in scored["scores"].items():
        if row["decision"] != "complete":
            continue
        sample = PINS["DS30-0016" if case == "weak" else case]["8ms"]
        original = native_rows(packet(*sample))
        candidate_pin = row["plan"]["masked_witness"]["native_sha256"]
        selected = native_rows(load_checked(root/case/"detections.json", candidate_pin[7:]))
        evidence = row["verified"]
        control = controls[case]["history8"]["science"]
        owner_audit = {}
        for arm in shared.ARMS:
            owners = evidence["science"]["roles"][arm]
            if (canonical_digest({oid: family for oid, family, _ in owners}) != evidence["verified"]["owners"][arm]
                    or any(selected[oid] != original[oid] for oid, _, _ in owners)):
                raise ValueError("A retained owner cannot introduce a different native measurement")
            owner_audit[arm] = dict(all8=coverage(control["roles"][arm], original), candidate=coverage(owners, selected))
        row["audit"]["full_and_selected_owner_rf_coverage"] = owner_audit
    scored["sealed_input_sha256"] = sha256((root/"result.json").read_bytes()).hexdigest()
    scored["read_only_audit_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    shared.write(output, scored)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    audit(args.result_root, args.output)
