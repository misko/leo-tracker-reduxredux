"""Frozen-IQ diagnostic: candidate support over the first three startup epochs."""

import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
out = BASE / "startup-persistence-ranking-v1"
out.mkdir(exist_ok=False)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
proposals = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())["cases"]
inputs = json.loads((BASE / "combined-pilot-controls-v1/result.json").read_text())["cases"]
refs = np.fromfile(BASE / "direct-references.ci16", dtype="<i2").reshape(4, 3300, 4).astype(float)
ref = refs[0, :, 0] + 1j * refs[0, :, 1]
energy = np.vdot(ref, ref).real
binary = BASE / "expanded-worker-v1/bench"
assert (
    digest(binary)
    == json.loads((BASE / "expanded-worker-v1/result.json").read_text())["binary_sha256"]
)
result = dict(
    scope="frozen_startup_persistence_ranking",
    new_rf_samples=0,
    arm_cost_measured=False,
    live_tracking_qualified=False,
    acceptance_gates_changed=False,
    frames=[0, 9, 18],
    shifts=[0, 30000, 60000],
    shortlist_budgets=[8, 64],
    aggregations=["minimum", "mean", "geometric_mean"],
    script_sha256=digest(Path(__file__)),
    binary_sha256=digest(binary),
    cases=[],
)
for case, source in zip(proposals, inputs, strict=True):
    assert (case["label"], case["number"]) == (source["label"], source["number"])
    label = f"{case['label']}-{case['number']}"
    path = BASE / "combined-pilot-controls-v1" / label / "iq.ci16"
    assert digest(path) == source["input_sha256"]
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 2).astype(float)
    iq = raw[:, 0] + 1j * raw[:, 1]
    powers = []
    for peak in case["scores"][:64]:
        row = []
        for shift in result["shifts"]:
            first = peak["epoch"] + 22 + shift
            z = iq[first : first + 3300]
            assert len(z) == 3300
            spectrum = np.fft.fft(z * ref.conj(), 4096)
            index = abs(spectrum).argmax()
            denominator = max(float(energy * np.vdot(z, z).real), 1)
            power = float(abs(spectrum[index]) ** 2 / denominator)
            direct = (
                abs(np.vdot(ref, z * np.exp(-2j * np.pi * index * np.arange(3300) / 4096))) ** 2
                / denominator
            )
            np.testing.assert_allclose(power, direct, rtol=2e-10, atol=2e-14)
            row.append(power)
        powers.append(row)
    powers = np.asarray(powers)
    ranking = np.argsort(-powers[:, 0], kind="stable")
    runs = {}
    comparisons = []
    for budget in result["shortlist_budgets"]:
        selected = ranking[:budget]
        for policy in result["aggregations"]:
            aggregate = {
                "minimum": powers.min(axis=1),
                "mean": powers.mean(axis=1),
                "geometric_mean": np.exp(
                    np.log(np.maximum(powers, np.finfo(float).tiny)).mean(axis=1)
                ),
            }[policy]
            winner = int(selected[np.argmax(aggregate[selected])])
            peak = case["scores"][winner]
            if winner not in runs:
                run = subprocess.run(
                    [
                        str(binary),
                        str(path),
                        str(BASE / "direct-references.ci16"),
                        str(peak["epoch"]),
                        str(peak["frequency"]),
                        str(peak["coarse_score"]),
                    ],
                    capture_output=True,
                    check=True,
                    timeout=12,
                )
                assert not run.stderr
                journal = out / f"{label}-candidate{winner + 1}.jsonl"
                journal.write_bytes(run.stdout)
                rows = [json.loads(line) for line in run.stdout.splitlines()]
                runs[winner] = dict(
                    winner=winner + 1,
                    proposal=peak,
                    terminal=rows[-1],
                    accepted=sum(r["accepted"] for r in rows if r["kind"] == 3),
                    journal_sha256=digest(journal),
                )
            comparisons.append(
                dict(
                    budget=budget, policy=policy, aggregate=float(aggregate[winner]), **runs[winner]
                )
            )
    result["cases"].append(
        dict(
            label=case["label"],
            number=case["number"],
            input_sha256=digest(path),
            powers=powers.tolist(),
            first_rank_order=(ranking + 1).tolist(),
            comparisons=comparisons,
        )
    )
    print(
        label,
        [(c["budget"], c["policy"], c["winner"], c["accepted"]) for c in comparisons],
        flush=True,
    )
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
