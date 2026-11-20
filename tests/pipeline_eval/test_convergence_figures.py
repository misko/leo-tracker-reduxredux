import csv
import gzip
import json
from collections import Counter
from dataclasses import replace
from hashlib import sha256

import pytest

from tools.pipeline_eval import figure_books
from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import convergence_figures as conv
from tools.pipeline_eval.qualification import short_receiver_figures as shared
from tools.pipeline_eval.scoring import ARMS, ROLES


def _save(path, content):
    path.write_bytes(encoded(content) + b"\n")
    return sha256(path.read_bytes()).hexdigest()


def _phase_pair(folder, cases, *, confirmation=False):
    folder.mkdir()
    refs, inputs = shared._frozen_roof()
    files = {}
    source = {"variant.py": "a" * 64}
    base = [
        {
            "id": ident,
            "native_sha256": inputs[ident]["native"]["sha256"],
            "catalog_sha256": inputs[ident]["catalog"]["sha256"],
            "input_sha256": sha256(ident.encode()).hexdigest(),
            "source_sha256": source,
            "cpu": 4,
            "result": {
                "status": "ok",
                "boundary": "Complete stored factors through the same cavity fit",
                "metrics": {},
                "arms": {arm: {"latlon": refs[ident]["truth"]} for arm in ARMS},
            },
        }
        for ident in cases
    ]
    if confirmation:
        plan = {
            "hash_prefix": conv.PHASE_SEED,
            "ds26_in_hash_order": cases[:16],
            "ds29": cases[16:],
            "timing_cases": conv.TIMING,
            "case_bindings": {
                r["id"]: {k: r[k] for k in ("native_sha256", "catalog_sha256")} for r in base
            },
        }
        files["plan.json"] = _save(folder / "plan.json", plan)
    for method in (conv.PHASE, "orbit_projector"):
        name = f"{method}.jsonl.gz"
        out = [dict(row, method=method) for row in base]
        if method == conv.PHASE:
            out[0]["result"] = {
                "status": "timed_out",
                "reason": "Worker deadline expired",
                "boundary": "Complete stored factors through the same cavity fit",
                "metrics": {},
            }
        raw = gzip.compress(b"".join(encoded(row) + b"\n" for row in out), mtime=0)
        (folder / name).write_bytes(raw)
        files[name] = sha256(raw).hexdigest()
    if confirmation:
        files["prediction-lock.json"] = _save(
            folder / "prediction-lock.json", {"cases": cases, "files": files}
        )
        files["original-v5-inputs.json"] = _save(
            folder / "original-v5-inputs.json",
            {case: {role: {"execution_sha256": "a" * 64} for role in ROLES} for case in cases},
        )
    source_key = "sources" if confirmation else "source"
    _save(folder / "receipt.json", {"cases": cases, "files": files, source_key: source})


def test_phase_scheduled_cohorts_and_timeout_are_kept_separate(tmp_path):
    independent = conv.confirmation_cases()
    assert not set(independent) & set(conv.TIMING)
    assert independent[:3] == ("DS26-0142", "DS26-0223", "DS26-0301")
    assert Counter(case[:4] for case in independent) == {"DS26": 16, "DS29": 5}
    _phase_pair(tmp_path / "phase-budget", conv.TIMING)
    _phase_pair(tmp_path / "phase-confirmation", independent, confirmation=True)
    timing, confirm = conv.pages("c0", [conv.PHASE], tmp_path)
    for page, expected in ((timing, 6), (confirm, 21)):
        assert Counter(r.series for r in page.rows) == dict.fromkeys(
            (*ROLES, "one", "stock"), expected
        )
        (timeout,) = [r for r in page.rows if r.decision == "timed_out"]
        assert timeout.error_km is None and timeout.series == "one"
    assert {x.recording for x in timing.rows}.isdisjoint(x.recording for x in confirm.rows)


def test_phase_figure_rejects_a_changed_sealed_record(tmp_path):
    folder = tmp_path / "phase-budget"
    _phase_pair(folder, conv.TIMING)
    path = folder / "orbit_projector.jsonl.gz"
    path.write_bytes(path.read_bytes() + b"replacement")
    with pytest.raises(ValueError, match="frozen content hash"):
        conv.pages("c0", [conv.PHASE], tmp_path)


def test_convergence_panel_exports_named_arm_and_local_index(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _phase_pair(evidence / "phase-budget", conv.TIMING)
    out = tmp_path / "out"
    entries = figure_books.generate(
        out, ["c0"], [conv.PHASE], panel="convergence", evidence=evidence
    )
    assert entries == json.loads((out / "manifest.json").read_bytes())
    (entry,) = entries
    assert entry["scope"] == "roof" and entry["arm"] == "c0"
    assert (out / entry["image"]).read_bytes().startswith(b"\x89PNG")
    assert (out / entry["pdf"]).read_bytes().startswith(b"%PDF")
    assert entry["image"] in (out / "index.html").read_text()
    with (out / entry["csv"]).open() as stream:
        records = list(csv.DictReader(stream))
    assert len(records) == 36
    assert sum(r["series"] == "one" and r["decision"] == "timed_out" for r in records) == 1


def test_convergence_export_rejects_a_roster_change_between_arms(tmp_path):
    _phase_pair(tmp_path / "phase-budget", conv.TIMING)
    (page,) = conv.pages("c0", [conv.PHASE], tmp_path)
    lost = page.rows[-1].recording
    shorter = replace(page, rows=[row for row in page.rows if row.recording != lost])
    books = {"c0": [page], "fitted_c": [shorter]}
    out = tmp_path / "bad-export"
    with pytest.raises(ValueError, match="different figure or recording rosters"):
        shared.render(out, ARMS, books.__getitem__, title="Test book")
    assert not (out / "manifest.json").exists()


@pytest.mark.parametrize("arm", ARMS)
def test_orbit_track_fit_keeps_timing_confirmation_and_wrong_offer_denominators(arm):
    timing, confirm, wrong, *_ = conv.pages(arm, [conv.TRACK])
    roles = (*ROLES, "one", "one_forced", "stock")
    assert Counter(r.series for r in timing.rows) == dict.fromkeys(roles, 6)
    assert Counter(r.series for r in confirm.rows) == dict.fromkeys(roles, 8)
    omitted = [r for r in wrong.rows if r.dataset == "Correct roof region omitted"]
    assert Counter(r.series for r in omitted) == {"candidate": 1, "diagnostic": 1, "stock": 1}
    assert all(r.error_km is None for r in omitted if r.series != "diagnostic")


@pytest.mark.parametrize("arm", ARMS)
def test_synthetic_challenge_keeps_perturbed_wrong_offer_publication(arm):
    roof, omitted, exact, perturbed = conv.pages(arm, [conv.REGION])
    assert sum(r.series == "one" and r.decision == "withheld" for r in roof.rows) == 6
    assert (
        sum(
            r.series == "candidate" and r.decision == "withheld"
            for r in omitted.rows
            if r.dataset == "Correct roof region omitted"
        )
        == 3
    )
    for page in (exact, perturbed):
        candidate = [r for r in page.rows if r.series == "candidate"]
        assert Counter(r.dataset for r in candidate) == {
            "Correct tile supplied": 4,
            "Correct region omitted": 4,
            "Shuffled detections · no site": 1,
        }
        assert not (set(ROLES) & {r.series for r in page.rows})
        assert sum(r.error_km is not None for r in page.rows if r.series == "stock") == 4
    wrong = [
        r
        for r in perturbed.rows
        if r.dataset == "Correct region omitted"
        and r.series == "candidate"
        and r.error_km is not None
    ]
    (false_fix,) = wrong
    assert false_fix.decision == "published" and false_fix.error_km > 75


@pytest.mark.parametrize("arm", ARMS)
def test_track_transfer_retains_contract_ineligible_measurements_and_compatible_controls(arm):
    physical, synthetic = conv.pages(arm, [conv.TRACK_TRANSFER])
    (upgraded_physical, upgraded_synthetic) = conv.pages(arm, [conv.TRACK])[-2:]
    for page in (physical, upgraded_physical):
        candidate = [r for r in page.rows if r.series == "candidate"]
        assert len(candidate) == 8
        assert all(r.decision == "unavailable" and r.error_km is None for r in candidate)
        assert any(r.error_km is not None for r in page.rows if r.series == "diagnostic")
    for page in (synthetic, upgraded_synthetic):
        candidate = [r for r in page.rows if r.series == "candidate"]
        assert len(candidate) == 9
        assert sum(r.decision == "published" for r in candidate) == 3
        assert all(r.error_km is None for r in candidate if r.dataset != "Correct tile supplied")
    assert len([r for r in upgraded_synthetic.rows if r.series == "stock"]) == 9


@pytest.mark.parametrize("arm", ARMS)
def test_roof_factor_studies_keep_anchor_controls_and_distinct_iq_provenance(arm):
    anchor, verified, stored = conv.pages(arm, [conv.ANCHOR, conv.RAW_TRACK])
    assert Counter(r.series for r in anchor.rows) == dict.fromkeys(
        (*ROLES, "one", "stock", "all_visits"), 6
    )
    for page, n in ((verified, 2), (stored, 4)):
        assert Counter(r.series for r in page.rows) == dict.fromkeys(
            (*ROLES, "one", "one_forced", "stock"), n
        )
    assert {r.recording for r in verified.rows}.isdisjoint(r.recording for r in stored.rows)


@pytest.mark.parametrize("arm", ARMS)
def test_conditioned_retry_is_a_detector_measurement_with_unmeasured_positions(arm):
    (page,) = conv.pages(arm, [conv.CONDITIONING_RETRY])
    assert page.method == conv.CONDITIONING_RETRY
    assert "+7.2%" in page.subtitle
    assert Counter(r.series for r in page.rows) == dict.fromkeys((*ROLES, "one"), 2)
    assert all(
        r.decision == "stage_only" and r.error_km is None for r in page.rows if r.series == "one"
    )


@pytest.mark.parametrize("arm", ARMS)
def test_conditioning_and_both_fit_budgets_export_measured_positions(arm):
    conditioned, combined = conv.pages(arm, [conv.CONDITIONING, conv.COMBINED])
    assert Counter(r.series for r in conditioned.rows) == dict.fromkeys((*ROLES, "one", "stock"), 2)
    assert [r.error_km for r in conditioned.rows if r.series == "one"] == [
        r.error_km for r in conditioned.rows if r.series == "stock"
    ]
    assert Counter(r.series for r in combined.rows) == dict.fromkeys(
        (*ROLES, "one", "stock", "all_visits", "one_native_factors"), 6
    )
    for role in ("one", "stock", "all_visits", "one_native_factors"):
        assert sum(r.series == role and r.decision == "published" for r in combined.rows) == 6


@pytest.mark.parametrize("arm", ARMS)
def test_secant_timing_and_phase_confirmation_keep_true_fixed_cohorts(arm):
    phase, confirmed = conv.pages(arm, [conv.PHASE])
    timing, secant_confirm = conv.pages(arm, [conv.SECANT])
    assert "DS26-0122 timing uses a same-core retry" in phase.subtitle
    assert timing.name == conv.SECANT
    assert secant_confirm.name == f"{conv.SECANT}-confirmation"
    for page, n in ((phase, 6), (timing, 6), (confirmed, 21), (secant_confirm, 8)):
        assert Counter(r.series for r in page.rows) == dict.fromkeys((*ROLES, "one", "stock"), n)
    assert {r.recording for r in phase.rows}.isdisjoint(r.recording for r in confirmed.rows)
    assert {r.recording for r in timing.rows}.isdisjoint(r.recording for r in secant_confirm.rows)
