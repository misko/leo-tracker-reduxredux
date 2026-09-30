"""Reproduce concurrent-track inventory and report matched-excerpt assay coverage."""

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent


def usable_pair(a, b):
    assert a["visit"] == b["visit"]
    assert a["source"]["excerpt_sha256"] == b["source"]["excerpt_sha256"]
    return min(len(a["qualified"]), len(b["qualified"])) >= 2


def main():
    metadata = BASE / "local/rows.json"
    census = BASE.parent / "2026_09_29_ds10_signal_extension/local/census.json"
    rows = json.loads(metadata.read_text())
    captures = {c["unit"]: {t["track_id"]: t for t in c["tracks"]}
                for c in json.loads(census.read_text())["captures"]}
    counts, opportunities = Counter(), []
    for a, b in itertools.combinations(rows, 2):
        if (a["unit"], a["edge"], a["channel"]) != (b["unit"], b["edge"], b["channel"]):
            continue
        t, u = [captures[r["unit"]][r["track_id"]] for r in (a, b)]
        common = sorted(set(t["visits"]) & set(u["visits"]))
        if not common:
            continue
        rx = "same_rx" if a["receiver"] == b["receiver"] else "different_rx"
        label = "unlabelled"
        if a["norad_id"] and b["norad_id"]:
            label = "same_ID" if a["norad_id"] == b["norad_id"] else "different_ID"
        counts[f"{rx}/{label}"] += 1
        if label == "different_ID":
            opportunities.append(dict(ids=[a["id"], b["id"]], receiver_match=rx,
                rate=a["rate"], tiers=[a["tier"], b["tier"]], common_visits=common))
    recovery = BASE / "local/simultaneous/recovery.json"
    recovered = json.loads(recovery.read_text())
    archived = recovery.with_name("executed-recovery.py")
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == recovered["method_sha256"]
    coverage = []
    for part in range(3):
        a, b = [r for r in recovered["rows"] if r["part"] == part]
        for r in (a, b):
            digest = hashlib.sha256(Path(r["artifact"]).read_bytes()).hexdigest()
            assert digest == r["artifact_sha256"]
        coverage.append(dict(part=part, visit=a["visit"], usable=usable_pair(a, b),
                             qualified_counts=[len(a["qualified"]), len(b["qualified"])]))
    result = dict(counts=dict(counts), opportunities=opportunities, coverage=coverage,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (metadata, census, recovery, archived)},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  conclusion="No matched visit has two qualified frames per candidate; abstain "
                  "from header comparison. Conditional identities do not establish two satellites.")
    recovery.with_name("coverage.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
