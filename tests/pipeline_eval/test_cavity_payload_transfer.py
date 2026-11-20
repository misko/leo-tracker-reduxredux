import pytest

from tools.pipeline_eval.qualification import cavity_payload_transfer as trial
from tools.pipeline_eval.qualification import cavity_payload_transfer_results as results
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.scoring import ARMS


def test_scientific_parity_separates_rf_and_position_from_stage_time():
    original = dict(
        status="ok",
        arms={a: dict(latlon=[10, 20], rf_rms_hz=80) for a in ARMS},
        metrics=dict(stage_s={"cavity": 1.0}, tracks=24),
    )
    elapsed = dict(original, metrics=dict(original["metrics"], stage_s={"cavity": 2.0}))
    assert results.science(original) == results.science(elapsed)
    changed = dict(elapsed, arms=dict(elapsed["arms"], c0=dict(latlon=[10, 20], rf_rms_hz=81)))
    assert results.science(original) != results.science(changed)


def test_package_check_rejects_a_changed_sealed_source(tmp_path):
    def digest(data):
        return trial.prior.INPUTS.cold._sha(data)

    plans = {}
    for name in trial.PACKAGES:
        stage = tmp_path / name
        (stage / "native").mkdir(parents=True)
        for member, payload in (
            ("package.py", name.encode()),
            ("native/manifest.json", b"{}"),
            ("projector.so", b"library"),
        ):
            (stage / member).write_bytes(payload)
        (tmp_path / f"{name}.tar.gz").write_bytes(name.encode())
        plans[name] = dict(
            files={"package.py": digest(name.encode())},
            binaries={"projector.so": digest(b"library")},
            native_manifest_sha256=digest(b"{}"),
            archive_sha256=digest(name.encode()),
        )
    trial.save_json(tmp_path / "plan.json", dict(packages=plans))
    assert trial.bound_packages(tmp_path) == plans
    (tmp_path / "small/package.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source or numerical binary"):
        trial.bound_packages(tmp_path)


def test_transfer_card_preserves_every_package_offer_and_calibration_arm():
    [card] = screening_figures.charts(evidence=trial.REPORT)
    assert len(card.cases) == 4
    for arm in ARMS:
        for series in ("candidate", "stock"):
            subset = [mark for mark in card.page(arm).rows if mark.series == series]
            assert len(subset) == 4
            assert sum(r.dataset == results.CONDITIONS["far-outside"] for r in subset) == 2
