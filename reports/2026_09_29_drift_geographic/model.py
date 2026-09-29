"""Compose the published correction and conditional contrast location model."""

import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPORTS / "2026_09_29_drift_position"))
sys.path.insert(0, str(REPORTS / "2026_09_29_unassociated_trend"))
from correction import correct_document  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def build(documents, scans, config, factory, arm):
    corrected, receipts = [], []
    for doc in documents:
        changed, receipt = correct_document(doc, scans[doc["session_id"]], arm)
        corrected.append(changed)
        receipts.extend({**r, "session_id": doc["session_id"]} for r in receipt)
    return TrendMixturePosition(corrected, config, factory, 0.2), receipts
