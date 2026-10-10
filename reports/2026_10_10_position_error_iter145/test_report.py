import json

import pytest
from report import load_terminal, markdown, pairing_counts, plot, sha, summarize


def rows():
    output = []
    for i in range(12):
        value = dict(qualified=True, error_km=1.0, objective=5.0, posterior_rms_hz=100.0)
        output.append(
            dict(
                label=f"DS{16 + i // 4}-{i:03}",
                dataset=f"DS{16 + i // 4}",
                status="complete",
                pairing={},
                attempt_failures={},
                arms={
                    arm: {name: dict(value) for name in ("archive", "control", "rho25")}
                    for arm in ("fitted-c", "zero-c")
                },
            )
        )
    return output


def test_complete_metrics_and_distinct_comparisons():
    data = rows()
    data[0]["arms"]["fitted-c"]["archive"]["error_km"] = 2.0
    data[0]["arms"]["fitted-c"]["rho25"]["error_km"] = 0.5
    summary = summarize(data)
    fitted = summary["full"]["fitted-c"]
    assert fitted["metrics"]["control"]["mean_km"] == 1
    assert fitted["metrics"]["rho25"]["mean_km"] == pytest.approx(11.5 / 12)
    assert fitted["archive_to_control"]["deltas"][0]["delta_km"] == -1
    assert fitted["control_to_correlated"]["deltas"][0]["delta_km"] == -0.5
    assert summary["DS16"]["zero-c"]["metrics"]["control"]["expected"] == 4


def test_failures_withhold_metrics_and_preserve_rows():
    data = rows()
    data[0]["arms"]["zero-c"]["rho25"] = None
    data[0]["attempt_failures"] = {"correlated/zero-c": "crash"}
    payload = dict(members=data, groups=summarize(data))
    metrics = payload["groups"]["full"]["zero-c"]["metrics"]["rho25"]
    assert metrics["qualified"] == 11 and metrics["position_metrics_withheld"]
    assert "mean_km" not in metrics
    assert "crash" in markdown(payload)
    json.dumps(payload, allow_nan=False)


def test_completion_and_hash_gate_before_evaluation(tmp_path):
    source = tmp_path / "source"
    source.write_text("fixed")
    plan = dict(
        members=[dict(label=r["label"]) for r in rows()], sources={"source": sha(source)}, inputs={}
    )
    folder = tmp_path / "results"
    folder.mkdir()
    with pytest.raises(ValueError, match="Not terminal"):
        load_terminal(plan, "protocol", folder, tmp_path)
    for r in rows():
        (folder / (r["label"] + ".json")).write_text(
            json.dumps(dict(label=r["label"], protocol_sha256="protocol", status="complete"))
        )
        (folder / (r["label"] + ".claim.json")).write_text(
            json.dumps(dict(label=r["label"], protocol_sha256="protocol"))
        )
    assert len(load_terminal(plan, "protocol", folder, tmp_path)) == 12
    claim = folder / (rows()[-1]["label"] + ".claim.json")
    valid = claim.read_text()
    claim.write_text(json.dumps(dict(label="foreign", protocol_sha256="protocol")))
    with pytest.raises(ValueError, match="Foreign claim"):
        load_terminal(plan, "protocol", folder, tmp_path)
    claim.write_text(valid)
    source.write_text("changed")
    with pytest.raises(ValueError, match="Frozen"):
        load_terminal(plan, "protocol", folder, tmp_path)


def test_pair_counts_and_partial_plot(tmp_path):
    pairing = dict(
        pairs=[[0, 1]],
        unpaired=[dict(index=2, reason="missing-support")],
        observations=3,
        reason_counts={"missing-support": 1},
    )
    assert pairing_counts(pairing)["paired_rows"] == 2
    pairing["unpaired"].append(dict(index=0, reason="duplicate"))
    with pytest.raises(ValueError, match="repeated"):
        pairing_counts(pairing)
    data = rows()
    data[0]["arms"]["zero-c"]["rho25"] = None
    path = tmp_path / "plot.png"
    plot(data, path)
    assert path.read_bytes().startswith(b"\x89PNG")
