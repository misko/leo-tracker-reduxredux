"""Independent selected-power, candidate provenance and frozen worker review."""

import copy
import hashlib
import json
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
root = BASE / "startup-persistence-ranking-v1"
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
reviewer = BASE / "review_missed_candidate_replay.py"
ns = {"__file__": str(reviewer)}
exec(compile(reviewer.read_text().split("\nmanifest=json.loads", 1)[0], str(reviewer), "exec"), ns)
ns["ROOT"] = BASE / "combined-pilot-controls-v1"
manifest = json.loads((root / "result.json").read_text())
proposals = json.loads((BASE / "expanded-proposal-ranking-v1.json").read_text())["cases"]
ref = ns["bases"][0][:, 0]
energy = np.vdot(ref, ref).real
results = []
decisions = mutations = 0
for case, original in zip(manifest["cases"], proposals, strict=True):
    assert (case["label"], case["number"]) == (original["label"], original["number"])
    label = f"{case['label']}-{case['number']}"
    path = ns["ROOT"] / label / "iq.ci16"
    assert digest(path) == case["input_sha256"]
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 2).astype(float)
    iq = raw[:, 0] + 1j * raw[:, 1]
    powers = np.asarray(case["powers"])
    order = np.argsort(-powers[:, 0], kind="stable")
    assert (order + 1).tolist() == case["first_rank_order"]
    seen = set()
    for choice in case["comparisons"]:
        aggregate = {
            "minimum": np.min(powers, axis=1),
            "mean": np.mean(powers, axis=1),
            "geometric_mean": np.exp(
                np.mean(np.log(np.maximum(powers, np.finfo(float).tiny)), axis=1)
            ),
        }[choice["policy"]]
        selected = order[: choice["budget"]]
        winner = int(selected[np.argmax(aggregate[selected])])
        assert winner + 1 == choice["winner"] and aggregate[winner] == choice["aggregate"]
        peak = original["scores"][winner]
        assert choice["proposal"] == peak
        decisions += 1
        if winner in seen:
            continue
        seen.add(winner)
        for repeat, shift in enumerate((0, 30000, 60000)):
            start = peak["epoch"] + 22 + shift
            z = iq[start : start + 3300]
            spectrum = np.fft.fft(z * ref.conj(), 4096)
            frequency = abs(spectrum).argmax()
            direct = abs(
                np.vdot(ref, z * np.exp(-2j * np.pi * frequency * np.arange(3300) / 4096))
            ) ** 2 / max(float(energy * np.vdot(z, z).real), 1)
            np.testing.assert_allclose(powers[winner, repeat], direct, rtol=2e-10, atol=2e-14)
        journal = root / f"{label}-candidate{winner + 1}.jsonl"
        assert digest(journal) == choice["journal_sha256"]
        rows = [json.loads(x) for x in journal.read_text().splitlines()]
        assert rows[-1] == choice["terminal"]
        description = dict(label=label, proposal=peak)
        checked = ns["check"](description, rows)
        assert checked["accepted"] == choice["accepted"]
        assert [r["frame"] for r in rows if r["kind"] == 3][:3] == [0, 9, 18]
        results.append(dict(winner=winner + 1, **checked))
        if label == "positive-0":
            for field in ("coherence", "cfo_hz"):
                changed = copy.deepcopy(rows)
                next(r for r in changed if r["kind"] == 3)[field] += 0.001
                try:
                    ns["check"](description, changed)
                except AssertionError:
                    mutations += 1
                else:
                    raise AssertionError("corruption accepted")
summary = []
for budget in (8, 64):
    for policy in manifest["aggregations"]:
        successes = {
            label: [
                c["number"]
                for c in manifest["cases"]
                if c["label"] == label
                and next(
                    x for x in c["comparisons"] if (x["budget"], x["policy"]) == (budget, policy)
                )["terminal"]["worker_result"]
                == 1
            ]
            for label in ("positive", "control")
        }
        summary.append(dict(budget=budget, policy=policy, **successes))
result = dict(
    status="pass",
    ranking_decisions=decisions,
    worker_checks=len(results),
    resolver_hypotheses=sum(r["resolver_hypotheses"] for r in results),
    moment_dense_fits=sum(r["moment_dense_fits"] for r in results),
    mutations_rejected=mutations,
    summary=summary,
    live_tracking_qualified=False,
    arm_cost_measured=False,
    new_rf_samples=0,
    script_sha256=digest(Path(__file__)),
    reused_reviewer_sha256=digest(reviewer),
    cases=results,
)
with (root / "independent-review.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps({k: v for k, v in result.items() if k != "cases"}))
