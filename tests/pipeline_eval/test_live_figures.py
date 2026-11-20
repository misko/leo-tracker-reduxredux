import csv
import json

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval import figure_books

METHOD = "candidate"
PANEL = "roof16"
PUBLISHED = "DS26-0036"
MISSING = "DS26-0070"
WITHHELD = "DS26-0112"


def _prediction(case, point=None, *, c0=None, timing=1):
    result = dict(
        status="ok" if point is not None else "withheld",
        reason="receiver decision",
        boundary="position solver",
        metrics={"candidate_s": timing},
        arms={"c0": {"latlon": c0 or point}, "fitted_c": {"latlon": point}},
    )
    return {"id": case, "result": result}


def _score(root, cases, records, panel=PANEL):
    root.mkdir(exist_ok=True, parents=True)
    predictions = root / "submitted.jsonl"
    predictions.write_text("".join(json.dumps(r) + "\n" for r in records))
    assert (
        cli.main(
            [
                "score",
                "--panel",
                panel,
                "--name",
                METHOD,
                "--predictions",
                str(predictions),
                "--out",
                str(root),
                *(arg for case in cases for arg in ("--case", case)),
            ]
        )
        == 0
    )


def _figures(root, out, *, panel=PANEL, arm="both", variant=METHOD):
    return cli.main(
        [
            "figures",
            "--panel",
            panel,
            "--runs",
            str(root),
            "--out",
            str(out),
            "--arm",
            arm,
            *(["--variant", variant] if variant else []),
        ]
    )


def _decisions(folder, series):
    with (folder / "modifications.csv").open() as stream:
        return [
            (r["recording"], r["decision"]) for r in csv.DictReader(stream) if r["series"] == series
        ]


def test_live_figures_join_declared_subset_attempts_and_deduplicate_agreeing_repeats(tmp_path):
    root = tmp_path / "runs"
    fix = [38.3, -104.8]
    _score(root, [PUBLISHED, MISSING], [_prediction(PUBLISHED, fix)])
    _score(
        root, [PUBLISHED, WITHHELD], [_prediction(PUBLISHED, fix, timing=2), _prediction(WITHHELD)]
    )
    interrupted = root / PANEL / METHOD / "subset-interrupted" / "runs" / "aborted"
    interrupted.mkdir(parents=True)
    (interrupted / "predictions.jsonl").write_text("unfinished")

    out = tmp_path / "figures"
    assert _figures(root, out, variant=None) == 0
    expected = [(PUBLISHED, "published"), (MISSING, "missing"), (WITHHELD, "withheld")]
    for arm in ("c0", "fitted_c"):
        folder = out / arm
        assert (folder / f"{METHOD}.png").read_bytes().startswith(b"\x89PNG")
        assert _decisions(folder, "one") == expected
        assert _decisions(folder, "baseline") == [(case, "published") for case, _ in expected]
    assert "1/3" in (out / "README.md").read_text()


def test_figures_reject_conflicting_repeats_in_either_calibration_arm(tmp_path):
    root = tmp_path / "runs"
    fix = [47.3, 8.5]
    _score(root, [PUBLISHED], [_prediction(PUBLISHED, fix)])
    _score(root, [PUBLISHED, MISSING], [_prediction(PUBLISHED, fix, c0=[47.4, 8.5])])

    out = tmp_path / "figures"
    with pytest.raises(ValueError, match=rf"conflicting.*{PUBLISHED}.*subset-.*subset-"):
        _figures(root, out, arm="fitted_c")
    assert not out.exists()


def test_both_figure_arms_use_the_same_generation_if_a_run_is_republished(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    _score(root, [PUBLISHED], [_prediction(PUBLISHED, [38.3, -104.8])])
    write_book = figure_books.write_book

    def publish_during_export(pages, destination, name, arm):
        write_book(pages, destination, name, arm)
        if arm == "fitted_c":
            _score(root, [PUBLISHED], [_prediction(PUBLISHED)])

    monkeypatch.setattr(figure_books, "write_book", publish_during_export)
    out = tmp_path / "figures"
    assert _figures(root, out) == 0
    for arm in ("c0", "fitted_c"):
        assert _decisions(out / arm, "one") == [(PUBLISHED, "published")]
    after = tmp_path / "next-figures"
    assert _figures(root, after, arm="c0") == 0
    assert _decisions(after / "c0", "one") == [(PUBLISHED, "withheld")]


@pytest.mark.parametrize("flat", [False, True])
def test_full_run_takes_precedence_over_subsets_including_flat_archive(tmp_path, flat):
    root = tmp_path / "runs"
    panel = "smoke"
    _score(root, [PUBLISHED], [_prediction(PUBLISHED)], panel)
    full = [_prediction(PUBLISHED, [47.3, 8.5])]
    if flat:
        (root / panel / METHOD / "predictions.jsonl").write_text(json.dumps(full[0]) + "\n")
    else:
        _score(root, [], full, panel)

    out = tmp_path / "figures"
    assert _figures(root, out, panel=panel, arm="c0") == 0
    assert _decisions(out / "c0", "one") == [(PUBLISHED, "published"), ("DS29-0082", "missing")]


def test_flat_subset_archives_use_declared_attempts_and_label_mixed_digests(tmp_path):
    for index, case in enumerate((PUBLISHED, MISSING)):
        folder = tmp_path / PANEL / METHOD / f"subset-archived-{index}"
        folder.mkdir(parents=True)
        summary = dict(
            panel=PANEL,
            method=METHOD,
            ids=[case],
            run={"implementation_sha256": str(index) * 64},
        )
        (folder / "summary.json").write_text(json.dumps(summary))
        (folder / "predictions.jsonl").write_text("")

    out = tmp_path / "figures"
    assert _figures(tmp_path, out, arm="c0") == 0
    assert _decisions(out / "c0", "one") == [(PUBLISHED, "missing"), (MISSING, "missing")]
    assert "Implementation digests differ" in (out / "c0" / "README.md").read_text()


@pytest.mark.parametrize(
    ("override", "records", "message"),
    [
        ({"panel": "smoke"}, [], "panel or method"),
        ({"method": "another-method"}, [], "panel or method"),
        ({"ids": [PUBLISHED, PUBLISHED]}, [], "roster"),
        ({"ids": ["unknown"]}, [], "roster"),
        ({}, [_prediction(MISSING)], "outside.*roster"),
        ({}, None, "missing predictions"),
        (None, [], "missing completion summary"),
    ],
)
def test_figures_reject_inconsistent_subset_completion(tmp_path, override, records, message):
    folder = tmp_path / PANEL / METHOD / "subset-archived"
    folder.mkdir(parents=True)
    if override is not None:
        summary = dict(panel=PANEL, method=METHOD, ids=[PUBLISHED]) | override
        (folder / "summary.json").write_text(json.dumps(summary))
    if records is not None:
        (folder / "predictions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))

    out = tmp_path / "figures"
    with pytest.raises(ValueError, match=message):
        _figures(tmp_path, out, arm="c0")
    assert not out.exists()
