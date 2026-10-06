"""Exploratory post hoc 16/32-basin check; frozen primary remains budget eight."""

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from bandwidth_replay import filter_decimate
from reacquire import run

from leo.storage.adaptive_hop import AdaptiveHopIqStore

ROOT = Path(__file__).resolve().parent


def main():
    data = json.loads((ROOT / "reacquisition-results.json").read_text())
    out = dict(purpose=__doc__, maximum_runtime_seconds=60, rows=[])
    started = time.monotonic()
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    for r in data["rows"]:
        if r["kind"] != "saved_iq" or r["receiver_id"] != 1:
            continue
        with store.reader(r["session_id"]) as reader:
            indexes = {
                v.event.visit_index: i for i, v in enumerate(reader.session.manifest.receipt.visits)
            }
            _, vals = reader.read_visit_ci16(indexes[r["visit_index"]])
            x = vals[600000:800000, 1, :]
            iq = x[:, 0].astype(float) + 1j * x[:, 1].astype(float)
            nominal = -312500 if r["edge"] == "lower" else 312500
            seed = (
                int(
                    hashlib.sha256((r["session_id"] + ":RX1-budget-null").encode()).hexdigest()[:8],
                    16,
                )
                ^ 20261006
            )
            rng = np.random.default_rng(seed)
            null = (rng.normal(size=len(iq)) + 1j * rng.normal(size=len(iq))) * np.sqrt(
                np.mean(abs(iq) ** 2) / 2
            )
            for kind, signal in [("saved_iq", iq), ("gaussian_null", null)]:
                low, _, _ = filter_decimate(signal, nominal)
                row = {
                    k: r[k]
                    for k in (
                        "session_id",
                        "split",
                        "edge",
                        "channel",
                        "receiver_id",
                        "visit_index",
                    )
                }
                row["kind"] = kind
                for budget in (16, 32):
                    row[str(budget)] = run(low, 2500000, 0, r["edge"], 400000, 1, budget=budget)
                    print(
                        r["split"],
                        r["edge"],
                        kind,
                        budget,
                        round(row[str(budget)]["elapsed_seconds"], 2),
                        flush=True,
                    )
                out["rows"].append(row)
                if time.monotonic() - started > 60:
                    break
        if time.monotonic() - started > 60:
            break
    store.close()
    out["elapsed_seconds"] = time.monotonic() - started
    (ROOT / "budget-results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
