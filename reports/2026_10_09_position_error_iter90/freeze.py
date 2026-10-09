"""Prepare immutable full148 paired-data diagnostic closure before execution."""

import datetime
import hashlib
import json
from pathlib import Path

import audit_pairs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists(), "Never overwrite a frozen protocol"
    upstream = HERE.parent / "2026_10_09_position_error_iter87/protocol.json"
    old = json.loads(upstream.read_text())
    files = {ROOT / name for name in old["source_sha256"]}
    # The inherited executable/input closure must still reproduce its freeze.
    for name, expected in old["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    files.add(upstream)
    files.update(
        HERE / name for name in ("audit_pairs.py", "paired_join.py", "freeze.py", "README.md")
    )
    files.add(HERE.parent / "2026_10_09_position_error_iter88/linear_contrast.py")
    assert len(old["members"]) == 148
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=old["members"],
        shards=2,
        optimizer_calls=0,
        contrast_sigma_hz=audit_pairs.CONTRAST_SIGMA_HZ,
        window_sigma_hz=audit_pairs.WINDOW_SIGMA_HZ,
        pair_variance_hz2=audit_pairs.PAIR_VARIANCE_HZ2,
        pair_noise="sqrt(2)*125Hz working independent-window approximation, not calibrated",
        assignments="Fitted B7 maximum responsibility >0.5, same assignments/pairs botharms",
        pairs="RX1-RX0, exact round(time_s*1000) satellite/channel join, duplicateaverage",
        background="Unpenalized intercept+centeredlinear time+deterministicchannel indicators",
        eligibility="At least10pairs per satellite, at least2satellites; explicit no-op",
        controls="Unadjusted zero-sum means vs backgroundprojected, fixed30Hzprior",
        sensitivity="ExistingB7 smoothclock pair differences; noRF/satelliteblocks/newknots",
        scope="Full148 consumeddevelopment; no optimizer, newpositions or referenceguidedchoice",
        failures="Retain every member, explicit input/reconstruction/diagnostic failure",
        execution="Only after parent review/freeze/capacityapproval; at mosttwo singlethreads",
        reserve="No reserve outcomes or RFcollection/productionchange",
        source_sha256={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(files)
        },
    )
    audit_pairs.write(destination, plan)
    print("Frozen148 paired diagnostics; no audit/optimizer launched")


if __name__ == "__main__":
    main()
