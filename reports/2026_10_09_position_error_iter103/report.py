"""Persisted direct-chain reporting; no optimizer or objective evaluations."""

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_09_position_error_iter98"
SPEC = importlib.util.spec_from_file_location("matched98_report_for103", PREVIOUS / "report.py")
matched = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matched)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    # Reuse only persisted-fit evaluation/reporting, not the numerical driver.
    matched.HERE = HERE
    matched.main()
    fresh = json.loads((HERE / "fresh-calibration.json").read_text())
    plan_digest = sha(HERE / "protocol.json")
    assert fresh["protocol_sha256"] == plan_digest
    attempt = fresh["attempt"]
    direct = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter102/result.json").read_text()
    )["attempts"]["calibration-prefit"]
    summary = json.loads((HERE / "summary.json").read_text())
    old = json.loads((PREVIOUS / "summary.json").read_text())
    comparison = []
    for row in summary["comparison"]:
        prior = next(r for r in old["comparison"] if r["arm"] == row["arm"])
        comparison.append(
            dict(
                arm=row["arm"],
                research98_error_km=prior["candidate"]["error_km"],
                direct103_error_km=row["candidate"]["error_km"] if row["candidate"] else None,
                same_consumed_scan=True,
            )
        )
    qualification = attempt.get("qualification")
    cost = dict(
        prefit_polish_evaluations=direct["objective_evaluations"],
        prefit_polish_elapsed_s=direct["polish_elapsed_s"],
        fresh_calibration_elapsed_s=attempt["elapsed_s"],
        bounded_postfit_elapsed_s=attempt.get("bounded_postfit_elapsed_s"),
        bounded_postfit_evaluations=attempt["postfit"]["evaluations"],
        bounded_postfit_stationarity=attempt["postfit"]["stationarity"],
        postfit_polish_evaluations=qualification["objective_evaluations"] if qualification else 0,
        postfit_polish_elapsed_s=qualification["polish_elapsed_s"] if qualification else 0,
        validated_postfit_stationarity=attempt["calibration"]["postfit"]["stationarity"]
        if attempt["calibration"]
        else None,
    )
    summary.update(
        direct_calibration_cost=cost,
        comparison_to_research98=comparison,
        reporting_source_sha256={"iteration98/report.py": sha(PREVIOUS / "report.py")},
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    original = (HERE / "RESULTS.md").read_text()
    original = original.replace(
        "[result.json](result.json)", "[compressed raw receipts](receipts.tar.gz)"
    )
    lead = [
        "# Direct calibration path and matched c continuation",
        "",
        "This run starts from iteration102's directly qualified ordinary prefit, builds a",
        "fresh receiver correction, fits its corrected postfit and uses direct qualification",
        "only if needed. It does not reuse iteration96's correction or iteration99's",
        "intermediate tangent states. The source prefit and both follow-on arms remain",
        "conditional on this consumed ordinary score-selected scan, not unseen validation.",
        "",
        "## Calibration cost",
        "",
        "| Component | Evaluations | Elapsed s |",
        "|---|---:|---:|",
    ]
    lead += [
        f"| Direct prefit polish (102) | {cost['prefit_polish_evaluations']} | "
        f"{cost['prefit_polish_elapsed_s']:.4f} |",
        f"| Fresh bounded postfit | {cost['bounded_postfit_evaluations']} | "
        f"{cost['bounded_postfit_elapsed_s']:.4f} |",
        f"| Direct postfit polish | {cost['postfit_polish_evaluations']} | "
        f"{cost['postfit_polish_elapsed_s']:.4f} |",
        "",
        f"Fresh correction/postfit/validation together took {attempt['elapsed_s']:.4f}s.",
        "This excludes bank/input reconstruction and downstream association/B7 costs.",
        "The prefit polish occurred in the prior frozen102 run; it is included for algorithm",
        "cost accounting, not represented as a new103 fit.",
        "",
        "## Comparison with the earlier research chain",
        "",
        "| Arm | Research98 error km | Direct103 error km |",
        "|---|---:|---:|",
    ]
    for row in comparison:
        lead.append(
            f"| {row['arm']} | {row['research98_error_km']:.6f} | {row['direct103_error_km']:.6f} |"
        )
    lead += [
        "",
        "Both are the same consumed scan. Their difference does not constitute independent",
        "validation or a new matched algorithm population. Use the ordinary-only replay below",
        "as the controlled B7 baseline. No frozen prior receipt is modified.",
        "",
    ]
    lead += [
        "The score-selected final errors are stable, but nonwinning zero-timing starts are",
        "sensitive to the directly rebuilt calibration:",
        "",
        "| Arm | Research98 zero-timing error km | Direct103 zero-timing error km |",
        "|---|---:|---:|",
    ]
    for arm in matched.ARMS:
        before = next(
            r["fit"]["error_km"]
            for r in old["recovered_finals"]
            if r["arm"] == arm and r["start"] == "zero-timing"
        )
        after = next(
            r["fit"]["error_km"]
            for r in summary["recovered_finals"]
            if r["arm"] == arm and r["start"] == "zero-timing"
        )
        lead.append(f"| {arm} | {before:.6f} | {after:.6f} |")
    lead += [
        "",
        "These starts remain qualified but have worse same-model scores than the association",
        "starts. This is observed start sensitivity, not a reason to tune using reference errors",
        "or to substitute a different operational winner.",
        "",
    ]
    archive_note = """
## Compressed raw receipts

[receipts.tar.gz](receipts.tar.gz) contains result.json, fresh-calibration.json and
every stages/*.json receipt. [receipts-manifest.json](receipts-manifest.json) records
per-file hashes/sizes and the archive hash. Deterministic archive creation and
readback verification preserved every original local raw file.
Individual raw JSON receipts are omitted from the published directory; unpack the
archive to inspect or reproduce them. Summary tables remain directly readable.

Restore into a **new, nonexistent directory**, without overwriting existing work:

```bash
python reports/2026_10_09_position_error_iter103/unpack_receipts.py /tmp/ac11-103-receipts
```

The verifier checks the archive hash, exact controlled membership, regular files,
relative paths, per-file sizes and hashes before creating the destination. It does
not use unrestricted tar extraction. Copy verified receipts into a separate checkout
of the frozen protocol if reproducing reports; do not replace existing local receipts.
The reporting helper also needs the published iteration98 report.py/summary.json
and original iteration93 document. Archive extraction itself runs no analysis.
"""
    (HERE / "RESULTS.md").write_text("\n".join(lead) + "\n" + original + archive_note)
    names = [
        "report.py",
        "RESULTS.md",
        "summary.json",
        "comparison.png",
        "protocol.json",
        "result.json",
        "fresh-calibration.json",
        "archive_receipts.py",
        "unpack_receipts.py",
        "receipts.tar.gz",
        "receipts-manifest.json",
    ]
    (HERE / "report-integrity.json").write_text(
        json.dumps({n: sha(HERE / n) for n in names}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
