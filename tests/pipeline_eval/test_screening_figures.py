import csv
import gzip
from collections import Counter
from hashlib import sha256

import pytest
from pypdf import PdfReader

from tools.pipeline_eval import figure_books
from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import prototype_figures
from tools.pipeline_eval.qualification import screening_figures as charts
from tools.pipeline_eval.qualification import short_receiver_figures as shared
from tools.pipeline_eval.scoring import ARMS, ROLES, distance_km, validate_result


def _save_json(path, data):
    path.write_bytes(encoded(data) + b"\n")


def _publish(folder, chart, cases, *, predictions, queries=None, version=1):
    folder.mkdir(exist_ok=True)
    files = {}
    archive = folder / "positions.jsonl.gz"
    raw = b"".join(encoded(row) + b"\n" for row in predictions)
    archive.write_bytes(gzip.compress(raw, mtime=0))
    files[archive.name] = sha256(archive.read_bytes()).hexdigest()
    if queries is not None:
        query_path = folder / "queries.json"
        _save_json(query_path, {"queries": queries})
        files[query_path.name] = sha256(query_path.read_bytes()).hexdigest()
    _save_json(folder / "receipt.json", {"cases": cases, "files": files})
    _save_json(folder / "figures.json", {"version": version, "charts": [chart]})


def _result(latlon, *, status="ok", forced=None, attempted=True):
    return {
        "status": status,
        "boundary": "Measured result",
        "reason": None if status == "ok" else status,
        "metrics": {"position_attempted": attempted},
        "arms": {arm: {"latlon": latlon, "forced_latlon": forced} for arm in ARMS},
    }


def _roof_bundle():
    refs, inputs = shared._frozen_roof()
    chart = {
        "id": "sample-roof",
        "method": "sample",
        "scope": "roof",
        "title": "Matched sample",
        "caption": "Identical native observations and catalogue in both fits.",
        "cases": "smoke-two",
        "seal": "receipt.json",
        "series": [
            {
                "key": "one",
                "label": "Candidate",
                "file": "positions.jsonl.gz",
                "value": "sample",
                "field": "variant",
            },
            {
                "key": "stock",
                "label": "Historical control",
                "file": "positions.jsonl.gz",
                "value": "control",
                "match": ["input_sha256"],
            },
        ],
    }
    predictions = []
    for ident in shared.SMOKE:
        common = {
            "id": ident,
            "input_sha256": sha256(ident.encode()).hexdigest(),
            "native_sha256": inputs[ident]["native"]["sha256"],
            "catalog_sha256": inputs[ident]["catalog"]["sha256"],
        }
        position = refs[ident]["truth"]
        result = _result(position)
        if ident == shared.SMOKE[0]:
            result = _result(None, status="withheld", attempted=False)
        predictions.extend(
            [
                dict(common, variant="sample", result=result),
                dict(common, method="control", result=_result(position)),
            ]
        )
    return chart, predictions


def _new_roof_bundle(ident="DS29-9999"):
    chart, _ = _roof_bundle()
    chart.update(
        cases="sealed",
        roof_references={"authority": "roof-authority.json", "predictions": "fresh-v5.jsonl.gz"},
    )
    truth = [37.0, -122.0]
    common = dict(
        paired_capture_sha256="a" * 64,
        catalog_sha256="b" * 64,
        capture_manifest_sha256="sha256:" + "d" * 64,
        tile={"id": "r0", "center": truth, "width_km": 25.0},
    )
    authority = dict(id=ident, group="DS29", recording=ident, truth=truth, bindings=common)
    candidate = dict(id=ident, **common, input_sha256="c" * 64, native_sha256="e" * 64)
    rows = [
        dict(candidate, variant="sample", result=_result(truth)),
        dict(candidate, method="control", result=_result(truth)),
    ]
    original = dict(id=ident, **common, native_sha256=common["paired_capture_sha256"])
    baseline = _result([37.001, -122.0])
    baseline["arms"]["fitted_c"]["latlon"] = [37.002, -122.0]
    timed_out = _result(None, status="timed_out")
    del timed_out["arms"]
    one_arm = _result(truth)
    one_arm["arms"]["fitted_c"]["latlon"] = None
    roles = [
        dict(original, method=role, result=result)
        for role, result in zip(
            ROLES,
            (baseline, _result(None, status="withheld"), timed_out, one_arm),
            strict=True,
        )
    ]
    return chart, authority, rows, roles


def _publish_new_roof(folder, chart, authority, rows, roles):
    _publish(folder, chart, list(dict.fromkeys(row["id"] for row in rows)), predictions=rows)
    authority_path = folder / "roof-authority.json"
    control_path = folder / "fresh-v5.jsonl.gz"
    _save_json(authority_path, {"cases": [authority]})
    control_path.write_bytes(
        gzip.compress(b"".join(encoded(row) + b"\n" for row in roles), mtime=0)
    )
    receipt_path = folder / "receipt.json"
    receipt = shared._json(receipt_path)
    receipt["files"].update(
        {
            path.name: sha256(path.read_bytes()).hexdigest()
            for path in (authority_path, control_path)
        }
    )
    _save_json(receipt_path, receipt)


def test_new_roof_renders_fresh_original_v5_controls_and_keeps_timeouts(tmp_path):
    chart, authority, rows, roles = _new_roof_bundle()
    study = tmp_path / "study"
    _publish_new_roof(study, chart, authority, rows, roles)
    manifest = figure_books.generate(tmp_path / "charts", ARMS, panel="screening", evidence=study)
    assert len(manifest) == 2
    truth = authority["truth"]
    for page in manifest:
        assert (tmp_path / "charts" / page["image"]).read_bytes().startswith(b"\x89PNG")
        arm = page["arm"]
        with (tmp_path / "charts" / page["csv"]).open() as stream:
            marks = {row["series"]: row for row in csv.DictReader(stream)}
        assert set(marks) == {*ROLES, "one", "stock"}
        assert {row["recording"] for row in marks.values()} == {authority["id"]}
        measured = roles[0]["result"]["arms"][arm]["latlon"]
        assert float(marks["baseline"]["error_km"]) == pytest.approx(distance_km(measured, truth))
        assert marks["selective-gap"]["decision"] == "withheld"
        assert marks["omitted-track-one"]["decision"] == "timed_out"
        assert marks["omitted-track-one"]["error_km"] == ""
        assert marks["omitted-tracks"]["decision"] == ("published" if arm == "c0" else "withheld")


def test_mixed_roof_uses_frozen_authority_only_for_existing_recordings(tmp_path):
    chart, authority, rows, roles = _new_roof_bundle()
    _, frozen = _roof_bundle()
    known = shared.SMOKE[1]
    old_rows = [row for row in frozen if row["id"] == known]
    _publish_new_roof(tmp_path, chart, authority, rows + old_rows, roles)
    (loaded,) = charts.charts(evidence=tmp_path)
    assert set(loaded.cases) == {authority["id"], known}
    refs, _ = charts._roof_authority()
    assert loaded.references[known] == refs[known]
    for arm in ARMS:
        marks = loaded.page(arm).rows
        assert {row.recording for row in marks} == set(loaded.cases)
        assert all(
            {m.series for m in marks if m.recording == ident} >= set(ROLES)
            for ident in loaded.cases
        )
    old_rows[0]["native_sha256"] = "f" * 64
    _publish_new_roof(tmp_path, chart, authority, rows + old_rows, roles)
    with pytest.raises(ValueError, match="frozen native and causal catalogue"):
        charts.charts(evidence=tmp_path)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("frozen", "cannot replace frozen roof"),
        ("missing-role", "prespecified recording roster"),
        ("duplicate-role", "four distinct original roles"),
        ("native", "different capture-era native input"),
        ("catalogue", "sealed new roof capture, catalogue or tile"),
        ("candidate-manifest", "sealed new roof capture, catalogue or tile"),
        ("tile", "sealed new roof capture, catalogue or tile"),
        ("calibration", "lacks calibration arms"),
        ("tampered", "frozen content hash"),
    ],
)
def test_new_roof_requires_complete_sealed_roles_and_matched_public_inputs(tmp_path, change, error):
    ident = shared.SMOKE[0] if change == "frozen" else "DS29-9999"
    chart, authority, rows, roles = _new_roof_bundle(ident)
    if change == "missing-role":
        roles.pop()
    elif change == "duplicate-role":
        roles.append(roles[0])
    elif change == "native":
        roles[0]["native_sha256"] = "f" * 64
    elif change == "catalogue":
        roles[0]["catalog_sha256"] = "f" * 64
    elif change == "candidate-manifest":
        del rows[0]["capture_manifest_sha256"]
    elif change == "tile":
        rows[0]["tile"] = dict(rows[0]["tile"], width_km=35.0)
    elif change == "calibration":
        del roles[0]["result"]["arms"]
    _publish_new_roof(tmp_path, chart, authority, rows, roles)
    if change == "tampered":
        filename = tmp_path / "fresh-v5.jsonl.gz"
        filename.write_bytes(filename.read_bytes() + b"change")
    with pytest.raises(ValueError, match=error):
        charts.charts(evidence=tmp_path)


def test_roof_manifest_renders_both_arms_from_one_stage_aware_snapshot(tmp_path, monkeypatch):
    chart, rows = _roof_bundle()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _publish(evidence / "study", chart, shared.SMOKE, predictions=rows)
    output = tmp_path / "out"
    original = charts._prediction_rows
    decoded = []

    def count_decode(name, data):
        decoded.append(name)
        return original(name, data)

    monkeypatch.setattr(charts, "_prediction_rows", count_decode)
    manifest = figure_books.generate(output, ARMS, panel="screening", evidence=evidence)
    assert decoded == ["positions.jsonl.gz"]
    assert {entry["arm"] for entry in manifest} == set(ARMS)
    assert len(manifest) == 2
    for entry in manifest:
        assert entry["image"] in (output / "index.html").read_text()
        assert (output / entry["image"]).read_bytes().startswith(b"\x89PNG")
        with (output / entry["csv"]).open() as stream:
            sample = list(csv.DictReader(stream))
        assert Counter(row["series"] for row in sample) == dict.fromkeys(
            (*ROLES, "one", "stock"), 2
        )
        (blank,) = [row for row in sample if row["decision"] == "stage_only"]
        assert blank["series"] == "one" and blank["error_km"] == ""


def test_roof_chart_records_a_paired_terminal_withholding_without_positions(tmp_path):
    chart, rows = _roof_bundle()
    for row in rows[::2]:
        row["result"] = _result(None, status="withheld", attempted=False)
    rows[0]["result"]["metrics"]["terminal_position_decision"] = True
    rows[0]["result"]["reason"] = "No consistent in-tile orbit set"
    _publish(tmp_path, chart, shared.SMOKE, predictions=rows)
    (study,) = charts.charts(evidence=tmp_path)
    for arm in ARMS:
        marks = [m for m in study.page(arm).rows if m.series == "one"]
        assert Counter(m.decision for m in marks) == {"stage_only": 1, "withheld": 1}
        assert all(m.error_km is None for m in marks)
    projected = study.predictions["one"][shared.SMOKE[0]]["result"]
    assert projected["reason"] == rows[0]["result"]["reason"]


@pytest.mark.parametrize("version", [1, 2])
def test_roof_cli_labels_full_failure_denominators_in_both_arms(tmp_path, version):
    chart, rows = _roof_bundle()
    for row, status in zip(rows[::2], ("failed", "timed_out"), strict=True):
        row["result"] = _result(None, status=status, attempted=False)
    _publish(tmp_path / "study", chart, shared.SMOKE, predictions=rows, version=version)
    output = tmp_path / "output"
    for entry in figure_books.generate(output, ARMS, panel="screening", evidence=tmp_path):
        with (output / entry["csv"]).open() as stream:
            sample = [row for row in csv.DictReader(stream) if row["series"] == "one"]
        assert Counter(row["decision"] for row in sample) == {"failed": 1, "timed_out": 1}
        assert all(not row["error_km"] for row in sample)
        text = PdfReader(output / entry["pdf"]).pages[0].extract_text()
        if version == 2:
            assert "0/1 · failed" in text and "0/1 · timed out" in text
        else:
            assert "0/1 ·" not in text and "Candidate    unmeasured" in text


@pytest.mark.parametrize("change", ["type", "failed", "refined", "reason", "arms", "forced"])
def test_terminal_withholding_marker_needs_two_null_arms_and_a_real_decision(change):
    result = _result(None, status="withheld", attempted=False)
    result["metrics"]["terminal_position_decision"] = True
    if change == "type":
        result["metrics"]["terminal_position_decision"] = 1
    elif change == "failed":
        result["status"] = "failed"
    elif change == "refined":
        result["metrics"]["position_attempted"] = True
    elif change == "reason":
        result["reason"] = " "
    elif change == "arms":
        del result["arms"]
    else:
        result["arms"]["c0"]["forced_latlon"] = [0.0, 0.0]
    with pytest.raises(ValueError, match="terminal position decision"):
        validate_result(result)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("file", "frozen content hash"),
        ("omitted", "prespecified recording roster"),
        ("duplicate", "prespecified recording roster"),
        ("native", "frozen native and causal catalogue"),
        ("paired", "unmatched input"),
        ("fake", "position for an unmeasured"),
        ("escape", "name a file within"),
    ],
)
def test_screening_rejects_incomplete_or_misbound_evidence(tmp_path, change, expected):
    chart, rows = _roof_bundle()
    if change == "omitted":
        rows.pop()
    elif change == "duplicate":
        rows.append(rows[-1])
    elif change == "native":
        rows[0]["catalog_sha256"] = "a" * 64
    elif change == "paired":
        rows[1]["input_sha256"] = "a" * 64
    elif change == "fake":
        rows[0]["result"]["arms"]["c0"]["forced_latlon"] = [36.0, 120.0]
    elif change == "escape":
        chart["series"][0]["file"] = "../positions.jsonl.gz"
    folder = tmp_path / "panel"
    _publish(folder, chart, shared.SMOKE, predictions=rows)
    if change == "file":
        path = folder / "positions.jsonl.gz"
        path.write_bytes(path.read_bytes() + b"unexpected")
    with pytest.raises(ValueError, match=expected):
        charts.charts(evidence=tmp_path)


def test_sealed_transfer_preserves_false_fix_and_contract_ineligible_best_guess(tmp_path):
    chart = {
        "id": "sample-transfer",
        "method": "candidate",
        "scope": "transfer",
        "title": "Three trial boundaries",
        "caption": "Original conditions are preserved as sealed in the report.",
        "cases": "sealed",
        "seal": "receipt.json",
        "queries": "queries.json",
        "series": [
            {
                "key": role,
                "label": role.title(),
                "file": "positions.jsonl.gz",
                "value": role,
                "where": {"panel": "planned"},
            }
            for role in ("candidate", "stock")
        ],
    }
    queries, rows = [], []
    for ident, condition, eligible in (
        ("true", "Correct tile", True),
        ("wrong", "Correct region omitted", True),
        ("single", "Only one physical lane", False),
    ):
        digest = sha256(ident.encode()).hexdigest()
        queries.append(
            {
                "id": ident,
                "condition": condition,
                "recording": "site-A",
                "truth": [0.0, 0.0],
                "bindings": {"input_sha256": digest},
                "eligible": eligible,
            }
        )
        for method in ("candidate", "stock"):
            disposition = _result([0.0, 1.0], forced=[1.0, 1.0])
            if method == "stock" and ident == "wrong":
                disposition = _result(None, status="withheld")
            rows.append(
                {
                    "id": ident,
                    "method": method,
                    "panel": "planned",
                    "input_sha256": digest,
                    "result": disposition,
                }
            )
    _publish(
        tmp_path / "study", chart, [q["id"] for q in queries], predictions=rows, queries=queries
    )
    (trial,) = charts.charts(evidence=tmp_path)
    for arm in ARMS:
        marks = trial.page(arm).rows
        assert not ({r.series for r in marks} & set(ROLES))
        by = {(r.dataset, r.series): r for r in marks}
        false_fix = by[("Correct region omitted", "candidate")]
        assert false_fix.decision == "published" and false_fix.error_km > 100
        assert by[("Only one physical lane", "candidate")].decision == "unavailable"
        assert by[("Only one physical lane", "diagnostic")].error_km > 100
        assert by[("Correct region omitted", "stock")].error_km is None


def _excluded_roof_bundle():
    chart, _ = _roof_bundle()
    chart["cases"] = "ds26-excluded32"
    refs, inputs = charts._roof_authority()
    cases = charts._cases("ds26-excluded32", None)
    rows = []
    for ident in cases:
        item = inputs[ident]
        if "unavailable" in item:
            result = _result(None, status="unavailable", attempted=False)
            result["reason"] = item["unavailable"]
            native = catalogue = digest = None
        else:
            result = _result(refs[ident]["truth"])
            native = item["native"]["sha256"]
            catalogue = item["catalog"]["sha256"]
            digest = sha256(ident.encode()).hexdigest()
        common = dict(
            id=ident,
            native_sha256=native,
            catalog_sha256=catalogue,
            input_sha256=digest,
            tile=item["regions"][0],
            result=result,
        )
        rows.extend([dict(common, variant="sample"), dict(common, method="control")])
    return chart, cases, rows


def test_excluded_roof_chart_counts_the_missing_input_in_every_series(tmp_path):
    chart, cases, rows = _excluded_roof_bundle()
    _publish(tmp_path / "study", chart, cases, predictions=rows)
    (trial,) = charts.charts(evidence=tmp_path)
    for arm in ARMS:
        marks = trial.page(arm).rows
        assert Counter(r.series for r in marks) == dict.fromkeys((*ROLES, "one", "stock"), 32)
        published = Counter(r.series for r in marks if r.error_km is not None)
        assert [published[k] for k in (*ROLES, "one", "stock")] == [16, 14, 11, 5, 31, 31]


@pytest.mark.parametrize(
    "tamper", ["native", "reason", "tile", "coordinate", "status", "attempt", "worker", "other"]
)
def test_only_the_frozen_missing_capture_can_have_null_bindings(tmp_path, tamper):
    chart, cases, rows = _excluded_roof_bundle()
    ident = "DS26-0172" if tamper != "other" else cases[0]
    row = next(r for r in rows if r["id"] == ident)
    if tamper in ("native", "other"):
        row["native_sha256"] = None if tamper == "other" else "0" * 64
    elif tamper == "reason":
        row["result"]["reason"] = "no result"
    elif tamper == "tile":
        row["tile"] = {"id": "other", "center": [0.0, 0.0]}
    elif tamper == "coordinate":
        row["result"]["arms"]["c0"]["latlon"] = [1.0, 1.0]
    elif tamper == "attempt":
        row["result"]["metrics"]["position_attempted"] = True
    elif tamper == "worker":
        row["worker_attempted"] = True
    else:
        row["result"]["status"] = "withheld"
    _publish(tmp_path / "study", chart, cases, predictions=rows)
    with pytest.raises(ValueError, match="unavailable|frozen native|cannot publish a coordinate"):
        charts.charts(evidence=tmp_path)


def test_transfer_counts_a_publication_on_a_query_without_geographic_truth():
    queries = {
        "null": {
            "condition": "Shuffled detections",
            "recording": "shuffle",
            "truth": None,
        }
    }
    predictions = {"candidate": {"null": {"result": _result([0, 0], forced=[1, 0])}}}
    rows = charts._transfer_marks(queries, predictions, "c0")
    assert [(r.decision, r.error_km) for r in rows] == [("published", None), ("diagnostic", None)]
    fig = prototype_figures.draw(
        prototype_figures.Page("shuffle", "Shuffled control", "No geographic reference.", rows),
        "c0",
        series_labels={"candidate": "Candidate"},
    )
    try:
        assert [tick.get_text() for tick in fig.axes[0].get_yticklabels()] == [
            "Candidate  1/1 · 0 scored",
            "Prototype · diagnostic  1/1 · 0 scored",
        ]
    finally:
        prototype_figures.plt.close(fig)


@pytest.mark.parametrize("version", [1, 2])
def test_transfer_chart_preserves_observed_rejection_and_unmeasured_diagnostic(version):
    queries = {"case": {"condition": "Correct region omitted", "recording": "site", "truth": None}}
    diagnostic = _result(None, status="withheld", attempted=False)
    gated = _result(None, status="withheld", attempted=False)
    gated["metrics"]["terminal_position_decision"] = True
    predictions = {
        "candidate": {"case": {"result": gated}},
        "stock": {"case": {"result": diagnostic}},
        "one": {"case": {"result": _result(None, status="failed", attempted=False)}},
        "four": {"case": {"result": _result(None, status="missing", attempted=False)}},
    }
    for arm in ARMS:
        marks = charts._transfer_marks(queries, predictions, arm, version=version)
        assert [(m.series, m.decision, m.error_km) for m in marks] == [
            ("candidate", "withheld", None),
            ("stock", "stage_only", None),
            ("one", "failed" if version == 2 else "stage_only", None),
            ("four", "missing" if version == 2 else "stage_only", None),
        ]


def test_v2_failed_result_rejects_legacy_forced_diagnostic():
    result = _result(None, status="timed_out", forced=[0.0, 0.0])
    record = {"id": "timeout", "result": result}
    validate_result(result)
    assert charts._checked_result(record, "legacy") == result
    with pytest.raises(ValueError, match="failed or missing result cannot supply"):
        charts._checked_result(record, "current", version=2)


@pytest.mark.parametrize("arm", ARMS)
def test_screening_roof_studies_keep_lineage_and_distinct_unmeasured_stage(arm):
    selected = (
        "orbital_projector_arm",
        "fractional_adjoint",
        "v5_secant_fit-full-iq",
        "v5_armijo_fit",
        "robust_support",
        "portable_v5-roof",
    )
    studies = {chart.id: chart for chart in charts.charts(selected)}
    for method, count in zip(selected, (2, 2, 2, 6, 8, 1), strict=True):
        page = studies[method].page(arm)
        assert Counter(row.series for row in page.rows)["one"] == count
    assert all(
        r.decision == "stage_only" and r.error_km is None
        for r in studies["orbital_projector_arm"].page(arm).rows
        if r.series == "one"
    )
    detector = studies["fractional_adjoint"].page(arm).rows
    assert [r.error_km for r in detector if r.series == "one"] == [
        r.error_km for r in detector if r.series == "stock"
    ]
    assert "DS26-0277" in studies["robust_support"].cases
    assert "DS26-0277" not in charts._cases("roof135", [])


@pytest.mark.parametrize("arm", ARMS)
def test_screening_transfer_cases_are_kept_under_their_sealed_offers(arm):
    physical, site, roof = (
        {c.id: c for c in charts.charts([name])}[name].page(arm)
        for name in (
            "affine_beacon_curvature",
            "robust_support-site-transfer",
            "robust_support-wrong-region",
        )
    )
    for page, n in ((physical, 12), (site, 13), (roof, 8)):
        assert len([r for r in page.rows if r.series == "candidate"]) == n
        assert not ({r.series for r in page.rows} & set(ROLES))
    assert all(r.error_km is None for r in physical.rows if r.series == "candidate")
    assert all(r.error_km is None for r in roof.rows if r.series in {"candidate", "stock", "one"})
    assert sum(r.decision == "published" for r in site.rows if r.series == "candidate") == 4


@pytest.mark.parametrize("arm", ARMS)
def test_portable_retries_do_not_replace_original_timed_out_queries(arm):
    paths = charts.charts(["portable_v5-synthetic", "portable_v5-synthetic-retry"])
    initial, retry = paths
    assert len(initial.cases) == 4
    assert set(retry.cases) < set(initial.cases)
    assert Counter(r.decision for r in initial.page(arm).rows if r.series == "candidate") == {
        "published": 1,
        "timed_out": 3,
    }
    assert Counter(r.decision for r in retry.page(arm).rows if r.series == "candidate") == {
        "timed_out": 2
    }


@pytest.mark.parametrize("arm", ARMS)
def test_screening_winner_and_discovery_memory_keep_real_stock_pairs(arm):
    selected = (
        "v5_screen_winner",
        "v5_screen_secant",
        "v5_discovery_memory-ordinary",
        "v5_discovery_memory-capture-era",
    )
    matches = {c.id: c.page(arm) for c in charts.charts(selected)}
    for ident, n in zip(selected, (6, 6, 2, 1), strict=True):
        rows = matches[ident].rows
        assert Counter(r.series for r in rows) == dict.fromkeys((*ROLES, "one", "stock"), n)
        assert [r.error_km for r in rows if r.series == "one"] == [
            r.error_km for r in rows if r.series == "stock"
        ]


@pytest.mark.parametrize("arm", ARMS)
def test_armijo_finish_keeps_a_failure_distinct_from_an_unavailable_control(arm):
    (chart,) = charts.charts(["v5_armijo_finish"])
    rows = chart.page(arm).rows
    assert Counter(r.series for r in rows) == dict.fromkeys(
        (*ROLES, "one", "stock", "one_native_factors", "all_visits"), 4
    )
    (failure,) = [r for r in rows if r.decision == "failed"]
    (unavailable,) = [r for r in rows if r.decision == "missing"]
    assert failure.series == "one" and failure.error_km is None
    assert unavailable.series == "stock" and unavailable.error_km is None
    assert failure.recording != unavailable.recording
    (retry,) = charts.charts(["v5_armijo_finish_phase_seed"])
    assert retry.cases == ("DS26-0066",)
    decisions = {r.series: r for r in retry.page(arm).rows}
    assert decisions["stock"].decision == "failed" and decisions["stock"].error_km is None
    assert decisions["one"].decision == "published"
    (guarded,) = [
        item
        for item in charts.charts(["v5_armijo_aligned_finish"])
        if item.id == "v5_armijo_aligned_finish"
    ]
    assert guarded.cases == chart.cases
    outcomes = [r.decision for r in guarded.page(arm).rows if r.series == "one"]
    assert outcomes == ["published"] * 4


@pytest.mark.parametrize("arm", ARMS)
def test_full_secant_plot_preserves_the_authenticated_127_plus_eight(arm):
    (chart,) = charts.charts(["v5_secant_fit-roof135"])
    rows = chart.page(arm).rows
    assert Counter((r.dataset, r.series) for r in rows) == {
        (dataset, key): n
        for dataset, n in (("DS26", 127), ("DS29", 8))
        for key in (*ROLES, "one", "stock")
    }
    assert all(r.decision == "published" for r in rows if r.series == "one")


def test_coincident_beacon_plot_keeps_three_policies_on_all_eight_measured_sites():
    (chart,) = charts.charts(["coincident_beacon_difference"])
    assert chart.scope == "transfer"
    assert len(chart.cases) == 24
    rows = chart.page("c0").rows
    assert rows == chart.page("fitted_c").rows
    conditions = ("Containing tile", "Receiver omitted", "Time-shift control")
    assert Counter((row.dataset, row.decision) for row in rows if row.series == "candidate") == {
        (condition, "withheld"): 8 for condition in conditions
    }
    assert Counter(
        row.dataset for row in rows if row.series == "diagnostic" and row.error_km is not None
    ) == dict.fromkeys(conditions, 5)
    for condition in conditions:
        assert len({row.recording for row in rows if row.dataset == condition}) == 8


def test_portable_gate_plot_preserves_false_publications_and_execution_failures():
    scopes = {chart.id: chart for chart in charts.charts(["portable_gate"])}
    past = scopes["portable_gate-historical"]
    fresh = scopes["portable_gate-fresh"]
    for arm in ARMS:
        wrong = [
            row
            for row in past.page(arm).rows
            if row.dataset == "Correct region omitted" and row.series == "candidate"
        ]
        assert len(wrong) == 2
        assert all(row.decision == "published" and row.error_km > 80 for row in wrong)
        outcomes = Counter(
            (row.dataset, row.decision) for row in fresh.page(arm).rows if row.series == "candidate"
        )
        assert outcomes == {
            ("Correct tile supplied", "published"): 2,
            ("Correct region omitted", "timed_out"): 1,
            ("Correct region omitted", "failed"): 1,
            ("Shuffled candidates · no geographic truth", "withheld"): 1,
        }


def test_armijo_tail_plot_keeps_held_and_diagnostic_recordings_in_distinct_scopes():
    scopes = {chart.id: chart for chart in charts.charts(["v5_armijo_tail"])}
    held = scopes["v5_armijo_tail-confirmation"]
    diagnostics = scopes["v5_armijo_tail-diagnostics"]
    assert held.cases == ("DS26-0313", "DS26-0080", "DS26-0078", "DS26-0231")
    assert diagnostics.cases == ("DS26-0152", "DS26-0283", "DS26-0092")
    for arm in ARMS:
        for scope in (held, diagnostics):
            rows = scope.page(arm).rows
            assert Counter(row.series for row in rows) == dict.fromkeys(
                (*ROLES, "one", "stock", "all_visits"), len(scope.cases)
            )
            assert all(row.decision == "published" for row in rows if row.series == "one")
