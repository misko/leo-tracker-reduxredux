"""Post hoc diagnostic: transport acquired high-rate winners into narrowed IQ.

This explains acquisition/conditioning differences; does not tune a threshold
or modify the frozen reacquisition settings or its results.
"""

import json
from pathlib import Path

from bandwidth_replay import filter_decimate, frame_inventory, score, transform_seed

from leo.storage.adaptive_hop import AdaptiveHopIqStore

ROOT = Path(__file__).resolve().parent


def main():
    data = json.loads((ROOT / "reacquisition-results.json").read_text())
    out = dict(purpose=__doc__, rows=[])
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    for r in data["rows"]:
        if r["kind"] != "saved_iq":
            continue
        with store.reader(r["session_id"]) as reader:
            indexes = {
                v.event.visit_index: i for i, v in enumerate(reader.session.manifest.receipt.visits)
            }
            _, vals = reader.read_visit_ci16(indexes[r["visit_index"]])
            x = vals[600000:800000, r["receiver_id"], :]
            iq = x[:, 0].astype(float) + 1j * x[:, 1].astype(float)
            nominal = -312500 if r["edge"] == "lower" else 312500
            low, _, _ = filter_decimate(iq, nominal)
            row = {
                k: r[k]
                for k in ("session_id", "split", "edge", "channel", "receiver_id", "visit_index")
            }
            for label in ("full", "search_only"):

                def margin(c):
                    value = c["fractional_glrt"]["fractional_margin"]
                    return value if value is not None else c["integer_glrt"]["margin"]

                c = max(r[label]["candidates"], key=margin)
                a = c["acquisition"]
                fr = c["fractional_glrt"]
                original_fraction = fr["fractional_epoch_offset_samples"] or 0.0
                ep, fraction, cfo = transform_seed(
                    a["refined_epoch_sample"], original_fraction, a["absolute_cfo_hz"], nominal
                )
                before = frame_inventory(
                    len(iq), 10000000, a["refined_epoch_sample"], original_fraction
                )
                after = frame_inventory(len(low), 2500000, ep, fraction)
                assert before == after
                row[label] = dict(
                    original_margin=margin(c),
                    transported_score=score(low, 2500000, ep, fraction, cfo, r["edge"]),
                    frame_indexes=before,
                    acquired_pilot_relative_hz=cfo,
                )
            out["rows"].append(row)
    store.close()
    (ROOT / "transport-results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
