from collections import Counter

import pytest

from tools.pipeline_eval.qualification import conditional_support_atlas as atlas
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.scoring import ARMS, ROLES


def test_conditional_support_atlas_preserves_measured_and_forced_decisions(tmp_path):
    expected = (
        "conditional_support_recovery-diagnostic",
        "conditional_support_recovery-confirmation",
        "conditional_support_recovery-omitted",
        "conditional_support_oracle-fixed",
        "conditional_support_oracle-release",
    )
    assert atlas.export(output=tmp_path) == expected
    diagnostic, confirm, omitted, fixed, released = screening_figures.charts(evidence=tmp_path)
    assert tuple(chart.id for chart in (diagnostic, confirm, omitted, fixed, released)) == expected

    def marks(chart, arm):
        return Counter((m.series, m.decision) for m in chart.page(arm).rows)

    for arm in ARMS:
        assert marks(diagnostic, arm)["one", "withheld"] == 2
        assert marks(diagnostic, arm)["one_forced", "diagnostic"] == 2
        assert marks(confirm, arm)["one", "published"] == 2
        assert marks(confirm, arm)["one", "withheld"] == 2
        assert marks(confirm, arm)["stock", "published"] == 2
        assert marks(omitted, arm) == Counter(
            {
                ("candidate", "withheld"): 1,
                ("stock", "withheld"): 1,
                ("one", "withheld"): 1,
                ("diagnostic", "diagnostic"): 1,
                ("stock_forced", "diagnostic"): 1,
                ("one_forced", "diagnostic"): 1,
            }
        )
        omitted_marks = {m.series: m.error_km for m in omitted.page(arm).rows}
        assert omitted_marks["diagnostic"] == omitted_marks["stock_forced"]
        assert omitted_marks["one_forced"] > omitted_marks["diagnostic"]
        for chart in (fixed, released):
            assert marks(chart, arm) == Counter(
                {
                    ("one", "withheld"): 2,
                    ("one_forced", "diagnostic"): 2,
                    **{(role, "published"): 2 for role in ROLES},
                }
            )
        original = {
            m.recording: m.error_km for m in fixed.page(arm).rows if m.series == "one_forced"
        }
        changed = {
            m.recording: m.error_km for m in released.page(arm).rows if m.series == "one_forced"
        }
        assert original.keys() == changed.keys()
        assert all(changed[k] < original[k] for k in original)


def test_conditional_support_atlas_rejects_changed_export(tmp_path):
    atlas.export(output=tmp_path)
    file = tmp_path / atlas.FORCED
    file.write_bytes(file.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="frozen content hash"):
        screening_figures.charts(methods=[atlas.ORACLE], evidence=tmp_path)
