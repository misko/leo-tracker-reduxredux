import hashlib
import json
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.pipeline_eval import corpus
from tools.pipeline_eval.frozen.freeze import freeze

DS26_EIGHT = {
    "DS26-0036",
    "DS26-0070",
    "DS26-0112",
    "DS26-0122",
    "DS26-0203",
    "DS26-0209",
    "DS26-0277",
    "DS26-0311",
}
DS29_EIGHT = {
    "DS29-0082",
    "DS29-0127",
    "DS29-0174",
    "DS29-0247",
    "DS29-0316",
    "DS29-0357",
    "DS29-0519",
    "DS29-0604",
}


@pytest.fixture
def absent_archives(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "bulk"))
    monkeypatch.setenv("PIPELINE_EVAL_BLIND_ROOT", str(tmp_path / "blind"))
    return tmp_path


def test_reference_rosters_and_archived_baseline_without_inputs(absent_archives):
    all_ds26 = list(corpus.references("ds26-all159"))
    common = list(corpus.references("ds26-common127"))
    roof = list(corpus.references("roof16"))
    smoke = list(corpus.references("smoke"))

    assert len(all_ds26) == len({row["id"] for row in all_ds26}) == 159
    assert len(common) == len({row["id"] for row in common}) == 127
    assert {row["id"] for row in roof} == DS26_EIGHT | DS29_EIGHT
    assert [row["id"] for row in smoke] == ["DS26-0036", "DS29-0082"]
    baseline = [row["reference"]["baseline"]["fitted_c"]["error_km"] for row in common]
    assert all(error is not None for error in baseline)
    assert sum(error <= 5 for error in baseline) == 125
    assert max(baseline) == pytest.approx(6.858, abs=0.001)
    assert smoke[0]["reference"]["baseline"]["fitted_c"]["latlon"] == [
        37.85210007037036,
        -122.49896065042755,
    ]
    assert smoke[0]["reference"]["grid_one"]["shape"]["latlon"] is None
    assert smoke[0]["truth"] == [37.849061591561885, -122.48574968092912]
    missing = next(row for row in all_ds26 if row["id"] == "DS26-0172")
    assert missing["reference"]["baseline"]["c0"]["status"] == "missing"
    assert missing["reference"]["grid_one"]["shape"]["status"] == "input_unavailable"


def test_roof_keeps_fixed_tile_and_scores_when_inputs_are_unavailable(absent_archives):
    cache = absent_archives / "cache"
    records = list(corpus.cases("roof16", cache, only={"DS26-0036"}))
    assert len(records) == 1
    case, reference = records[0]
    assert case["id"] == reference["id"] == "DS26-0036"
    assert case["panel"] == "DS26"
    assert case["regions"] == [{"id": "original", "center": [37.906, -122.545]}]
    assert set(case).isdisjoint(
        {"truth", "condition", "reference", "recording", "latlon", "error_km"}
    )
    assert all(
        case[f"{name}_path"] is None
        for name in ("native", "graph", "observation", "catalog", "request")
    )
    assert "missing" in case["input_issues"]["native"]
    assert reference == next(corpus.references("smoke"))
    assert not cache.exists()


def test_excluded_panel_is_the_ordered_complement_even_without_the_raw_corpus(absent_archives):
    from tools.pipeline_eval.__main__ import PANELS, main
    from tools.pipeline_eval.scoring import ROLES

    assert set(PANELS) == {*corpus.PANELS, "transfer16"}
    common = {row["id"] for row in corpus.references("ds26-common127")}
    full = list(corpus.references("ds26-all159"))
    remaining = list(corpus.references("ds26-excluded32"))
    assert remaining == [row for row in full if row["id"] not in common]
    assert len({row["id"] for row in remaining}) == 32
    case, scorer = next(corpus.cases("ds26-excluded32", absent_archives, only={"DS26-0172"}))
    assert case["native_path"] is None and case["input_issues"]
    assert scorer["reference"]["baseline"]["fitted_c"]["status"] == "missing"
    assert main(["baseline", "--panel", "ds26-excluded32", "--out", str(absent_archives)]) == 0
    saved = json.loads(
        (absent_archives / "ds26-excluded32/baseline-distributions.json").read_bytes()
    )
    expected = dict(zip(ROLES, (16, 14, 11, 5), strict=True))
    for arm in ("c0", "fitted_c"):
        rows = {r["method"]: r for r in saved if r["method"] in ROLES and r["arm"] == arm}
        assert {name: r["error_km"]["n"] for name, r in rows.items()} == expected
        assert all(r["attempts"] == 32 for r in rows.values())


def test_transfer_preserves_every_paired_offer_and_opaque_query_id(absent_archives):
    pairs = defaultdict(dict)
    seen = set()
    groups = Counter()
    for case, reference in corpus.cases("transfer124", absent_archives / "cache"):
        assert case["id"] == reference["id"] and case["id"] != reference["recording"]
        assert case["id"] not in seen
        seen.add(case["id"])
        groups[case["panel"]] += 1
        assert set(case).isdisjoint(
            {"truth", "condition", "reference", "recording", "native_sha256", "session_id"}
        )
        assert len(case["regions"]) == 4 and len({region["id"] for region in case["regions"]}) == 4
        key = (reference["group"], reference["recording"])
        pairs[key][reference["condition"]] = case
        assert set(reference["reference"]) == {"grid_four", "grid_forced_four"}
        if reference["condition"] == "missing":
            result = reference["reference"]["grid_four"]["shape"]
            assert result["status"] == "withheld" and result["latlon"] is None
    assert groups == {"DS29": 16, "StarLoc": 22, "Synthetic": 80, "Altrincham": 6}
    assert len(pairs) == 62
    for pair in pairs.values():
        assert set(pair) == {"present", "missing"}
        assert pair["present"]["regions"] != pair["missing"]["regions"]
        assert pair["present"]["catalog_timestamp_ns"] == pair["missing"]["catalog_timestamp_ns"]


def test_portable_transfer_sample_replays_without_external_archives(absent_archives):
    from tools.pipeline_eval.__main__ import references
    from tools.pipeline_eval.frozen.pack_transfer_sample import pack

    _, refs = references("transfer16", None)
    ids = {r["id"] for r in refs}
    inputs = {
        r["id"]: r
        for r in map(json.loads, (corpus.FROZEN / "inputs.jsonl").read_bytes().splitlines())
    }
    cases = list(corpus.cases("transfer124", absent_archives / "cache", only=ids))
    assert {case["id"] for case, _ in cases} == ids
    for case, _ in cases:
        item = inputs[case["id"]]
        for key, folder in [("observation", "observations"), ("catalog", "orbits")]:
            raw_path = Path(case[f"{key}_path"])
            digest = item[key] if isinstance(item[key], str) else item[key]["sha256"]
            assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == raw_path.stem == digest
            external = absent_archives / "blind" / item["blind_tree"] / folder / raw_path.name
            external.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(raw_path, external)
        assert "truth" not in json.loads(Path(case["observation_path"]).read_bytes())
    rebuilt = absent_archives / "rebuilt.zip"
    pack(absent_archives / "blind", rebuilt)
    assert rebuilt.read_bytes() == corpus.TRANSFER_SAMPLE.read_bytes()


def test_corrupt_observation_is_rejected_and_exact_bytes_are_accepted(absent_archives, monkeypatch):
    monkeypatch.setattr(corpus, "TRANSFER_SAMPLE", absent_archives / "no-bundle.zip")
    query = "q-ad4fd8bc0cedbe01fc8f566c"
    digest = "2df7f5ef92f15e705af7b4e1f78b9eda8f8d29356b78c34db938daff6d7faf81"
    path = absent_archives / "blind/public_field2/observations" / f"{digest}.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}\n")
    case, _ = next(corpus.cases("transfer124", absent_archives / "cache", only={query}))
    assert case["observation_path"] is None
    assert "SHA-256" in case["input_issues"]["observation"]

    path.write_bytes(
        b'{"anchor_utc_ns":1678510800000000000,"catalog_timestamp_ns":1678490103000000000,'
        b'"cutoff_utc_ns":1678510800000000000,"duration_s":3600.0,"tracks":[]}\n'
    )
    case, _ = next(corpus.cases("transfer124", absent_archives / "cache", only={query}))
    assert case["observation_path"] == str(path)
    assert "observation" not in case["input_issues"]
    assert "catalog" in case["input_issues"]


def test_bundled_member_must_match_the_frozen_observation_digest(absent_archives, monkeypatch):
    query = "q-ad4fd8bc0cedbe01fc8f566c"
    digest = "2df7f5ef92f15e705af7b4e1f78b9eda8f8d29356b78c34db938daff6d7faf81"
    altered = absent_archives / "transfer-inputs.zip"
    with ZipFile(altered, "w") as archive:
        archive.writestr(digest + ".json", b"{}")
    monkeypatch.setattr(corpus, "TRANSFER_SAMPLE", altered)
    case, _ = next(corpus.cases("transfer124", absent_archives / "cache", only={query}))
    assert case["observation_path"] is None
    assert "SHA-256" in case["input_issues"]["observation"]


def test_reference_rejects_modified_fixture(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    shutil.copytree(corpus.FROZEN, frozen, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(corpus, "FROZEN", frozen)
    with (frozen / "scores.csv").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        list(corpus.references("smoke"))


def test_protected_raw_archive_keeps_frozen_identity_for_read_only_reader(
    absent_archives, monkeypatch
):
    original_open = Path.open
    protected = absent_archives / "bulk/leo/fast-scan-recordings"

    def protect(path, *args, **kwargs):
        if path.is_relative_to(protected):
            raise PermissionError("archive is readable through the dedicated IQ reader")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", protect)
    case, _ = next(corpus.cases("smoke", absent_archives / "cache", only={"DS26-0036"}))
    assert len(case["recording_segments"]) == 14
    first = case["recording_segments"][0]
    assert first["path"] == case["recording_path"]
    assert (
        first["sha256"] == "sha256:73d4a1863312144137a88f3b66bda857277b4a307fbd7d951efcd2cd026ef465"
    )
    assert "delegated" in case["input_issues"]["recording"]


def test_cache_publish_is_concurrent_and_repairs_invalid_bytes(tmp_path):
    raw = b'{"tracks":[]}\n'
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: corpus._store(tmp_path, "observations", raw), range(16)))
    assert len(set(paths)) == 1
    assert paths[0].read_bytes() == raw
    assert list(paths[0].parent.iterdir()) == [paths[0]]
    paths[0].write_bytes(b"interrupted output")
    assert corpus._store(tmp_path, "observations", raw).read_bytes() == raw


def test_freezer_and_cache_reject_qnap_destination_symlinks(tmp_path):
    qnap_link = tmp_path / "qnap"
    qnap_link.symlink_to("/mnt/qnap01", target_is_directory=True)
    with pytest.raises(ValueError, match="outside /mnt/qnap01"):
        freeze(qnap_link / "eval")
    with pytest.raises(ValueError, match="outside /mnt/qnap01"):
        corpus._store(qnap_link / "eval", "requests", b"{}")
    (tmp_path / "scores.csv").symlink_to(qnap_link / "scores.csv")
    with pytest.raises(ValueError, match="outside /mnt/qnap01"):
        freeze(tmp_path)
