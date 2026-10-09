"""Preserve original failures while reporting isolated metadata retries."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "protocol.json").read_text())
digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
rows = []
for binding in plan["members"]:
    member = binding["member"]
    label = member["inventory_label"]
    original = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter51/results" / f"{label}.json").read_text()
    )
    assert original["status"] == "failed" and original["error"] == "KeyError('bank')"
    row = dict(member=member, original_attempt=original, retry_status="pending")
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        result = json.loads(path.read_text())
        row["retry_status"] = result["status"]
        if result["status"] == "complete":
            assert result["member"] == member and result["protocol_sha256"] == digest
            row["arms"] = {
                a: dict(
                    previous_error_km=result["previous_candidate"][a]["error_km"],
                    retry_error_km=result["extension"]["operational"][a]["error_km"],
                    frequency_rms_hz=result["extension"]["operational"][a]["posterior_rms_hz"],
                    raw_final_converged=result["extension"]["stages"]["slope-0.25"][a]["converged"],
                )
                for a in ("fitted-c", "zero-c")
            }
        else:
            row["retry_error"] = result.get("error")
    rows.append(row)
summary = dict(complete=sum(r["retry_status"] == "complete" for r in rows), expected=2, rows=rows)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
text = f"""# Iteration64: isolated metadata retries, {summary["complete"]}/2 complete

The original DS16-020/S14 and DS16-035/S27 failures remain immutable in
iteration51/results. Both were `KeyError('bank')` during output serialization:
corrected historical baseline documents omit diagnostic bank metadata. They are
not numerical convergence failures and neither member is excluded.

The separately frozen retry uses the original case document's bank/TLE snapshot
metadata for serialization. Session/input/analysis digests and reconstructed bank
IDs are asserted equal. Numerical baseline, observations, priors, starts, c locks,
regional budgets, score selection and downstream model remain unchanged. New
results and caches are isolated; no original executed source/result is overwritten.

![Cohort distributions](../2026_10_09_position_error_iter51/comparison.png)

| Member | Retry status | Arm | Previous research km | Retry km | RMS Hz | Final converged |
|---|---|---|---:|---:|---:|---|
"""
for row in rows:
    for arm in ("fitted-c", "zero-c"):
        a = row.get("arms", {}).get(arm)
        text += f"| {row['member']['inventory_label']} | {row['retry_status']} | {arm} | "
        if a:
            text += (
                f"{a['previous_error_km']:.6f} | {a['retry_error_km']:.6f} | "
                f"{a['frequency_rms_hz']:.3f} | {a['raw_final_converged']} |\n"
            )
        else:
            text += "— | — | — | — |\n"
text += """
Iteration51 incorporates only completed protocol-bound retries, retaining the
original attempt, retry status and result source. Its full148 membership and
DS16 original48/added15 and DS18 prior-registry24/unmatched10 subgroup counts
remain unchanged. No prior registry match is not evidence of independent
validation. Subgroup means never substitute for full-dataset results.

This corrects result serialization, not an inference model or numerical prior.
Freeze0d13db115. Production, public contracts, fixtures, QNAP and RF collection
remain unchanged. The below1km goal is active and not achieved.
"""
(HERE / "README.md").write_text(text)
print(summary["complete"], "/2")
