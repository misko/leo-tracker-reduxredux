#!/usr/bin/env python3
"""Host checks for all supported rates, partial support, zeros, and control parity."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEATURES = ("lag1", "lag3", "lag5", "power")
RATES = (2500000, 5000000, 7500000, 10000000)


def write_case(directory, rate, zero):
    n = round(rate / 750)
    template = directory / "template.c128"
    iq = directory / "IQ.ci16"
    if zero:
        template.write_bytes(struct.pack("<" + "d" * (2 * n), *([0.0] * (2 * n))))
        iq.write_bytes(bytes(rate * 120 // 1000 * 8))
        return template, iq
    reference = []
    for sample in range(n):
        reference.extend((float((sample * 17) % 101 - 50), float((sample * 29) % 89 - 44)))
    template.write_bytes(struct.pack("<" + "d" * len(reference), *reference))
    samples = rate * 120 // 1000
    values = []
    for sample in range(samples):
        if sample >= samples * 3 // 4:
            values.extend((0, 0, 0, 0))
        else:
            values.extend((((sample * 11) % 251 - 125), ((sample * 7) % 239 - 119),
                           ((sample * 13) % 233 - 116), ((sample * 19) % 227 - 113)))
    iq.write_bytes(struct.pack("<" + "h" * len(values), *values))
    return template, iq


def run(binary, rate, template, iq, *flags):
    completed = subprocess.run([str(binary), str(rate), str(template), str(iq), *flags], text=True, capture_output=True, check=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(rows) == 22
    return rows


def comparable(rows):
    return [{"receiver_id": row["receiver_id"], "probe_index": row["probe_index"],
             "top4": row["top4"]["combined"]} for row in rows]


def main():
    feature = ROOT / "builds/host/proposal_feature_ablation"
    control = ROOT / "builds/host/control_proposal_probe"
    results = []
    with tempfile.TemporaryDirectory(prefix="proposal-feature-ablation-") as temporary:
        directory = Path(temporary)
        for rate in RATES:
            for zero in (False, True):
                template, iq = write_case(directory, rate, zero)
                base = run(feature, rate, template, iq, "--combined-only")
                oracle = run(control, rate, template, iq, "--combined-only")
                assert comparable(base) == comparable(oracle)
                assert all(row["feature_mask"] == list(FEATURES) for row in base)
                if zero:
                    assert all(not row["top4"]["combined"] for row in base)
                else:
                    full = run(feature, rate, template, iq, "--scores")
                    scored_oracle = run(control, rate, template, iq, "--scores")
                    for actual, expected in zip(full, scored_oracle, strict=True):
                        assert actual["receiver_id"] == expected["receiver_id"]
                        assert actual["probe_index"] == expected["probe_index"]
                        assert actual["top32"] == expected["top32"]
                        assert actual["scores"] == expected["scores"]
                for omitted in FEATURES:
                    rows = run(feature, rate, template, iq, "--combined-only", f"--omit={omitted}")
                    expected = [name for name in FEATURES if name != omitted]
                    assert all(row["feature_mask"] == expected for row in rows)
                    if zero:
                        assert all(not row["top4"]["combined"] for row in rows)
                results.append({"rate": rate, "case": "zero" if zero else "partial", "rows": len(base)})
    receipt = {"schema": "arm-proposal-feature-ablation-test/v1", "passed": True,
               "rates": list(RATES), "cases": results,
               "partial_input": "first 90 ms deterministic CI16 signal followed by 30 ms zero CI16 at each rate",
               "control_parity": "exact JSON numerical equality for all scores and top32 at every rate on partial input; top4 parity at every rate and both input cases"}
    (ROOT / "host-test-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
