"""Validate all four preselected narrowband matched-time recovery receipts."""

import hashlib
import json
from pathlib import Path

import numpy as np
from simultaneous_coverage import usable_pair

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/simultaneous5"


def main():
    results, sources = [], {}
    for index in range(4):
        receipt = OUT / f"pair-{index}/recovery.json"
        recovery = json.loads(receipt.read_text())
        executed = OUT / "executed-recovery.py"
        assert hashlib.sha256(executed.read_bytes()).hexdigest() == recovery["method_sha256"]
        sources[str(receipt)] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        excerpts, visits = [], []
        for r in recovery["rows"]:
            artifact = Path(r["artifact"])
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == r["artifact_sha256"]
            with np.load(artifact) as data:
                meta = json.loads(str(data["metadata"]))
            pilots = [meta["diagnostics"][f]["held_pilot_coherence"]
                      for f in meta["evaluation_frames"]]
            qualified = [f for f in meta["evaluation_frames"]
                         if meta["diagnostics"][f]["held_pilot_coherence"] > .5]
            assert qualified == r["qualified"]
            excerpts.append(dict(id=r["id"], visit=r["visit"], part=r["part"],
                qualified=len(qualified), evaluation_frames=len(pilots),
                held_pilot_max=float(max(pilots)), held_pilot_median=float(np.median(pilots))))
        for part in sorted({r["part"] for r in recovery["rows"]}):
            a, b = [r for r in recovery["rows"] if r["part"] == part]
            visits.append(dict(part=part, visit=a["visit"], usable=usable_pair(a, b)))
        results.append(dict(pair=index, shared_visits=len(recovery["common_visits"]),
                            excerpts=excerpts, visits=visits))
    result = dict(pairs=results, source_sha256=sources,
                  executed_method_sha256=hashlib.sha256(executed.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  usable_visits=sum(v["usable"] for r in results for v in r["visits"]),
                  limitation="Fixed acquisition-margin selection, held-pilot >0.5. Failure "
                  "is lack of comparison coverage, not evidence about header identity.")
    (OUT / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in results:
        print(r["pair"], [(v["visit"], v["qualified"]) for v in r["excerpts"]])
    print("Usable matched visits:", result["usable_visits"])


if __name__ == "__main__":
    main()
