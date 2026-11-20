import csv
import gzip
import hashlib
import json
import re
from collections import Counter

import numpy as np
import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval import figure_books as books
from tools.pipeline_eval import position_figure
from tools.pipeline_eval.position_figure import Mark, cohort_title, cumulative, marks
from tools.pipeline_eval.qualification import pilot_positions, roof_replays, transfer_figures
from tools.pipeline_eval.qualification.prefix_figures import TIMING_IDS
from tools.pipeline_eval.reference import waveform
from tools.pipeline_eval.scoring import ROLES, distance_km


def test_long_chart_labels_fit_each_column_and_the_entire_legend_is_visible():
    rows = [
        Mark(dataset, dataset + "-sample", series, "published", 1.0)
        for dataset in ("DS26", "DS29")
        for series in (*ROLES, "one", "stock")
    ]
    labels = {
        "one": "Five-refresh compact v5, ordinary detector factors",
        "stock": "Five-refresh compact v5, capture-era detector factors",
    }
    fig = position_figure.draw(rows, "input_factor_comparison", "c0", "", series_labels=labels)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        previous_right = 0
        for ax in fig.axes[-2:]:
            assert min(t.get_window_extent(renderer).x0 for t in ax.get_yticklabels()) >= (
                previous_right + 4
            )
            previous_right = ax.bbox.x1
        assert fig.legends[0].get_window_extent(renderer).x1 < fig.bbox.width
    finally:
        position_figure.plt.close(fig)


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_published_gallery_keeps_measured_cohorts_and_both_region_offers(arm):
    names = [m for m in (*books.TEN, *books.EXTENDED) if m not in books.FRONTEND]
    pages = books.published_pages(arm, names)
    pages.insert(len(books.TEN), books._complete_recordings(arm))
    names.insert(len(books.TEN), "native-to-v5")
    assert [p.name for p in pages] == names
    folder = books.STREAMING_REPORT / "figures" / arm
    pdf = (folder / "modifications.pdf").read_bytes()
    assert len(re.findall(rb"/Type /Page\b", pdf)) == len(pages)
    expected_images = [page.name + ".png" for page in pages]
    gallery = (folder / "README.md").read_text()
    assert re.findall(r"!\[[^\]]+\]\(([^)]+)\)", gallery) == expected_images
    for filename in expected_images:
        with (folder / filename).open("rb") as image:
            assert image.read(8) == b"\x89PNG\r\n\x1a\n"
    with (folder / "modifications.csv").open() as stream:
        saved = list(csv.DictReader(stream))
    assert [
        (
            r["figure"],
            r["arm"],
            r["dataset"],
            r["recording"],
            r["series"],
            r["decision"],
            float(r["error_km"]) if r["error_km"] else None,
        )
        for r in saved
    ] == [
        (p.name, arm, m.dataset, m.recording, m.series, m.decision, m.error_km)
        for p in pages
        for m in p.rows
    ]
    for page in pages:
        expected = {"DS26": 127, "DS29": 8}
        if page.name in (
            "native-to-v5",
            "anchor_receiver",
            "catalogue_checksum",
            "pilot_kernel",
            "native_geometry",
        ):
            expected = {"DS26": 1, "DS29": 1}
        elif page.name in ("v5_core", "sweep_schedule", *books.CHANNELS):
            expected = {"DS26": 3, "DS29": 3}
        elif page.name == "compact_finish":
            expected = {"DS26": 3, "DS29": 1}
        elif page.name.startswith("early_"):
            expected = {"DS26": 8}
        rows = {(r.dataset, r.recording) for r in page.rows if r.series == "baseline"}
        assert Counter(d for d, _ in rows) == expected
        for series in {r.series for r in page.rows}:
            assert {(r.dataset, r.recording) for r in page.rows if r.series == series} == rows
        if page.name in ("shared_doppler", "arc_validation"):
            assert {"one", "four", "four_forced"} <= {r.series for r in page.rows}
        if page.name == "native_geometry":
            assert {r.decision for r in page.rows if r.series == "one"} == {"stage_only"}
        if page.name == "anchor_receiver":
            assert all(r.decision == "published" for r in page.rows if r.series == "one")
            baseline = {r.recording: r.error_km for r in page.rows if r.series == "baseline"}
            for r in page.rows:
                if r.series == "one":
                    assert r.error_km == pytest.approx(baseline[r.recording], abs=1e-6)


@pytest.fixture
def measured_frontend(tmp_path):
    refs = {r["id"]: r for r in books._common_roof()}
    smoke = {r["id"] for r in cli.references("smoke", None)[1]}
    files = {
        "native-to-v5": "ordinary/positions.jsonl.gz",
        "native_winner": "winner/positions.jsonl.gz",
        "single_rx0": "single/full-positions.jsonl.gz",
        "single_rx0_factors": "single/archive-positions.jsonl.gz",
        "pilot_confirmation": "confirmation/positions.jsonl.gz",
        "spectral_grid": "spectral/positions.jsonl.gz",
    }

    def save(filename, records):
        path = tmp_path / filename
        cli.write(path, gzip.compress(b"".join(cli.encoded(item) + b"\n" for item in records)))

    for method, filename in files.items():
        cases = TIMING_IDS if method in ("native-to-v5", "native_winner") else sorted(smoke)
        records = []
        for case in cases:
            point = refs[case]["truth"]
            record = dict(id=case, method=method, **position(point))
            if method == "single_rx0":
                record["variant"] = "fresh-native-rx0"
            elif method == "single_rx0_factors":
                record["variant"] = "capture-era-rx0"
            elif method == "pilot_confirmation":
                record.update(position(status="withheld"))
                record["result"]["metrics"]["position_attempted"] = False
            elif method == "spectral_grid":
                record["result"] = dict(status="ok", boundary="coarse pilot search", metrics={})
            records.append(record)
        save(filename, records)
    ordinary = [
        dict(
            id=case,
            variant="ordinary-native-rx0",
            **position([refs[case]["truth"][0] + 0.02, refs[case]["truth"][1]]),
        )
        for case in sorted(smoke)
    ]
    ordinary[0]["result"]["arms"]["fitted_c"] = {"latlon": refs[ordinary[0]["id"]]["truth"]}
    save("single/ordinary-factor-positions.jsonl.gz", ordinary)
    return tmp_path, smoke, list(files)


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_frontend_gallery_keeps_boundaries_and_separate_rx0_sources(measured_frontend, arm):
    directory, smoke, methods = measured_frontend
    pages = books.published_pages(arm, methods, evidence=directory)
    assert [p.method for p in pages] == methods
    for page in pages:
        e = set(TIMING_IDS) if page.method in ("native-to-v5", "native_winner") else smoke
        roles = {*ROLES, "one"}
        if page.method == "single_rx0_factors":
            roles.add("one_native_factors")
        assert {(m.series, m.recording) for m in page.rows} == {(m, r) for m in roles for r in e}
        if page.method in ("pilot_confirmation", "spectral_grid"):
            unmeasured = [m for m in page.rows if m.series == "one"]
            assert all(m.decision == "stage_only" and m.error_km is None for m in unmeasured)
        if page.method == "single_rx0_factors":
            assert all(m.error_km == 0 for m in page.rows if m.series == "one")
            native = [m for m in page.rows if m.series == "one_native_factors"]
            assert len(native) == 2
            assert sum(m.error_km > 2 for m in native) == (2 if arm == "c0" else 1)


def test_frontend_gallery_requires_complete_and_distinct_saved_sources(measured_frontend):
    directory, _, _ = measured_frontend
    filename = directory / "single/ordinary-factor-positions.jsonl.gz"
    records = list(cli.read_predictions(filename).values())
    raw = b"".join(cli.encoded(item) + b"\n" for item in records[:1])
    cli.write(filename, gzip.compress(raw))
    with pytest.raises(ValueError, match="requested recording roster"):
        books.published_pages("fitted_c", ["single_rx0_factors"], evidence=directory)
    records[0]["variant"] = "capture-era-rx0"
    raw = b"".join(cli.encoded(item) + b"\n" for item in records)
    cli.write(filename, gzip.compress(raw))
    with pytest.raises(ValueError, match="ordinary-native-rx0"):
        books.published_pages("fitted_c", ["single_rx0_factors"], evidence=directory)


def test_frontend_gallery_cli_labels_both_factor_series_and_unmeasured_cases(
    measured_frontend, tmp_path
):
    directory, _, _ = measured_frontend
    selected = ["single_rx0_factors", "pilot_confirmation"]
    out = tmp_path / "output"
    assert (
        cli.main(
            [
                "figures",
                "--arm",
                "c0",
                "--evidence",
                str(directory),
                "--out",
                str(out),
                "--variant",
                selected[0],
                "--variant",
                selected[1],
            ]
        )
        == 0
    )
    index = (out / "README.md").read_text()
    for label in (*books.RX0_FACTOR_LABELS.values(), "Unmeasured"):
        assert label in index
    assert "did not advance to position fitting" in (out / "c0/README.md").read_text()
    pdf = (out / "c0/modifications.pdf").read_bytes()
    assert len(re.findall(rb"/Type /Page\b", pdf)) == len(selected)


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_off_region_roof_uses_only_the_eight_sealed_four_region_queries(arm):
    expected = {
        "DS29-0082": "fe569d790afd03ceb19c68f0b63ef211",
        "DS29-0127": "3d8e04c2558a7e7e4611a69ef9a74553",
        "DS29-0174": "750094261478aa077633a1bdc5d54278",
        "DS29-0247": "18f88b6cbb8cb431196ba3004717d9ca",
        "DS29-0316": "88f9a9722925ced68957ddb261ffaeb3",
        "DS29-0357": "79c70b008fa53f59e7966ceddac45a4f",
        "DS29-0519": "57035950bf8e55f72a9abdb88a0a970d",
        "DS29-0604": "267df7a2df16dbdba6dc77aa89dd8cfc",
    }
    path = books.FRONTEND_REPORT / "regions/predictions.jsonl.gz"
    sealed = transfer_figures._longitude_evidence(path)["transfer124"]
    (page,) = books.published_pages(arm, ["off_region_test"])
    roles = (*ROLES, "four", "four_forced")
    marks_by_key = {(m.recording, m.series): m for m in page.rows}
    assert len(page.rows) == len(marks_by_key) == 48
    assert marks_by_key.keys() == {(case, role) for case in expected for role in roles}
    assert {m.dataset for m in page.rows} == {"DS29"}
    assert "eight DS29 blind-panel recordings" in page.subtitle
    assert "single-region" in page.subtitle
    assert sum(m.decision == "published" for m in page.rows if m.series == "four") == 7
    assert sum(m.decision == "diagnostic" for m in page.rows if m.series == "four_forced") == 8
    assert marks_by_key["DS29-0519", "four"].decision == "withheld"
    assert marks_by_key["DS29-0519", "four"].error_km is None
    for ref in cli.references("roof16", list(expected))[1]:
        recording = ref["recording"]
        arms = sealed[expected[recording]]["results"]["off_region_test"]["arms"]
        for role, endpoint in (("four", "latlon"), ("four_forced", "forced_latlon")):
            assert marks_by_key[recording, role].error_km == distance_km(
                arms[arm][endpoint], ref["truth"]
            )
        for role in ROLES:
            assert marks_by_key[recording, role].error_km == ref["reference"][role][arm]["error_km"]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("id", "frozen transfer query IDs"),
        ("observation_sha256", "observation digest differs"),
        ("catalog_sha256", "catalog digest differs"),
        ("tile", "four-region offers differ"),
    ],
)
def test_off_region_roof_rejects_unmatched_query_bindings(monkeypatch, field, message):
    path = books.FRONTEND_REPORT / "regions/predictions.jsonl.gz"
    evidence = transfer_figures._longitude_evidence(path)
    records = evidence["transfer124"]
    case = "fe569d790afd03ceb19c68f0b63ef211"
    if field == "id":
        records["another query"] = records.pop(case)
    elif field == "tile":
        scores = records[case]["results"]["off_region_test"]["metrics"]["regional_scores"]
        scores["another tile"] = scores.pop(next(iter(scores)))
    else:
        records[case][field] = "0" * 64
    monkeypatch.setattr(transfer_figures, "_longitude_evidence", lambda _: evidence)
    with pytest.raises(ValueError, match=message):
        books.published_pages("c0", ["off_region_test"])


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_frontend_milestone_keeps_all_44_saved_pages(arm):
    pages = books.published_pages(arm, list(books.FRONTEND_METHODS))
    folder = books.FRONTEND_REPORT / "figures" / arm
    image_names = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", (folder / "README.md").read_text())
    assert len(pages) == len(image_names) == 44
    assert image_names == [page.name + ".png" for page in pages]
    assert len(re.findall(rb"/Type /Page\b", (folder / "modifications.pdf").read_bytes())) == 44
    with (folder / "modifications.csv").open() as stream:
        saved = list(csv.DictReader(stream))
    assert [
        (r["figure"], r["recording"], r["series"], r["decision"], r["error_km"]) for r in saved
    ] == [
        (
            page.name,
            row.recording,
            row.series,
            row.decision,
            "" if row.error_km is None else str(row.error_km),
        )
        for page in pages
        for row in page.rows
    ]


@pytest.fixture
def cold_start_receipts(tmp_path):
    def store(path, rows):
        cli.write(path, gzip.compress(b"".join(cli.encoded(row) + b"\n" for row in rows)))

    _, hashes = books.corpus._selection("roof16")
    inputs = books.corpus._index(books.corpus._read_frozen("inputs.jsonl", hashes))
    refs = {r["id"]: r for r in books._common_roof()}
    for method, folder, roster in (
        ("point_votes", "point-votes", TIMING_IDS),
        ("rate_triplets", "rate-triplets", TIMING_IDS),
        ("folded_doppler", "folded-doppler", ("DS26-0036", "DS29-0082")),
    ):
        for mode in ("global", "matched-tile"):
            rows = []
            for case in roster:
                row = dict(
                    id=case,
                    method=method,
                    mode=mode,
                    native_sha256=inputs[case]["native"]["sha256"],
                    catalog_sha256=inputs[case]["catalog"]["sha256"],
                    **position(refs[case]["truth"]),
                )
                if mode == "global" and case == "DS26-0036":
                    row.update(position(status="withheld", forced_latlon=[0, 0]))
                elif mode == "global" and case == "DS26-0122":
                    row["result"] = dict(
                        status="timed_out", reason="deadline", boundary="worker", metrics={}
                    )
                elif mode == "matched-tile" and case == "DS26-0237":
                    row.update(position(status="withheld", forced_latlon=refs[case]["truth"]))
                rows.append(row)
            store(tmp_path / folder / f"{mode}.jsonl.gz", rows)
    return tmp_path, store


def test_cold_start_keeps_exact_rosters_and_saves_only_measured_diagnostics(cold_start_receipts):
    directory, _ = cold_start_receipts
    pages = books.published_pages(
        "c0", ["point_votes", "rate_triplets", "folded_doppler"], evidence=directory
    )
    for page in pages:
        roster = TIMING_IDS if page.name != "folded_doppler" else ("DS26-0036", "DS29-0082")
        series = (*ROLES, "global", "global_forced", "one", "one_forced")
        rows = {(m.recording, m.series): m for m in page.rows}
        assert rows.keys() == {(recording, role) for recording in roster for role in series}
        assert len(rows) == len(page.rows)
        assert rows["DS26-0036", "global"].decision == "withheld"
        assert rows["DS26-0036", "global"].error_km is None
        assert rows["DS26-0036", "global_forced"].error_km > 1000
        assert rows["DS26-0036", "one"].error_km == 0
        assert rows["DS26-0036", "one_forced"].decision == "no_estimate"
        assert rows["DS26-0036", "one_forced"].error_km is None
        if page.name != "folded_doppler":
            assert rows["DS26-0122", "global"].decision == "timed_out"
            assert rows["DS26-0122", "global_forced"].error_km is None
            assert rows["DS26-0237", "one"].decision == "withheld"
            assert rows["DS26-0237", "one_forced"].error_km == 0
            assert "six timing recordings" in page.subtitle
        else:
            assert "two smoke recordings" in page.subtitle


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "global", "different receiver or search mode"),
        ("catalog_sha256", "0" * 64, "unmatched catalog input"),
        ("id", "DS26-0066", "requested recording roster"),
    ],
)
def test_cold_start_rejects_mislabeled_or_unmatched_receipts(
    cold_start_receipts, field, value, message
):
    directory, store = cold_start_receipts
    path = directory / "point-votes/matched-tile.jsonl.gz"
    rows = list(cli.read_predictions(path).values())
    rows[0][field] = value
    store(path, rows)
    with pytest.raises(ValueError, match=message):
        books.published_pages("c0", ["point_votes"], evidence=directory)


def test_default_gallery_waits_for_both_primary_receipts_and_keeps_third_optional(
    cold_start_receipts, monkeypatch
):
    directory, _ = cold_start_receipts
    monkeypatch.setattr(books, "COLD_START_REPORT", directory)
    path = directory / "rate-triplets/matched-tile.jsonl.gz"
    saved = path.read_bytes()
    path.unlink()
    assert tuple(p.method for p in books.published_pages("c0", [])) == books.FRONTEND_METHODS
    cli.write(path, saved)
    optional = directory / "folded-doppler/matched-tile.jsonl.gz"
    third = optional.read_bytes()
    optional.unlink()
    assert [p.method for p in books.published_pages("c0", [])][-2:] == [
        "point_votes",
        "rate_triplets",
    ]
    cli.write(optional, third)
    assert [p.method for p in books.published_pages("c0", [])][-3:] == [
        "point_votes",
        "rate_triplets",
        "folded_doppler",
    ]


def test_cold_start_cli_renders_both_measured_search_modes(cold_start_receipts, tmp_path):
    directory, _ = cold_start_receipts
    out = tmp_path / "cold-preview"
    assert (
        cli.main(
            [
                "figures",
                "--variant",
                "point_votes",
                "--evidence",
                str(directory),
                "--arm",
                "c0",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    index = (out / "README.md").read_text()
    assert "Global search · published · 1/3" in index
    assert "Supplied tile · published · 2/3" in index
    assert (out / "c0/point_votes.png").read_bytes().startswith(b"\x89PNG")
    with (out / "c0/modifications.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 48
    assert dict(Counter(r["series"] for r in rows)) == {
        key: 6 for key in (*ROLES, "global", "global_forced", "one", "one_forced")
    }


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_memory_figure_uses_paired_stock_and_candidate_on_the_receipt_case(arm):
    (page,) = books.published_pages(arm, ["v5_batched_salvage"])
    rows = {m.series: m for m in page.rows}
    assert len(rows) == len(page.rows) == 6
    assert rows.keys() == {*ROLES, "one", "stock"}
    assert {m.recording for m in rows.values()} == {"DS26-0036"}
    assert rows["one"].error_km == rows["stock"].error_km
    assert rows["one"].error_km == pytest.approx(rows["baseline"].error_km, abs=1e-9)


def test_default_memory_figure_requires_a_completed_position_attempt(
    cold_start_receipts, monkeypatch
):
    directory, store = cold_start_receipts
    monkeypatch.setattr(books, "COLD_START_REPORT", directory)
    folder = directory / "catalogue-memory"
    refs = cli.references("smoke", None)[1]
    by_case = {r["id"]: r["truth"] for r in refs}
    inputs = {case: hashlib.sha256(case.encode()).hexdigest() for case in by_case}
    receipts = {"cases": list(by_case), "input_sha256": inputs, "runs": {}}

    def write_pair(run, name, method, *, stage_only=False):
        rows = [
            dict(id=case, method=method, input_sha256=inputs[case], **position(point))
            for case, point in by_case.items()
        ]
        if stage_only:
            for row in rows:
                row["result"] = dict(
                    boundary="catalogue propagation",
                    status="ok",
                    metrics={"position_attempted": False},
                )
        path = folder / name
        store(path, rows)
        receipts["runs"][run] = {"position_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        cli.write(folder / "receipt.json", cli.encoded(receipts))

    method = "v5_catalogue_memory"
    write_pair("control", "stock-positions.jsonl.gz", "compact_finish")
    write_pair("candidate", "positions.jsonl.gz", method, stage_only=True)
    assert method not in {p.method for p in books.published_pages("c0", [])}
    write_pair("candidate", "positions.jsonl.gz", method)
    page = books.published_pages("c0", [])[-1]
    assert page.method == method
    assert {m.recording for m in page.rows} == set(by_case)
    assert sum(m.series == "stock" and m.decision == "published" for m in page.rows) == 2


def reference(i):
    return dict(
        id=i,
        recording=i,
        group="DS26",
        truth=[0, 0],
        reference={k: {"c0": dict(error_km=1.25, status="ok")} for k in ROLES},
    )


def position(point=None, status="ok", **kwargs):
    arm = dict(latlon=point, **kwargs)
    return {
        "result": dict(
            status=status,
            boundary="position",
            metrics={},
            reason="test",
            arms={"c0": arm, "fitted_c": arm},
        )
    }


def test_cumulative_counts_every_recording_and_includes_exact_ties():
    refs = [reference(str(i)) for i in range(7)]
    raw = {
        "0": position([0, 0]),
        "1": position([0, 0.01]),
        "2": position([0, 0.01]),
        "3": position(status="withheld"),
        "4": position(status="failed"),
        "5": {"result": dict(status="ok", boundary="pilot search", metrics={})},
    }
    rows = marks(refs, raw, None, "v5_lean", "c0")
    single = [m for m in rows if m.series == "one"]
    assert {m.series for m in rows} == {*ROLES, "one"}
    assert [m.decision for m in single] == [
        "published",
        "published",
        "published",
        "withheld",
        "failed",
        "stage_only",
        "missing",
    ]
    error = distance_km([0, 0.01], [0, 0])
    np.testing.assert_array_equal(
        cumulative(single, [0, np.nextafter(error, 0), error, 500]), np.array([1, 1, 3, 3]) / 7
    )
    with pytest.raises(ValueError, match="unique"):
        marks(refs * 2, raw, None, "v5_lean", "c0")


def test_plot_only_names_a_frozen_cohort_when_its_recordings_match():
    cases = [r for r in cli.references("roof16", None)[1] if r["group"] == "DS29"]
    rows = [Mark("DS29", r["recording"], "baseline", "published", 1.0) for r in cases]
    assert "8 blind-panel recordings" in cohort_title("DS29", rows)
    different = Mark("DS29", "another recording", "baseline", "published", 1.0)
    assert cohort_title("DS29", [*rows[1:], different]).endswith("8 recordings")


def test_default_figure_command_includes_modifications_from_a_smaller_study(tmp_path):
    result = cli.main(
        ["figures", "--variant", "early_events", "--arm", "fitted_c", "--out", str(tmp_path)]
    )
    assert result == 0
    folder = tmp_path / "fitted_c"
    assert (folder / "early_events.png").is_file()
    with (folder / "modifications.csv").open() as stream:
        results = [r for r in csv.DictReader(stream) if r["series"] == "one"]
    assert len(results) == 8 and {r["decision"] for r in results} == {"withheld"}


def test_forced_guess_is_independent_of_publication_and_the_one_tile():
    refs = [reference("a"), reference("b")]
    single = {r["id"]: position([0, 0]) for r in refs}
    four = {"a": position([0, 0.02]), "b": position(status="withheld", forced_latlon=[0, 0.1])}
    rows = marks(refs, single, four, "projected_fit", "c0")
    default = marks(refs, single, four, "external", "c0")
    diagnostic = [m for m in rows if m.series == "four_forced"]
    assert [m.error_km for m in diagnostic] == [distance_km([0, v], [0, 0]) for v in (0.02, 0.1)]
    assert (
        next(m for m in default if (m.recording, m.series) == ("a", "four_forced")).error_km is None
    )
    assert [m.error_km for m in rows if m.series == "one"] == [0, 0]
    assert [m.decision for m in rows if m.series == "four"] == ["published", "withheld"]
    assert {m.series for m in rows} == {*ROLES, "one", "four", "four_forced"}


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_all_published_figures_use_matched_rosters_and_repeat_overlapping_results(arm):
    large, other = books.bundled(arm, books.TEN, additional=True)
    assert len(large) == len(books.TEN) == 10
    assert len(other) == 11 and other[-1].name == "native-to-v5"
    original_ds26 = {r["recording"] for r in cli.references("ds26-common127", None)[1]}
    expected_ds29 = {
        r["recording"] for r in cli.references("roof16", None)[1] if r["group"] == "DS29"
    }
    for page, small in zip(large, other[:-1], strict=True):
        assert small.method == page.name and small.name == page.name + "-roof16"
        observed = {(m.recording, m.series): m for m in page.rows}
        assert len(page.rows) == len(observed)
        for series in {m.series for m in page.rows}:
            assert {
                m.recording for m in page.rows if m.series == series
            } == original_ds26 | expected_ds29
        for m in small.rows:
            if m.recording in original_ds26 | expected_ds29:
                repeated = observed[m.recording, m.series]
                assert m.decision == repeated.decision
                if m.error_km is None:
                    assert repeated.error_km is None
                else:
                    assert m.error_km == pytest.approx(repeated.error_km, abs=1e-6, rel=0)
        if page.method == "v5_lean":
            for case in original_ds26 | expected_ds29:
                assert observed[case, "one"].error_km == pytest.approx(
                    observed[case, "baseline"].error_km, abs=1e-6
                )
    assert len({m.recording for m in other[-1].rows}) == 2


def test_four_tile_ds29_replays_match_archived_blind_region_queries():
    refs = [
        r
        for r in cli.references("transfer124", None)[1]
        if r["group"] == "DS29" and r["condition"] == "present"
    ]
    methods = ["orbit_interp", "shape_score", "track_reduce", "projected_fit"]
    small, _ = books.bundled("fitted_c", methods, panel="roof16")
    for page in small:
        records = cli.read_predictions(
            books.REPORT / "predictions/transfer124" / (page.method + ".jsonl.gz")
        )
        for case in refs:
            result = records[case["id"]]["result"]["arms"]["fitted_c"]
            for series, point in [
                ("four", result["latlon"]),
                ("four_forced", result.get("forced_latlon")),
            ]:
                expected = distance_km(point, case["truth"])
                row = next(
                    m for m in page.rows if (m.recording, m.series) == (case["recording"], series)
                )
                if expected is None:
                    assert row.error_km is None
                else:
                    assert row.error_km == pytest.approx(expected, abs=1e-6)


def test_orbital_reuse_reproduces_every_point_in_the_original_roof_figure():
    roof = cli.references("ds26-common127", None)[1] + cli.references("roof16", None)[1]
    originals = {r["id"]: dict(r["reference"]) for r in roof}
    for case in cli.references("transfer124", None)[1]:
        if case["group"] == "DS29" and case["condition"] == "present":
            originals[case["recording"]].update(case["reference"])
    pages, _ = books.bundled("fitted_c", ["orbit_interp"])
    lookup = {"one": "grid_one", "four": "grid_four", "four_forced": "grid_forced_four"}
    for mark in pages[0].rows:
        role = lookup.get(mark.series, mark.series)
        arm = "shape" if mark.series in lookup else "fitted_c"
        expected = originals[mark.recording][role][arm]["error_km"]
        if expected is None:
            assert mark.error_km is None
        else:
            assert mark.error_km == pytest.approx(expected, abs=1e-6, rel=0)


def test_frontend_position_receipts_match_each_detector_control_and_shared_raw_replay():
    offers = books._offer_digests()
    data = books._supplement("roof16-frontend-positions.jsonl.gz", offers)
    for case in cli.references("roof16", None)[1]:
        recording = case["id"]
        for method in ("glrt_batch", "glrt_cascade"):
            result = data[method, "one"][recording]["result"]
            metrics = result["metrics"]
            assert metrics["verified_windows"] == 80
            assert metrics["valid_receiver_windows"] > 0
            assert metrics["control_positive"] == metrics["positive"]
            assert metrics["peak_disagreements"] == 0
            assert metrics == data[method, "four"][recording]["result"]["metrics"]
        for mode in ("one", "four"):
            stream = data["iq_stream", mode][recording]["result"]
            native = data["iq_position", mode][recording]["result"]
            assert stream["arms"] == native["arms"] and stream["metrics"] == native["metrics"]
            assert stream["metrics"]["matched_reader_windows"] == 80


def test_supplement_rejects_different_offers_and_duplicate_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "REPORT", tmp_path)
    (tmp_path / "evidence").mkdir()
    filename = "measurements.jsonl.gz"
    row = dict(id="a", method="trial", offers="one", regions_sha256="abc", **position([0, 0]))
    with gzip.open(tmp_path / "evidence" / filename, "wt") as stream:
        stream.write((json.dumps(row) + "\n") * 2)
    with pytest.raises(ValueError, match="different region offers"):
        books._supplement(filename, {("a", "one"): "def"})
    with pytest.raises(ValueError, match="duplicate"):
        books._supplement(filename, {("a", "one"): "abc"})


def test_peak_projection_and_input_binding(tmp_path):
    epoch, cfo, margin, counter = 456, -4500, 0.3, 123456789
    peak = dict(passed=True, epoch_sample=epoch, alias_cfo_hz=cfo, margin=margin)
    picked = pilot_positions._bank_peak({"winner": peak})
    rate, size = waveform.RATE, waveform.PROBE_SAMPLES
    (point,) = pilot_positions._point(picked, counter, rate, size)
    assert point.first_counter == counter and point.cfo_hz == cfo and point.margin == margin
    for test_epoch, frames in [(epoch, 15), (12_000, 14)]:
        offsets = np.rint(np.arange(frames) * rate / 750)[:, None, None] + waveform.TAPS
        (measured,) = pilot_positions._point((test_epoch, cfo, margin), counter, rate, size)
        assert measured.time_s == pytest.approx(
            (counter + test_epoch + offsets.mean()) / rate, abs=1e-14, rel=0
        )
    assert point.phase_us == waveform.phase_at(epoch, counter)
    assert pilot_positions._point(None, counter, rate, size) == []
    assert pilot_positions._bank_peak({"winner": dict(peak, passed=False)}) is None
    paths = {key + "_path": tmp_path / key for key in ("observation", "catalog")}
    for path in paths.values():
        path.write_bytes(b"original")
    digest = hashlib.sha256(b"original").hexdigest()
    entry = {"x": dict(observation_sha256=digest, catalog_sha256=digest, regions=["original"])}
    assert roof_replays.four_offers(dict(id="x", **paths), entry) == ["original"]
    paths["catalog_path"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="catalog differs"):
        roof_replays.four_offers(dict(id="x", **paths), entry)


def test_figure_command_creates_named_pngs_multi_page_pdf_and_attempt_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_EVAL_BULK_ROOT", str(tmp_path / "absent"))
    assert (
        cli.main(
            [
                "figures",
                "--variant",
                "v5_lean",
                "--variant",
                "orbit_interp",
                "--evidence",
                str(books.REPORT / "evidence"),
                "--out",
                str(tmp_path),
                "--arm",
                "fitted_c",
            ]
        )
        == 0
    )
    folder = tmp_path / "fitted_c"
    assert all(
        (folder / (v + ".png")).read_bytes().startswith(b"\x89PNG")
        for v in ("v5_lean", "orbit_interp")
    )
    assert len(re.findall(rb"/Type /Page\b", (folder / "modifications.pdf").read_bytes())) == 2
    with (folder / "modifications.csv").open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["series"] == "baseline"]
    assert Counter(r["figure"] for r in rows) == {"v5_lean": 135, "orbit_interp": 135}
    gallery = (folder / "README.md").read_text()
    images = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", gallery)
    assert images == ["v5_lean.png", "orbit_interp.png"]
    assert all((folder / filename).is_file() for filename in images)
    index = (tmp_path / "README.md").read_text()
    assert "(fitted_c/README.md)" in index
    assert "DS26 fixes · median km · P95 km" in index
    assert "127/127 · 0.999 · 3.126" in index
