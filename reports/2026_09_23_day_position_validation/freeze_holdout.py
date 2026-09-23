"""Freeze the computationally bounded, day-spanning predictive test before scores."""
import hashlib
import json
from pathlib import Path

out=Path(__file__).resolve().parent
inventory=json.loads((out/"inventory.json").read_text())
eligible=inventory["eligible_session_ids"]
indices=[round(i*(len(eligible)-1)/15) for i in range(16)]
assert len(set(indices))==16
points=out.parent/"2026_09_23_sixteen_scan_comparison/common_finalists.json"
receipt=dict(selection="16 evenly spaced eligible chronological indices including endpoints; frozen before new frequency scoring",
    inventory_sha256=hashlib.sha256((out/"inventory.json").read_bytes()).hexdigest(),
    session_ids=[eligible[i] for i in indices],eligible_indices=indices,
    locations=json.loads(points.read_text()),locations_sha256=hashlib.sha256(points.read_bytes()).hexdigest(),
    candidate_policy="Full causal Starlink catalogue; no published winner shortlist; candidate and nuisance selection use training rows only",
    partition="Exact existing randomized training mask; no chronological frequency holdout",
    timing_grid_s=list(range(-5,6)),
    decision_policy="All five geographic positions frozen; no new location refinement or parameter tuning on test outcomes",
    scientific_scope="Prospective scoring protocol on a retrospective disjoint scan cohort; reconstructed track support is conditioned upon",
    replication_scope="All116scans receive separate conditional-shortlist block replication; this16-scan subset is reserved for full-catalogue predictive scoring")
(out/"holdout_protocol.json").write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps(receipt,indent=2))
