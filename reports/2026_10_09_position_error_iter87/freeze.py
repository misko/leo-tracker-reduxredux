"""Seal source and all148 immutable B7 input bindings before residual audit."""

import datetime
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists(), "Never overwrite a frozen protocol"
    original = audit.ARCHIVE / "protocol.json"
    old = json.loads(original.read_text())
    files = {ROOT / name for name in old["source_sha256"]}
    files.add(original)
    members = []
    for binding in old["members"]:
        label = binding["member"]["inventory_label"]
        source = audit.ARCHIVE / "results" / f"{label}.json"
        assert source.is_file(), source
        files.add(source)
        members.append(dict(binding, b7_source=str(source.relative_to(ROOT))))
    files.update(HERE / name for name in ("audit.py", "freeze.py", "residual_stats.py"))
    files.add(HERE / "README.md")
    native = importlib.util.find_spec("leo.analysis._regional_orbits")
    assert native is not None and native.origin is not None
    files.add(Path(native.origin).resolve())
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if (
            path.is_file()
            and path.suffix in (".py", ".so")
            and (
                path.is_relative_to(ROOT / "reports")
                or path.is_relative_to(ROOT / "src/leo")
                or "/worker/src/leo/" in str(path)
            )
        ):
            files.add(path)
    assert len(members) == 148
    assert Counter(x["member"]["dataset"] for x in members) == dict(DS16=63, DS17=51, DS18=34)
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members,
        shards=2,
        optimizer_calls=0,
        reconstruction="Both accepted B7 objectives match within1e-6; staticc/RF-time zero in c0",
        assignments="Maximum fitted-B7 responsibility strictly >0.5; same assignments botharms",
        pairs="Same satellite/channel/time rounded milliseconds; average duplicates withinRX",
        eligibility="At least10 pairs per satellite; fewer than2 eligible satellites is no-op",
        serial="Same satellite/receiver/channel; adjacent time gap(0,2]seconds; >=10pairs",
        margin="Original GLRT margin; descriptive only, no variance/weight calibration",
        reference="No known coordinates or reference errors for grouping or selection",
        failures="Retain all148 membership, explicit input/reconstruction/statistics failures",
        execution="Prepare only; launch after parent capacity approval, at most two singlethreads",
        scope="Consumed development; no optimizer, RF, productionchange or reserveoutcome access",
        source_sha256={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(files)
        },
    )
    audit.write(destination, plan)
    print("Frozen148 B7 residual audits; no optimizer or audit launched", flush=True)


if __name__ == "__main__":
    main()
