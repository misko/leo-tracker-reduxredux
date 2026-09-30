"""Re-audit correction scope and missing identity support in metadata screen."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_28_signal_clustering/local"


def adjusted(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    q = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty_like(q)
    result[order] = np.minimum(q, 1)
    return result


def main():
    path = SOURCE / "metadata_correlations.csv"
    rows = list(csv.DictReader(path.open()))
    tested = [r for r in rows if r["permutation_p"]]
    corrected = adjusted([float(r["permutation_p"]) for r in tested])
    np.testing.assert_allclose(corrected, [float(r["bh_q"]) for r in tested], atol=1e-12)
    summary_path = SOURCE / "metadata_correlation_summary.json"
    summary = json.loads(summary_path.read_text())
    details_path = SOURCE / "metadata_details.json"
    details = {r["summary"]["signal"]: r["summary"]
               for r in json.loads(details_path.read_text())}
    primary = [details[n] for n in summary["primary_signals"]]
    assert len({r["session"] for r in primary}) == len(primary) == 12
    assert len(tested) == summary["tested_features"] == 18
    associations = []
    for row in rows:
        tested_feature = bool(row["permutation_p"])
        associations.append(dict(
            feature=row["feature"], evidence=row,
            assessment="No BH-supported association in this screen" if tested_feature
            else "Abstention: insufficient labelled sessions; not a negative test",
            primary_support=int(row["primary_sessions"]),
            sensitivity_delta=(float(row["balanced_rho"]) - float(row["rho"]))
            if tested_feature else None))
    result = dict(associations=associations, primary_signals=summary["primary_signals"],
                  minimum_bh_q=float(corrected.min()), tested=len(tested),
                  abstained=len(rows) - len(tested),
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (path, summary_path, details_path)},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Historical selected DS7/DS8 word-family screen; no new "
                  "permutation or RF scan. One representative per session reduces "
                  "pseudoreplication but does not condition on channel/receiver/quality. "
                  "BH covers 18 tested attributes, not the entire investigation. "
                  "Known T-code family distributions are not decoded message fields.")
    (BASE / "local/metadata-receipt-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Features", len(rows), "tested", len(tested), "abstained", len(rows) - len(tested),
          "minimum q", result["minimum_bh_q"])


if __name__ == "__main__":
    main()
