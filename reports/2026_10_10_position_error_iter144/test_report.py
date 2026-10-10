import json

import pytest
from report import load_terminal, markdown, plot, sha, summarize


def rows():
    return [
        dict(
            label=f"DS16-{i:03}",
            status="complete",
            optimizer_calls=0,
            outcome="no-earlier-changed-snapshot",
            arms={},
            admissions={},
        )
        for i in range(12)
    ]


def arm():
    return dict(
        projection=dict(
            total_weighted_energy=10,
            nuisance_energy=2,
            spatial_conditional_energy=3,
            outside_energy=5,
            retained_rows=8,
            original_row_count=12,
            positive_weight_rows=6,
        ),
        original_weight=4,
        omitted_original_weight=1,
        prediction_delta_rms_hz=7,
        original_ids=[1, 2, 3],
        common_valid_ids=[1, 2],
        propagation_filtered_ids=[3],
        visibility_changes=2,
        event_normalizer_nll_delta=None,
        event_normalizer_scope="partial bank",
    )


def test_partial_failure_denominators_and_zero_energy():
    data = rows()
    data[0].update(status="failed", error="second arm failed", arms={"fitted-c": arm()})
    zero = arm()
    zero["projection"].update(
        total_weighted_energy=0, nuisance_energy=0, spatial_conditional_energy=0, outside_energy=0
    )
    zero.update(original_weight=0, omitted_original_weight=0)
    data[1]["arms"] = {"zero-c": zero}
    summary = summarize(data)
    fitted = summary["arms"]["fitted-c"]["entries"][0]
    assert fitted["energy_fractions"] == dict(
        nuisance_energy=0.2, spatial_conditional_energy=0.3, outside_energy=0.5
    )
    assert fitted["omitted_weight_fraction"] == 0.25
    assert summary["arms"]["zero-c"]["entries"][0]["energy_fractions"]["outside_energy"] is None
    assert summary["arms"]["fitted-c"]["unavailable"] == 11
    assert not summary["full_metrics_available"]
    assert not summarize(rows())["full_metrics_available"]
    assert summarize(rows())["terminal_all_complete"]
    assert "second arm failed" in markdown(summary)
    json.dumps(summary, allow_nan=False)


def test_terminal_claim_hash_and_source_gate(tmp_path):
    directory = tmp_path / "report"
    (directory / "results").mkdir(parents=True)
    source = tmp_path / "source"
    source.write_text("frozen")
    protocol = directory / "protocol.json"
    protocol.write_text(
        json.dumps(
            dict(
                members=[dict(label=r["label"]) for r in rows()],
                sources={"source": sha(source)},
                inputs={},
            )
        )
    )
    digest = sha(protocol)
    for row in rows():
        row["protocol_sha256"] = digest
        path = directory / "results" / (row["label"] + ".json")
        path.write_text(json.dumps(row))
        path.with_suffix(".claim.json").write_text(
            json.dumps(dict(label=row["label"], protocol_sha256=digest))
        )
    loaded, integrity = load_terminal(tmp_path, directory)
    assert len(loaded) == 12 and len(integrity["receipts"]) == 24
    target = directory / "results" / (rows()[0]["label"] + ".json")
    snapshot = target.with_suffix(".snapshots.json")
    snapshot.write_text(
        json.dumps(
            dict(label=rows()[0]["label"], protocol_sha256=digest, selection={"wrong": True})
        )
    )
    with pytest.raises(ValueError, match="snapshot"):
        load_terminal(tmp_path, directory)
    snapshot.write_text(
        json.dumps(dict(label=rows()[0]["label"], protocol_sha256=digest, selection=None))
    )
    assert len(load_terminal(tmp_path, directory)[1]["receipts"]) == 25
    broken = json.loads(target.read_text())
    broken["status"] = "pending"
    target.write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="terminal"):
        load_terminal(tmp_path, directory)
    broken.update(status="complete", protocol_sha256="wrong")
    target.write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="Foreign"):
        load_terminal(tmp_path, directory)
    source.write_text("changed")
    with pytest.raises(ValueError, match="binding"):
        load_terminal(tmp_path, directory)


def test_empty_and_partial_plots(tmp_path):
    data = rows()
    for partial in (False, True):
        if partial:
            data[0]["arms"] = {"fitted-c": arm()}
        output = tmp_path / f"plot-{partial}.png"
        plot(summarize(data), output)
        assert output.read_bytes().startswith(b"\x89PNG")


def test_incomplete_or_duplicate_cohort_rejected():
    with pytest.raises(ValueError, match="coverage"):
        summarize(rows()[:-1])
    data = rows()
    data[-1] = data[0]
    with pytest.raises(ValueError, match="coverage"):
        summarize(data)
