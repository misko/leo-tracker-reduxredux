import copy
import json

import archive_results
import pytest
import report


def fixture(tmp_path):
    members = [dict(label=f"m{i}", dataset="synthetic") for i in range(12)]
    plan = dict(members=members, sources={}, inputs={})
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    digest = report.sha(tmp_path / "protocol.json")
    folder = tmp_path / "results"
    folder.mkdir()
    block = dict(pairs=1, score_sum=0.5, score_mean=0.5, positive_pairs=1)
    arm = dict(
        pairs=1,
        score_sum=0.5,
        score_mean=0.5,
        positive_pairs=1,
        pair_details=[
            dict(
                first_window_id="a",
                second_window_id="b",
                group=[0, 1, 100, "upper"],
                alternating_block=0,
                score=0.5,
                shared_label_mass=0.7,
            )
        ],
        groups=[
            dict(
                identity=[0, 1, 100, "upper"],
                **block,
                shared_label_mass_sum=0.7,
                alternating_blocks=[block, dict(pairs=0, score_sum=0, score_mean=None)],
            )
        ],
        frequency_nll=10,
        archive_objective_delta=0,
    )
    for member in members:
        identity = dict(label=member["label"], protocol_sha256=digest)
        raw = dict(
            **identity,
            status="complete",
            observations=3,
            total_elapsed_s=2,
            support=dict(
                rows=[dict(window_id=x) for x in "abc"],
                available=2,
                unavailable_reasons={"missing-probe": 1},
            ),
            pairing=dict(
                observations=3,
                pairs=[[0, 1]],
                unpaired=[dict(index=2, reason="missing-support")],
                reason_counts={"missing-support": 1},
            ),
            arms={name: copy.deepcopy(arm) for name in report.ARMS},
        )
        (folder / (member["label"] + ".json")).write_text(json.dumps(raw))
        (folder / (member["label"] + ".claim.json")).write_text(json.dumps(identity))
    return plan


def test_complete_counts_scores_blocks_and_plot(tmp_path):
    fixture(tmp_path)
    plan, receipts, hashes = report.load(tmp_path, tmp_path)
    result = report.summarize(plan, receipts)
    assert len(hashes) == 24
    assert result["totals"]["observations"] == 36
    assert result["totals"]["pairs"] == 12
    assert result["totals"]["unpaired"] == 12
    assert result["totals"]["arms"]["fitted-c"]["score_mean"] == 0.5
    assert result["totals"]["arms"]["zero-c"]["shared_label_mass_sum"] == pytest.approx(8.4)
    assert result["members"][0]["arms"]["fitted-c"]["comparable_block_groups"] == 0
    assert "not estimates of rho" in report.markdown(result)
    report.plot(result, tmp_path / "plot.png")
    assert (tmp_path / "plot.png").stat().st_size > 1000


def test_terminal_failure_keeps_support_and_withholds_totals(tmp_path):
    fixture(tmp_path)
    plan, receipts, _ = report.load(tmp_path, tmp_path)
    receipts["m3"].update(status="failed", error="endpoint mismatch")
    result = report.summarize(plan, receipts)
    assert result["totals"] is None
    assert result["members"][3]["observations"] == 3
    assert "endpoint mismatch" in report.markdown(result)
    with pytest.raises(ValueError, match="full matched"):
        report.plot(result, tmp_path / "absent.png")


def test_missing_terminal_blocks_report_and_archive(tmp_path):
    fixture(tmp_path)
    (tmp_path / "results/m3.json").unlink()
    with pytest.raises(FileNotFoundError):
        report.load(tmp_path, tmp_path)
    with pytest.raises(FileNotFoundError):
        archive_results.create(tmp_path, tmp_path)
    assert not (tmp_path / "results.tar.gz").exists()


def test_foreign_claim_rejected(tmp_path):
    fixture(tmp_path)
    (tmp_path / "results/m3.claim.json").write_text(
        json.dumps(dict(label="m3", protocol_sha256="foreign"))
    )
    with pytest.raises(ValueError, match="foreign"):
        report.load(tmp_path, tmp_path)


def test_pair_reuse_and_cross_arm_changes_rejected(tmp_path):
    fixture(tmp_path)
    plan, receipts, _ = report.load(tmp_path, tmp_path)
    bad = copy.deepcopy(receipts)
    bad["m0"]["pairing"]["unpaired"][0]["index"] = 0
    with pytest.raises(ValueError, match="accounting"):
        report.summarize(plan, bad)
    receipts["m0"]["arms"]["zero-c"]["pair_details"][0]["second_window_id"] = "changed"
    with pytest.raises(ValueError, match="different pairs"):
        report.summarize(plan, receipts)


def test_archive_retains_failed_member_and_hashes(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "results/m3.json"
    raw = json.loads(path.read_text())
    raw.update(status="failed", error="support unavailable")
    path.write_text(json.dumps(raw))
    original = path.read_bytes()
    receipt = archive_results.create(tmp_path, tmp_path)
    assert len(receipt["files"]) == 24
    assert receipt["files"]["results/m3.json"]["sha256"] == report.sha(path)
    assert path.read_bytes() == original
