"""Select 30 visit identities from metadata without opening phase results."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BINDING = ROOT / "reports/figures/2026_09_23_scan_glrt_multiplicity/relaxed-rx0-anchor-binding.json"
OUT = ROOT / "reports/figures/2026_09_23_relaxed_adaptive_coherence/random-30-selection.json"


def main():
    metadata = json.loads(BINDING.read_text())
    population = sorted(row["visit_index"] for row in metadata["rows"])
    chosen = sorted(random.Random(20260923).sample(population, 30))
    document = {
        "method": "Python random.Random(20260923).sample(sorted eligible visit IDs, 30)",
        "seed": 20260923, "population_size": len(population),
        "binding_sha256": hashlib.sha256(BINDING.read_bytes()).hexdigest(),
        "selection_reads_phase_results": False, "visit_indices": chosen,
        "reference_visit_indices": [1065, 1077, 1109, 1113, 1140],
        "scope_note": "Full replay finished before user narrowed review; sample chosen from metadata only.",
    }
    OUT.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(document))


if __name__ == "__main__":
    main()
