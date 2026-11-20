import csv
import json
from hashlib import sha256
from zipfile import ZipFile

from PIL import Image

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import receiver_deadline_benchmark as benchmark
from tools.pipeline_eval.scoring import ARMS


def test_deadline_pack_keeps_failed_position_rows_and_separate_stage_evidence(
    tmp_path, monkeypatch
):
    root = tmp_path / "receiver-deadline"
    position = root / "position"
    stage = root / "measurement"
    position.mkdir(parents=True)
    stage.mkdir()
    digest = sha256(b"recording").hexdigest()
    query = dict(
        id="held",
        recording="held",
        condition="Withheld location",
        truth=[0, 0],
        bindings={"input_sha256": digest},
    )
    cli.save_json(position / "queries.json", {"queries": [query]})
    row = dict(
        id=query["id"],
        method="candidate",
        input_sha256=digest,
        result=dict(status="timed_out", reason="Wall limit", boundary="Fit", metrics={}),
    )
    cli.write(position / "positions.jsonl", cli.encoded(row) + b"\n")
    chart = dict(
        id="candidate",
        method="candidate",
        scope="transfer",
        title="A held fit",
        caption="One held recording.",
        cases="sealed",
        seal="result-lock.json",
        queries="queries.json",
        series=[dict(key="candidate", label="Fit", file="positions.jsonl", value="candidate")],
    )
    cli.save_json(position / "figures.json", dict(version=2, charts=[chart]))
    cli.save_json(
        position / chart["seal"],
        dict(
            cases=[query["id"]],
            files={
                name: benchmark._sha(position / name)
                for name in ("queries.json", "positions.jsonl")
            },
        ),
    )
    measurement = dict(
        version=1,
        id="detector-stage",
        title="Detector measurement",
        sample="One recording",
        boundary="IQ to detector",
        note="One measured service time.",
        seal="stage-lock.json",
        image="stage.png",
        csv="stage.csv",
        profile_image="profile.png",
        profile_csv="profile.csv",
        profile_pdf="profile.pdf",
    )
    Image.new("RGB", (100, 80), "white").save(stage / measurement["image"])
    cli.write(stage / measurement["csv"], b"recording,detector_ms\nheld,10\n")
    profile = Image.new("RGB", (110, 80), "gray")
    profile.save(stage / measurement["profile_image"])
    profile.save(stage / measurement["profile_pdf"])
    cli.write(stage / measurement["profile_csv"], b"recording,profile_ms\nheld,12\n")
    cli.save_json(stage / benchmark.pack.STAGE_SPEC, measurement)
    cli.save_json(
        stage / measurement["seal"],
        dict(
            files={
                measurement[k]: benchmark._sha(stage / measurement[k])
                for k in ("image", "csv", "profile_image", "profile_csv", "profile_pdf")
            }
        ),
    )
    monkeypatch.setattr(benchmark, "SCOPES", (position.name, stage.name))
    monkeypatch.setattr(benchmark, "ROOT", root)
    out = tmp_path / "products"
    assert cli.main(["benchmark", "--receiver", "receiver-deadline", "--out", str(out)]) == 0
    assert not (root / "index.html").exists()
    lock = json.loads((out / "benchmark-lock.json").read_bytes())
    assert (lock["position_comparisons"], lock["stage_charts"], lock["plotted_position_rows"]) == (
        1,
        2,
        2,
    )
    assert all(benchmark._sha(out / name) == digest for name, digest in lock["files"].items())
    with ZipFile(out / benchmark.pack.ZIP) as result:
        scores = list(csv.DictReader(result.read("summary.csv").decode().splitlines()))
        assert [(r["arm"], r["timed_out"], r["median_km"]) for r in scores] == [
            (arm, "1", "") for arm in ARMS
        ]
        assert b"held,10" in result.read("stage-charts/detector-stage.csv")
        assert b"held,12" in result.read("stage-charts/detector-stage-profile.csv")
        positions = list(csv.DictReader(result.read("positions.csv").decode().splitlines()))
        assert {r["figure"] for r in positions} == {chart["id"]}
        assert {r["decision"] for r in positions} == {"timed_out"}
        digests = json.loads(result.read("artifact-sha256.json"))["files"]
        assert all(
            sha256(result.read(name)).hexdigest() == hash_ for name, hash_ in digests.items()
        )
