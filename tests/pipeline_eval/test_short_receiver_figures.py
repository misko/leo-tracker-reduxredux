import csv
import gzip
import json
import re
import shutil
from collections import Counter
from hashlib import sha256

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import short_receiver_figures as figures
from tools.pipeline_eval.scoring import ARMS, ROLES


def test_study_render_fits_long_titles_inside_the_screenshot(tmp_path, monkeypatch):
    page = figures.Page(
        "omitted",
        "omitted",
        "Staggered RF contrasts with orbit time advanced by 79 seconds",
        "One recorded offer.",
        [figures.Mark("Omitted", "one", "candidate", "withheld", None)],
        "transfer",
    )
    right_edges = []

    def bounds(figure, _):
        heading = next(text for text in figure.texts if text.get_text() == page.title)
        right_edges.append(heading.get_window_extent().x1 / figure.bbox.width)

    monkeypatch.setattr(figures, "save_png", bounds)
    figures.render(tmp_path / "classic", ("c0",), lambda _: [page], title="Classic")
    figures.render(tmp_path / "study", ("c0",), lambda _: [page], title="Study", fit_titles=True)
    assert right_edges[0] > 1
    assert right_edges[1] < 0.99


def _rows(cases, method):
    frozen, inputs = figures._frozen_roof()
    return [
        {
            "id": case,
            "method": method,
            "native_sha256": inputs[case]["native"]["sha256"],
            "catalog_sha256": inputs[case]["catalog"]["sha256"],
            "input_sha256": sha256(case.encode()).hexdigest(),
            "cpu": 3,
            "result": {
                "status": "ok",
                "boundary": "Full paired fit",
                "metrics": {},
                "arms": {arm: {"latlon": frozen[case]["truth"]} for arm in ARMS},
            },
        }
        for case in cases
    ]


def _seal(root, named, cases):
    files = {}
    for name, rows in named.items():
        path = root / name
        data = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
        path.write_bytes(data)
        files[name] = sha256(data).hexdigest()
    (root / "receipt.json").write_bytes(encoded({"files": files, "cases": cases}) + b"\n")


def test_paired_search_books_keep_abstentions_and_only_actual_diagnostics(tmp_path):
    method = "v5_one_seed"
    folder = tmp_path / "search-budget"
    folder.mkdir()
    cases = figures.TIMING
    candidate = _rows(cases, method)
    control = _rows(cases, "orbit_projector")
    candidate[0]["result"]["arms"]["c0"] = {"latlon": None, "forced_latlon": [36, -120]}
    candidate[0]["result"]["arms"]["fitted_c"] = {"latlon": None}
    candidate[0]["result"].update(status="withheld", reason="Held-out validation rejected the fit")
    _seal(folder, {f"{method}.jsonl.gz": candidate, "orbit_projector.jsonl.gz": control}, cases)

    (c0,) = figures.pages("c0", [method], tmp_path)
    (fitted,) = figures.pages("fitted_c", [method], tmp_path)
    assert Counter(r.series for r in c0.rows) == dict.fromkeys(
        (*ROLES, "one", "one_forced", "stock"), 6
    )
    assert Counter(r.series for r in fitted.rows) == dict.fromkeys((*ROLES, "one", "stock"), 6)
    forced = [r for r in c0.rows if r.series == "one_forced" and r.error_km is not None]
    [point] = forced
    (withheld,) = [r for r in c0.rows if r.series == "one" and r.decision == "withheld"]
    assert point.recording == withheld.recording
    assert point.error_km > 100
    assert withheld.error_km is None


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("file", "frozen content hash"),
        ("roster", "prespecified recording roster"),
        ("repeated", "duplicate prediction"),
        ("native", "unmatched native digest"),
        ("cpu", "matched provenance"),
    ],
)
def test_paired_search_rejects_misbound_or_truncated_receipts(tmp_path, change, error):
    method = "v5_first_ranked"
    folder = tmp_path / "search-budget"
    folder.mkdir()
    cases = figures.TIMING
    candidate = _rows(cases, method)
    control = _rows(cases, "orbit_projector")
    if change == "roster":
        candidate.pop()
    elif change == "repeated":
        candidate.append(candidate[0])
    elif change == "native":
        candidate[0]["native_sha256"] = "0" * 64
    elif change == "cpu":
        control[0]["cpu"] = 4
    name = f"{method}.jsonl.gz"
    _seal(folder, {name: candidate, "orbit_projector.jsonl.gz": control}, cases)
    if change == "file":
        path = folder / name
        path.write_bytes(path.read_bytes() + b"unexpected")
    with pytest.raises(ValueError, match=error):
        figures.pages("c0", [method], tmp_path)


@pytest.mark.parametrize("arm", ARMS)
def test_archived_initial_and_prefix_figures_keep_matched_denominators(arm):
    wanted = (figures.INITIAL_RANK, "v5_prefix_180", "v5_prefix_180_raw", "refine_bank")
    initial, prefix, raw, refinement = figures.pages(arm, wanted)
    groups = Counter((row.dataset, row.series) for row in initial.rows)
    assert groups == {
        (dataset, series): count
        for dataset, count in (("DS26", 127), ("DS29", 8))
        for series in (*ROLES, "one", "stock")
    }
    for page, n in ((prefix, 6), (raw, 2), (refinement, 2)):
        assert Counter(r.series for r in page.rows) == dict.fromkeys((*ROLES, "one", "stock"), n)
    assert [r.error_km for r in refinement.rows if r.series == "one"] == [
        r.error_km for r in refinement.rows if r.series == "stock"
    ]


@pytest.mark.parametrize("arm", ARMS)
def test_published_six_case_runtime_controls_share_the_candidate_recordings(arm):
    for page in figures.pages(arm, figures.SEARCH_BUDGET):
        assert Counter((r.dataset, r.series) for r in page.rows) == {
            (dataset, series): 3
            for dataset in ("DS26", "DS29")
            for series in (*ROLES, "one", "stock")
        }
        assert all(r.decision == "published" for r in page.rows if r.series in {"one", "stock"})


def test_broad_roof_keeps_the_full_roster_and_the_preselected_replay_subset(tmp_path):
    cases = list(figures._frozen_roof()[0])
    previous = figures.REPORT / "search-budget/initial-checkpoints"
    shutil.copytree(previous, tmp_path / "search-budget/initial-checkpoints")
    folder = tmp_path / "search-budget/broad"
    folder.mkdir()
    difference = []
    with gzip.open(previous / "v5_initial_best3.jsonl.gz", "rt") as stream:
        for row in map(json.loads, stream):
            if row["result"]["metrics"]["winning_rank"] != 0:
                difference.append(row["id"])
    fresh_controls = ("DS26-0201", "DS26-0062", "DS26-0006")
    replayed = {*difference, *figures.TIMING, *fresh_controls}
    candidate = _rows(cases, figures.BROAD_RANK)
    control = _rows(cases, "orbit_projector")
    for row in control:
        row["source"] = "archived_projector"
    for row in candidate:
        if row["id"] in figures.TIMING:
            row["source"] = "six_pair_replay"
        elif row["id"] in replayed:
            row["source"] = "broad_fresh"
        else:
            row["source"] = "unmeasured_agreement"
            row["result"] = {
                "status": "missing",
                "boundary": "Full fit would require a replay",
                "reason": "No replay was scheduled for this agreement",
                "metrics": {"position_attempted": False},
            }
    name = f"{figures.BROAD_RANK}.jsonl.gz"
    _seal(folder, {name: candidate, "orbit_projector.jsonl.gz": control}, cases)

    overall, paired = figures.pages("c0", [figures.BROAD_RANK], tmp_path)
    all_candidates = [r for r in overall.rows if r.series == "one"]
    assert len(all_candidates) == 135
    assert sum(r.decision == "missing" and r.error_km is None for r in all_candidates) == 96
    assert Counter(r.series for r in paired.rows) == dict.fromkeys((*ROLES, "one", "stock"), 39)
    row = next(r for r in candidate if r["source"] == "unmeasured_agreement")
    row["result"]["arms"] = {arm: {"latlon": None, "forced_latlon": [37, -122]} for arm in ARMS}
    _seal(folder, {name: candidate, "orbit_projector.jsonl.gz": control}, cases)
    with pytest.raises(ValueError, match="misstates the replay decision"):
        figures.pages("c0", [figures.BROAD_RANK], tmp_path)


@pytest.mark.parametrize("arm", ARMS)
def test_published_broad_roof_receipts_account_for_every_recording(arm):
    scheduled, replayed = figures.pages(arm, [figures.BROAD_RANK])
    assert Counter((r.dataset, r.decision) for r in scheduled.rows if r.series == "one") == {
        ("DS26", "published"): 35,
        ("DS26", "missing"): 92,
        ("DS29", "published"): 4,
        ("DS29", "missing"): 4,
    }
    assert Counter((r.dataset, r.series) for r in replayed.rows) == {
        (dataset, series): count
        for dataset, count in (("DS26", 35), ("DS29", 4))
        for series in (*ROLES, "one", "stock")
    }


@pytest.mark.parametrize("arm", ARMS)
def test_geographic_transfer_panels_preserve_false_fixes_and_negative_cases(arm):
    wanted = ("joint_pass_id", "robust_em", figures.FIELD_METHOD, "pass_geometry")
    pages = {p.name: p for p in figures.pages(arm, wanted)}
    for method, n in (("joint_pass_id", 3), ("robust_em", 1)):
        wrong = pages[f"{method}-wrong-region"]
        assert wrong.scope == "transfer"
        omitted = [r for r in wrong.rows if r.dataset == "Correct roof region omitted"]
        assert Counter(r.series for r in omitted) == {"candidate": n, "diagnostic": n}
        assert all(r.error_km is None for r in omitted if r.series == "candidate")
    actual = pages[figures.FIELD_METHOD]
    assert set(r.series for r in actual.rows) == {"candidate", "diagnostic"}
    assert Counter(r.dataset for r in actual.rows if r.series == "candidate") == {
        "Global search": 4,
        "Correct tile supplied": 4,
        "Correct region omitted": 4,
    }
    (worldwide,) = [r for r in actual.rows if r.series == "candidate" and r.decision == "published"]
    assert worldwide.dataset == "Global search"
    assert worldwide.error_km > 9_000
    for method, publications in (("joint_pass_id", int(arm == "fitted_c")), ("pass_geometry", 2)):
        page = pages[f"{method}-fresh-scenes"]
        rows = [r for r in page.rows if r.series == "candidate"]
        assert Counter(r.dataset for r in rows) == {
            "Correct synthetic tile": 4,
            "Correct synthetic region omitted": 4,
            "Shuffled detections · no site": 1,
        }
        assert sum(r.error_km is not None for r in rows if "omitted" in r.dataset) == publications
        assert next(r for r in rows if "Shuffled" in r.dataset).error_km is None


@pytest.mark.parametrize("arm", ARMS)
def test_raw_robust_keeps_fresh_and_stored_detector_cohorts_separate(arm):
    fresh, stored = figures.pages(arm, [figures.RAW_ROBUST])
    assert fresh.name == "raw_robust-fresh"
    assert stored.name == "raw_robust-stored"
    seen = set()
    for page, n in ((fresh, 2), (stored, 4)):
        track_kinds = (*ROLES, "one", "one_forced", "stock", "all_visits")
        assert Counter(r.series for r in page.rows) == dict.fromkeys(track_kinds, n)
        assert all(r.error_km is not None for r in page.rows if r.series == "one_forced")
        cases = {r.recording for r in page.rows}
        assert len(cases) == n and seen.isdisjoint(cases)
        seen.update(cases)


@pytest.mark.parametrize("arm", ARMS)
def test_shared_search_keeps_the_original_failure_and_separate_confirmation(arm):
    original, followup = figures.pages(arm, [figures.SHARED_SEARCH])
    assert Counter(r.series for r in original.rows) == dict.fromkeys((*ROLES, "one", "stock"), 4)
    (timeout,) = [r for r in original.rows if r.decision == "timed_out"]
    assert timeout.series == "one" and timeout.error_km is None
    controls = {r.recording: r.error_km for r in original.rows if r.series == "stock"}
    assert all(
        r.error_km == controls[r.recording]
        for r in original.rows
        if r.series == "one" and r.decision == "published"
    )
    assert controls[timeout.recording] is not None
    assert followup.name == "v5_shared_search-followup"
    assert Counter(r.series for r in followup.rows) == dict.fromkeys((*ROLES, "one", "stock"), 1)
    assert {r.recording for r in followup.rows} == {timeout.recording}
    (stock,) = [r for r in followup.rows if r.series == "stock"]
    (candidate,) = [r for r in followup.rows if r.series == "one"]
    assert candidate.decision == "published"
    assert candidate.error_km == stock.error_km == controls[stock.recording]


def test_failed_shared_search_confirmation_keeps_its_own_row_and_validates_input(tmp_path):
    source = figures.REPORT / "shared-search"
    folder = tmp_path / "shared-search"
    folder.mkdir()
    for name in figures.SHARED_ORIGINAL:
        shutil.copyfile(source / name, folder / name)
    with gzip.open(source / "original-positions.jsonl.gz", "rt") as stream:
        receipt = next(
            r for r in map(json.loads, stream) if r["id"] == figures.SHARED_DEADLINE_CASE
        )
    receipt["qualification"] = "standalone_corroboration"
    receipt["result"].update(reason="Standalone worker reached its own deadline")
    name = "followup-position.jsonl.gz"
    lock = folder / "followup-receipt.json"

    def write_followup():
        _seal(folder, {name: [receipt]}, (receipt["id"],))
        (folder / "receipt.json").replace(lock)

    write_followup()
    original, followup = figures.pages("c0", [figures.SHARED_SEARCH], tmp_path)
    assert sum(r.decision == "timed_out" for r in original.rows) == 1
    (candidate,) = [r for r in followup.rows if r.series == "one"]
    assert candidate.decision == "timed_out" and candidate.error_km is None
    receipt["input_sha256"] = "0" * 64
    write_followup()
    with pytest.raises(ValueError, match="matched provenance"):
        figures.pages("c0", [figures.SHARED_SEARCH], tmp_path)


def test_generate_named_figures_keeps_roof_and_transfer_books_separate(tmp_path):
    manifest = figures.generate(tmp_path, ("c0",), ("v5_prefix_180_raw", figures.FIELD_METHOD))
    assert manifest == json.loads((tmp_path / "manifest.json").read_bytes())
    assert {row["scope"] for row in manifest} == {"roof", "transfer"}
    assert len(manifest) == 2
    for entry in manifest:
        assert entry["arm"] == "c0"
        assert (tmp_path / entry["image"]).read_bytes().startswith(b"\x89PNG")
        assert len(re.findall(rb"/Type /Page\b", (tmp_path / entry["pdf"]).read_bytes())) == 1
        with (tmp_path / entry["csv"]).open() as stream:
            rows = list(csv.DictReader(stream))
        assert set(r["figure"] for r in rows) == {entry["id"]}
    assert "fitted_c/" not in (tmp_path / "README.md").read_text()
