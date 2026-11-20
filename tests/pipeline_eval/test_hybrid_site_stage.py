"""Verify first-party stage data publication against its original image and scores."""

import csv

import pytest

from tools.pipeline_eval.qualification import hybrid_site_stage as stage


def test_stage_publication_preserves_seals_and_honors_probe_denominators(tmp_path):
    counts = dict(
        hybrid=dict(
            winner_hits=340,
            planted_probes=346,
            no_emission_gate_positives=258,
            no_emission_probes=1190,
        ),
        gaussian=dict(
            winner_hits=343,
            planted_probes=346,
            no_emission_gate_positives=0,
            no_emission_probes=1190,
        ),
        **{"donor-only": dict(no_emission_gate_positives=345, no_emission_probes=1536)},
    )
    stage.save_json(
        tmp_path / "scores.json",
        dict(detector=dict(backgrounds={label: dict(counts=c) for label, c in counts.items()})),
    )
    (tmp_path / stage.IMAGE).write_bytes(b"existing first-party PNG digest fixture")
    stage.save_json(
        tmp_path / "score-lock.json",
        dict(files={"scores.json": stage.stock.digest(tmp_path / "scores.json")}),
    )
    stage.save_json(
        tmp_path / "published-evidence.json",
        dict(files={stage.IMAGE: stage.stock.digest(tmp_path / stage.IMAGE)}),
    )
    original = (tmp_path / "score-lock.json").read_bytes()

    stage.publish(tmp_path)

    assert (tmp_path / "score-lock.json").read_bytes() == original
    with (tmp_path / stage.TABLE).open() as text:
        rows = [
            (r["probe_group"], r["background"], int(r["count"]), int(r["receiver_probes"]))
            for r in csv.DictReader(text)
        ]
    assert rows == [
        ("planted", "hybrid", 340, 346),
        ("planted", "gaussian", 343, 346),
        ("dark", "hybrid", 258, 1190),
        ("dark", "gaussian", 0, 1190),
        ("dark", "donor-only", 345, 1536),
    ]
    assert stage.stock.sealed(tmp_path, stage.SEAL)["files"][stage.IMAGE] == stage.stock.digest(
        tmp_path / stage.IMAGE
    )
    (tmp_path / stage.IMAGE).write_bytes(b"different image")
    with pytest.raises(ValueError, match="does not authenticate"):
        stage.publish(tmp_path)
