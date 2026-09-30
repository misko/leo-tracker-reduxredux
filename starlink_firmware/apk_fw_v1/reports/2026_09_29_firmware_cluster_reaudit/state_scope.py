"""Audit T-state prediction support and distinct baselines without another scan."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
EXT = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local"


def supported_frames(summary):
    state = {w["frame"]: w["phase_hypothesis"] for w in summary["windows"] if w["label"] == 1}
    qualified = summary["qualified_frames"]
    split = len(qualified) // 2
    train = [f for f in qualified[:split] if f in state]
    counts = Counter(state[f] for f in train)
    eligible = sorted(s for s, n in counts.items() if n >= 2)
    test = [f for f in qualified[split:] if f in state and state[f] in eligible]
    return train, test, eligible, counts


def check_baselines(metrics):
    # SSE(state)/SSE(zero) = SSE(state)/SSE(global) * SSE(global)/SSE(zero).
    left = 1 - metrics["state_over_zero_error_reduction"]
    right = ((1 - metrics["state_over_global_error_reduction"])
             * (1 - metrics["global_over_zero_error_reduction"]))
    # Historical reductions can be computed from complex64 arrays; ratios and
    # 1-ratio incur float32 rounding before conversion to JSON floats.
    np.testing.assert_allclose(left, right, rtol=8 * np.finfo(np.float32).eps, atol=1e-12)


def main():
    path = EXT / "within-visit/state-transfer.json"
    original = json.loads(path.read_text())
    visits = []
    for row in original["visits"]:
        directory = EXT / "paired" / row["visit"]
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text())
        data_path = directory / f"{row['visit']}-data-soft.npz"
        assert hashlib.sha256(data_path.read_bytes()).hexdigest() == row["source_sha256"]
        train, test, eligible, counts = supported_frames(summary)
        assert train == row["train_frames"] and test == row["test_frames"]
        assert eligible == row["eligible_states"]
        supported = len(train) >= 4 and len(test) >= 4 and len(eligible) >= 2
        assert supported == ("assays" in row)
        for assay in row.get("assays", []):
            check_baselines(assay["raw"])
            check_baselines(assay["residual"])
        if supported:
            for a, b in zip(row["assays"][:5], row["assays"][5:], strict=True):
                assert a["symbols"] == b["symbols"] and a["raw"] == b["raw"]
        visits.append(dict(**row, training_state_counts=dict(counts),
                           summary_source=dict(path=str(summary_path),
                               sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest())))
    result = dict(visits=visits, source=dict(path=str(path),
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Eligibility reconstructed from original window receipts and "
                  "source NPZ hashes checked. Saved score identities checked, fits not rerun. "
                  "Only one supported excerpt. Raw assays repeat across the two gain models "
                  "and must not count as independent replication. Shuffled-label ranks do "
                  "not replace the state-independent prediction baseline.")
    (BASE / "local/state-scope.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Visits", len(visits), "supported", sum("assays" in v for v in visits))


if __name__ == "__main__":
    main()
