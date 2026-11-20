import json
from collections import Counter

from tools.pipeline_eval.qualification import derivative_receiver_curvature_figures as figures
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.scoring import ARMS, ROLES


def test_curvature_cards_use_original_attempts_with_dedicated_primary_and_forced_rows():
    report = figures.REPORT
    pinned = json.loads((report / "artifact-lock.json").read_bytes())["files"]
    for name, digest in pinned.items():
        figures.sealed(report, name, digest)
    cards = {card.id: card for card in screening_figures.charts(evidence=report)}
    assert len(cards) == 10
    for scope in figures.TITLES:
        original = cards["derivative_receiver-" + scope]
        added = cards[original.id + figures.SUFFIX]
        assert added.method == figures.METHOD
        assert added.cases == original.cases
        assert added.scope == original.scope
        primary, forced = (
            ("one", "one_forced") if added.scope == "roof" else ("candidate", "diagnostic")
        )
        assert added.predictions[primary] == original.predictions["stock"]
        assert "publication" in added.labels[primary]
        assert "forced" in added.labels[forced]
        assert set(added.predictions) == (
            {primary} if scope in ("simulated", "field") else {primary, "stock"}
        )
        for arm in ARMS:
            rows = added.page(arm).rows
            counts = Counter(row.series for row in rows)
            assert counts[primary] == counts[forced] == len(added.cases)
            assert all(row.error_km is None for row in rows if row.series == primary)
            assert all(row.error_km is not None for row in rows if row.series == forced)
            if added.scope == "roof":
                assert all(counts[role] == len(added.cases) for role in ROLES)
