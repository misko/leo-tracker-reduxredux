import gzip

import pytest

from tools.pipeline_eval.__main__ import encoded, save_json
from tools.pipeline_eval.qualification import owner_factor_roof as roof
from tools.pipeline_eval.qualification.screening_figures import charts
from tools.pipeline_eval.scoring import ARMS, ROLES


def evidence(folder, *, upset_alias=False):
    folder.mkdir()
    trials = []
    for case in roof.CASES:
        authority = roof._load_case(case)
        estimates = {}
        for _, _, cells in roof.CARDS:
            for cell in cells:
                shift = 0.005 if upset_alias and cell == "lean_owner_v5_alias" else 0
                estimates[cell] = dict(
                    status="withheld",
                    reason="diagnostic only",
                    boundary=roof.BOUNDARY,
                    metrics={},
                    arms={
                        arm: dict(latlon=None, forced_latlon=[37.91 + shift, -122.54])
                        for arm in ARMS
                    },
                )
        trials.append(
            dict(
                id=case,
                bindings={
                    "native_sha256": authority["native"]["sha256"],
                    "catalog_sha256": authority["catalog"]["sha256"],
                    "observation_sha256": authority["observation"],
                },
                estimates=estimates,
            )
        )
    raw = gzip.compress(b"".join(encoded(row) + b"\n" for row in trials), mtime=0)
    (folder / roof.FILE).write_bytes(raw)
    save_json(folder / roof.SOURCE_LOCK, {"fixture": "roof"})
    save_json(folder / roof.INPUT_LOCK, {"fixture": "frozen"})
    save_json(
        folder / roof.PREDICTION_LOCK,
        dict(
            cases=list(roof.CASES),
            files={roof.FILE: roof._sha(folder / roof.FILE)},
            source_lock_sha256=roof._sha(folder / roof.SOURCE_LOCK),
            input_lock_sha256=roof._sha(folder / roof.INPUT_LOCK),
        ),
    )
    return raw


def test_export_keeps_all_roof_diagnostics_separate_from_publications(tmp_path):
    original, output = tmp_path / "original", tmp_path / "standard"
    raw = evidence(original)
    identifiers = roof.export(original, output)
    assert len(identifiers) == len(set(identifiers)) == 6
    assert (original / roof.FILE).read_bytes() == raw
    for chart in charts(evidence=output):
        assert chart.id in identifiers
        assert chart.labels["one"] == roof.PUBLIC_LABEL
        assert chart.labels["one_forced"].startswith("Forced ·")
        assert len(chart.labels["one_forced"]) <= len(roof.PUBLIC_LABEL)
        for arm in ARMS:
            rows = chart.page(arm).rows
            for role in ROLES:
                assert sum(row.series == role for row in rows) == 4
            offered = [row for row in rows if row.series == "one"]
            forced = [row for row in rows if row.series == "one_forced"]
            assert len(offered) == len(forced) == 4
            assert all(row.decision == "withheld" and row.error_km is None for row in offered)
            assert all(row.decision == "diagnostic" and row.error_km is not None for row in forced)


def test_export_rejects_tampered_fit_and_distinct_alias_outcomes(tmp_path):
    original = tmp_path / "original"
    raw = evidence(original, upset_alias=True)
    with pytest.raises(ValueError, match="distinct alias outcomes"):
        roof.export(original)
    (original / roof.FILE).write_bytes(raw + b"changed")
    with pytest.raises(ValueError, match="prediction seal"):
        roof.export(original)
