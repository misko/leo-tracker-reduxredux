"""Build position charts from the convergence studies' saved predictions."""

import gzip
import json
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from itertools import product
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, read_predictions
from ..position_figure import Mark
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import short_receiver_figures as shared
from .short_receiver_figures import SMOKE, TIMING, Page, Study

REPORT = corpus.REPO / "reports/2026_11_19_receiver_convergence"
PHASE = "v5_two_refresh"
LIKELIHOOD = "v5_likelihood_reuse"
ANCHOR = "periodic_anchor"
REGION = "region_challenge"
TRACK = "robust_orbit_fit"
SECANT = "v5_secant_fit"
CONDITIONING = "conditioned_cfo_bank"
CONDITIONING_RETRY = "conditioned_cfo_retry"
COMBINED = "v5_secant_two_refresh"
FRESH_CONTROL = "joint_pass_id"
TRACK_TRANSFER = "robust_em"
RAW_TRACK = "raw_orbit_fit"
PHASE_SEED = "phase-refresh-confirm-v1:"
TRACK_CONFIRM = (
    "DS26-0189",
    "DS26-0231",
    "DS26-0243",
    "DS26-0223",
    "DS26-0257",
    "DS26-0201",
    "DS26-0150",
    "DS26-0241",
)
PHASE_FILES = (f"{PHASE}.jsonl.gz", "orbit_projector.jsonl.gz", "receipt.json")
CONFIRM_BINDINGS = ("plan.json", "prediction-lock.json", "original-v5-inputs.json")
PHASE_CONFIRM_FILES = (*PHASE_FILES, *CONFIRM_BINDINGS)
ANCHOR_VARIANTS = ("periodic-reference-64", "ordinary-native-control", "capture-era-control")
ANCHOR_FILES = (
    "positions.jsonl.gz",
    "ordinary-control-positions.jsonl.gz",
    "capture-era-control-positions.jsonl.gz",
)
FRESH_METHODS = (REGION, FRESH_CONTROL)
FRESH_COHORTS = ("exact", "perturbed")
TRACK_FILES = (
    "positions.jsonl.gz",
    "stock-positions.jsonl.gz",
    "wrong-region.jsonl.gz",
    "stock-wrong-region.jsonl.gz",
    "prediction-lock.json",
)
FRESH_FILES = (
    "predictions.jsonl.gz",
    "prediction-lock.json",
    "source-lock.json",
    "input-lock.json",
    *(
        f"{file}-{cohort}.json"
        for file, cohort in product(
            ("offers", "labels", "cohort-lock", "capture-manifest"), FRESH_COHORTS
        )
    ),
)
TRACK_TRANSFER_FILES = (
    "plan.json",
    "predictions.jsonl.gz",
    "source-lock.json",
    "prediction-lock.json",
    "scores.json",
    "score-lock.json",
)
RAW_TRACK_FILES = ("positions.jsonl.gz", "control-positions.jsonl.gz", "prediction-lock.json")
COMBINED_FILES = (
    "positions.jsonl.gz",
    "stock-positions.jsonl.gz",
    "prediction-lock.json",
    "source-lock.json",
)
SECANT_TIMING_FILES = (
    "secant-positions.jsonl.gz",
    "reference-positions.jsonl.gz",
    "seal.json",
    "prediction-lock.json",
)
SECANT_CONFIRM_FILES = (
    f"{SECANT}.jsonl.gz",
    "orbit_projector.jsonl.gz",
    "receipt.json",
    *CONFIRM_BINDINGS,
)
REGION_STUDY = Study(
    "Competing region hypotheses on matched roof recordings",
    "Compare the supplied 25 km square with eight neighboring squares on the same withheld "
    "probes. The archived joint-pass fit uses the same supplied region and native inputs.",
    "region-challenge/matched-tile.jsonl.gz",
    wrong="region-challenge/omitted-tile.jsonl.gz",
)
TRACK_STUDY = Study(
    "Robust fit with orbit-specific corrections",
    "Use anonymous GLRT tracks and causal orbits. The control is the original robust fit on "
    "the same archived track projection and original 25 km tile.",
    "track-fit/positions.jsonl.gz",
    wrong="track-fit/wrong-region.jsonl.gz",
)

GROUPS = {
    ANCHOR: ("anchors", (*ANCHOR_FILES, "prediction-lock.json", "schedule-receipts.json")),
    LIKELIHOOD: ("likelihood", ("positions.jsonl.gz", "stock-positions.jsonl.gz", "receipt.json")),
    PHASE: ("phase-budget", PHASE_FILES),
    REGION: (
        "region-challenge",
        ("matched-tile.jsonl.gz", "omitted-tile.jsonl.gz", "source-lock.json"),
    ),
    TRACK: ("track-fit", TRACK_FILES),
    SECANT: ("position-fit", SECANT_TIMING_FILES),
    CONDITIONING: ("conditioning", ("positions.jsonl.gz", "qualification.json")),
    CONDITIONING_RETRY: ("conditioning/whole-retry", ("positions.jsonl.gz", "qualification.json")),
    FRESH_CONTROL: ("fresh-transfer", FRESH_FILES),
    TRACK_TRANSFER: ("track-transfer", TRACK_TRANSFER_FILES),
    RAW_TRACK: ("raw-orbit-fit", RAW_TRACK_FILES),
    COMBINED: ("combined-fit", COMBINED_FILES),
}


def available(evidence=REPORT):
    evidence = Path(evidence)
    measured = [
        method for method, (folder, files) in GROUPS.items() if _present(evidence / folder, files)
    ]
    if PHASE not in measured and _present(evidence / "phase-confirmation", PHASE_CONFIRM_FILES):
        measured.append(PHASE)
    if SECANT not in measured and _present(evidence / "secant-confirmation", SECANT_CONFIRM_FILES):
        measured.append(SECANT)
    if REGION not in measured and FRESH_CONTROL in measured:
        measured.append(REGION)
    return measured


def _present(folder, files):
    return all((folder / filename).is_file() for filename in files)


def _sealed(folder, receipt, filename):
    path = folder / filename
    shared._verify_seal(path, receipt["files"][filename])
    return path


def _records(path, cases, field, value):
    records = read_predictions(path)
    shared._exact(records, cases, path)
    if any(record.get(field) != value for record in records.values()):
        raise ValueError(f"{path} has an unexpected {field}")
    return records


def _roof(
    arm, method, title, caption, candidate, stock=None, other=None, *, name=None, additional=None
):
    refs = shared._frozen_roof()[0]
    samples = sorted(candidate)
    if stock is not None:
        shared._exact(stock, samples, "paired stock")
    if other is not None:
        shared._exact(other, samples, "matched additional control")
    rows = shared._visible_marks(
        [refs[k] for k in samples], candidate, method, arm, stock, other, additional=additional
    )
    return Page(name or method, method, title, caption, rows)


def confirmation_cases():
    eligible = set(shared._frozen_roof()[0]) - set(TIMING)
    ds26 = sorted(
        (case for case in eligible if case.startswith("DS26-")),
        key=lambda case: sha256(f"{PHASE_SEED}{case}".encode()).hexdigest(),
    )[:16]
    return tuple(ds26 + sorted(case for case in eligible if case.startswith("DS29-")))


def _independent_plan(folder, receipt, cases, predictions):
    plan = shared._json(_sealed(folder, receipt, "plan.json"))
    seal = shared._json(_sealed(folder, receipt, "prediction-lock.json"))
    original = shared._json(_sealed(folder, receipt, "original-v5-inputs.json"))
    shared._exact(seal["cases"], cases, "confirmation prediction seal")
    shared._exact(original, cases, "confirmation v5 input pairs")
    if any(
        seal["files"].get(name) != receipt["files"][name] for name in (*predictions, "plan.json")
    ):
        raise ValueError("confirmation prediction lock differs from the scored archive")
    shared._exact(plan["timing_cases"], TIMING, "confirmation timing exclusion")
    ds26 = [case for case in cases if case.startswith("DS26-")]
    if plan["ds26_in_hash_order"] != ds26 or plan["ds29"] != list(cases[len(ds26) :]):
        raise ValueError("confirmation plan differs from the prespecified roster")
    _, inputs = shared._frozen_roof()
    if plan["case_bindings"] != {
        case: {f"{kind}_sha256": inputs[case][kind]["sha256"] for kind in ("native", "catalog")}
        for case in cases
    }:
        raise ValueError("confirmation differs from the frozen native and TLE inputs")
    for case in cases:
        shared._exact(original[case], ROLES, f"{case} original v5 input roles")
    return plan


def _phase_page(arm, folder, cases, *, confirmation):
    receipt = shared._json(folder / "receipt.json")
    shared._exact(receipt["cases"], cases, "phase replay receipt")
    if confirmation:
        plan = _independent_plan(folder, receipt, cases, PHASE_FILES[:2])
        if plan["hash_prefix"] != PHASE_SEED:
            raise ValueError("phase confirmation plan changed the hash selection")
    candidate, stock = [
        shared._read_bound(_sealed(folder, receipt, filename), cases, ("method", method))
        for filename, method in zip(PHASE_FILES[:2], (PHASE, "orbit_projector"), strict=True)
    ]
    required = ("input_sha256",) if confirmation else ("input_sha256", "cpu")
    shared._exact_pair(candidate, stock, cases, required)
    sources = receipt["sources" if confirmation else "source"]
    measured = candidate.values() if confirmation else (*candidate.values(), *stock.values())
    if not sources or any(row.get("source_sha256") != sources for row in measured):
        raise ValueError("phase study records differ from their frozen scientific sources")
    if confirmation:
        name = f"{PHASE}-confirmation"
        title = "Two early phase refreshes · independent roof confirmation"
        caption = (
            "16 DS26 recordings selected by a frozen ID hash and five other DS29 recordings. "
            "The control is the archived full-budget compact projector on the identical inputs."
        )
    else:
        name = PHASE
        title = "Two early phase refreshes · paired timing"
        caption = (
            "Six same-CPU pairs through the compact v5 cavity fit. The original search branches, "
            "complete detector factors, supplied tile and late validation budgets are shared."
        )
        if (interrupted := folder / "interrupted-attempt.json").is_file():
            attempt = shared._json(interrupted)
            if attempt["id"] != "DS26-0122" or any(
                attempt[k] != candidate[attempt["id"]][k]
                for k in ("method", "cpu", "input_sha256", "source_sha256")
            ):
                raise ValueError("phase timing retry changed the interrupted attempt's input")
            caption += " DS26-0122 timing uses a same-core retry."
    return _roof(arm, PHASE, title, caption, candidate, stock, name=name)


def _phase_pages(arm, evidence):
    pages = []
    for name, cases, confirmation in (
        ("phase-budget", TIMING, False),
        ("phase-confirmation", confirmation_cases(), True),
    ):
        folder = evidence / name
        required = PHASE_CONFIRM_FILES if confirmation else PHASE_FILES
        if _present(folder, required):
            pages.append(_phase_page(arm, folder, cases, confirmation=confirmation))
    return pages


def _likelihood(arm, evidence):
    folder = evidence / "likelihood"
    receipt = shared._json(folder / "receipt.json")
    cases = receipt["cases"]
    if len(set(cases)) != len(cases) or not set(SMOKE) <= set(cases) <= {
        *SMOKE,
        "DS26-0122",
        "DS29-0174",
    }:
        raise ValueError("likelihood replay used an unexpected primary or corroboration roster")
    comparisons = {item["id"]: item["input_sha256"] for item in receipt["comparisons"]}
    shared._exact(comparisons, cases, "likelihood matched input declarations")
    if len(receipt["comparisons"]) != len(cases):
        raise ValueError("likelihood replay repeats a paired comparison")
    pair = []
    for filename, run, method in (
        ("positions.jsonl.gz", "candidate", LIKELIHOOD),
        ("stock-positions.jsonl.gz", "control", "orbit_projector"),
    ):
        path = folder / filename
        shared._verify_seal(path, receipt["runs"][run]["position_sha256"])
        rows = _records(path, cases, "method", method)
        if any(rows[k].get("input_sha256") != comparisons[k] for k in cases):
            raise ValueError(f"{path} differs from its paired input receipts")
        pair.append(rows)
    return _roof(
        arm,
        LIKELIHOOD,
        "Reuse identical likelihood calculations in compact v5",
        "Paired compact v5 runs through the cavity stage on the same complete archived detector "
        "factors. The measured cohorts retain the original four v5 reference positions.",
        *pair,
    )


def _anchors(arm, evidence):
    folder = evidence / "anchors"
    receipt = shared._json(folder / "prediction-lock.json")
    shared._exact(receipt["cases"], TIMING, "periodic anchor prediction seal")
    if receipt["schedule"] != 64:
        raise ValueError("periodic anchor replay differs from the fixed schedule")
    mixtures = [
        _records(_sealed(folder, receipt, name), TIMING, "variant", variant)
        for name, variant in zip(ANCHOR_FILES, ANCHOR_VARIANTS, strict=True)
    ]
    _, frozen = shared._frozen_roof()
    schedule_rows = shared._json(folder / "schedule-receipts.json")
    shared._exact(schedule_rows, TIMING, "periodic anchor schedule")
    ordinary = shared._json(shared.ORDINARY / "recording-receipts.json")["recordings"]
    for case in TIMING:
        composite, ordinary_stock, capture_stock = [rows[case] for rows in mixtures]
        factors = composite["factor_sha256"]
        if (
            composite["method"] != ANCHOR
            or factors["ordinary-native-control"] != ordinary[case]["native_sha256"]
            or factors["capture-era-control"] != frozen[case]["native"]["sha256"]
            or not composite.get("schedule_sha256")
            or composite["schedule_sha256"] != schedule_rows[case]["schedule_sha256"]
            or factors != schedule_rows[case]["factor_sha256"]
        ):
            raise ValueError(
                f"periodic anchor replay differs from frozen input authority for {case}"
            )
        for record, variant in zip(
            (composite, ordinary_stock, capture_stock), ANCHOR_VARIANTS, strict=True
        ):
            if (
                record["factor_sha256"] != factors
                or record["native_sha256"] != factors[variant]
                or record["catalog_sha256"] != frozen[case]["catalog"]["sha256"]
                or record["schedule_sha256"] != composite["schedule_sha256"]
            ):
                raise ValueError(f"periodic anchor factor input differs for {case}")
    return _roof(
        arm,
        ANCHOR,
        "One capture-era reference sweep in every 64",
        "The complete hybrid factor files replace selected ordinary visits with capture-era "
        "factors. Both controls use the same compact fitter. Bounded raw checks cover the first "
        "selected sweep on two recordings.",
        *mixtures,
    )


def _region_pages(arm, evidence):
    pages = []
    if _present(evidence / "fresh-transfer", FRESH_FILES):
        pages.extend(_fresh_pages(arm, evidence, REGION))
    root, files = GROUPS[REGION]
    if not _present(evidence / root, files):
        return pages
    primary, records = shared._roof_page(arm, REGION, REGION_STUDY, evidence)
    source = shared._json(evidence / root / "source-lock.json")["region_challenge.py"]
    if any(row.get("implementation_sha256") != source for row in records.values()):
        raise ValueError("region challenge positions changed their sealed implementation")
    matching = shared._read_bound(
        shared.REPORT / "joint-pass/matched-tile.jsonl.gz",
        TIMING,
        ("method", "joint_pass_id"),
        mode="matched-tile",
    )
    shared._exact_pair(records, matching, TIMING, ("offer", "native_sha256", "catalog_sha256"))
    primary = _roof(arm, REGION, primary.title, primary.subtitle, records, matching)
    wrong = shared._wrong_page(arm, REGION, REGION_STUDY, evidence, records)
    archived_wrong = shared._read_bound(
        shared.REPORT / "joint-pass/omitted-tile.jsonl.gz",
        tuple(shared.cold_missing.CASES),
        ("method", "joint_pass_id"),
        mode="omitted-tile",
    )
    current_wrong = read_predictions(evidence / REGION_STUDY.wrong)
    keys = ("offer", "query_sha256", "native_sha256", "catalog_sha256")
    shared._exact_pair(current_wrong, archived_wrong, archived_wrong, keys)
    wrong = _wrong_control(arm, wrong, matching, archived_wrong)
    return [primary, wrong, *pages]


def _wrong_control(arm, page, stock, wrong_stock):
    refs = shared._frozen_roof()[0]
    rows = list(page.rows)
    for cohort, recordings in (
        ("Original roof tile supplied", {k: stock[k] for k in wrong_stock}),
        ("Correct roof region omitted", wrong_stock),
    ):
        rows.extend(
            Mark(
                cohort,
                refs[case]["recording"],
                "stock",
                mark.decision,
                mark.error_km,
            )
            for case, record in recordings.items()
            for mark in shared._visible_marks([refs[case]], {case: record}, page.method, arm)
            if mark.series == "one"
        )
    return replace(page, rows=rows)


def _track_pages(arm, evidence):
    folder = evidence / "track-fit"
    roster = (*TIMING, *TRACK_CONFIRM)
    receipt = shared._json(folder / "prediction-lock.json")
    for name, cases in (
        ("timing", TIMING),
        ("confirmation", TRACK_CONFIRM),
        ("wrong-region", ("DS26-0036",)),
    ):
        shared._exact(receipt["cases"][name], cases, f"robust track-fit {name} cases")
    candidate = shared._read_bound(
        _sealed(folder, receipt, "positions.jsonl.gz"), roster, ("method", TRACK)
    )
    stock = shared._read_bound(
        _sealed(folder, receipt, "stock-positions.jsonl.gz"), roster, ("method", "robust_em")
    )
    shared._exact_pair(candidate, stock, roster, ("observation_sha256", "tile", "input_sha256"))
    pages = []
    for name, cases in ((TRACK, TIMING), (f"{TRACK}-confirmation", TRACK_CONFIRM)):
        for case in cases:
            row = candidate[case]
            if row["mode"] != "matched-tile":
                raise ValueError(f"track-fit received a different offered tile for {case}")
        title = TRACK_STUDY.title
        if cases == TRACK_CONFIRM:
            title = "Orbit-aware fit · eight additional DS26 recordings"
        pages.append(
            _roof(
                arm,
                TRACK,
                title,
                TRACK_STUDY.caption,
                {k: candidate[k] for k in cases},
                {k: stock[k] for k in cases},
                name=name,
            )
        )
    wrong_path = _sealed(folder, receipt, "wrong-region.jsonl.gz")
    wrong = shared._wrong_page(arm, TRACK, TRACK_STUDY, evidence, candidate, single_alt=True)
    wrong_stock = shared._read_bound(
        _sealed(folder, receipt, "stock-wrong-region.jsonl.gz"),
        ("DS26-0036",),
        ("method", "robust_em"),
        mode="wrong-region",
    )
    shared._exact_pair(
        read_predictions(wrong_path), wrong_stock, wrong_stock, ("observation_sha256", "tile")
    )
    pages.append(_wrong_control(arm, wrong, stock, wrong_stock))
    if _present(evidence / "track-transfer/robust-orbit-fit", TRACK_TRANSFER_FILES):
        pages.extend(_track_transfer(arm, evidence, TRACK))
    return pages


def _secant_timing(arm, evidence):
    folder = evidence / "position-fit"
    receipt = shared._json(folder / "prediction-lock.json")
    shared._verify_seal(folder / "seal.json", receipt["source_seal_sha256"])
    plan = shared._json(folder / "seal.json")["roster"]
    shared._exact(plan, TIMING, "secant frozen schedule")
    for pair in plan.values():
        shared._exact(pair, ("reference", "secant"), "secant within-recording pair")
    shared._exact(receipt["cases"], TIMING, "secant fixed paired schedule")
    candidate, stock = [
        shared._read_bound(_sealed(folder, receipt, filename), TIMING, ("variant", method))
        for filename, method in (
            ("secant-positions.jsonl.gz", SECANT),
            ("reference-positions.jsonl.gz", "compact-v5-bounded-gn"),
        )
    ]
    shared._exact_pair(candidate, stock, TIMING, ("input_sha256", "cpu", "source_seal_sha256"))
    if any(
        row["source_seal_sha256"] != receipt["source_seal_sha256"] for row in candidate.values()
    ):
        raise ValueError("secant paired position records differ from the frozen source")
    return _roof(
        arm,
        SECANT,
        "Safeguarded secant steps in the compact v5 position fit",
        "The secant derivative and stock bounded solver use the same full capture-era native "
        "GLRT factors and all five outer phase passes.",
        candidate,
        stock,
    )


def _secant_pages(arm, evidence):
    pages = []
    if _present(evidence / "position-fit", SECANT_TIMING_FILES):
        pages.append(_secant_timing(arm, evidence))
    folder = evidence / "secant-confirmation"
    if _present(folder, SECANT_CONFIRM_FILES):
        independent = confirmation_cases()
        cases = (*independent[:4], *independent[16:20])
        receipt = shared._json(folder / "receipt.json")
        shared._exact(receipt["cases"], cases, "secant confirmation schedule")
        plan = _independent_plan(folder, receipt, cases, SECANT_CONFIRM_FILES[:2])
        shared._verify_seal(
            evidence / "phase-confirmation/roster.json", plan["parent_roster_sha256"]
        )
        shared._verify_seal(
            evidence / "position-fit/seal.json", plan["position_fit_source_receipt_sha256"]
        )
        candidate, stock = [
            shared._read_bound(_sealed(folder, receipt, filename), cases, ("method", method))
            for filename, method in zip(
                SECANT_CONFIRM_FILES[:2], (SECANT, "orbit_projector"), strict=True
            )
        ]
        shared._exact_pair(candidate, stock, cases, ("input_sha256",))
        if any(
            row.get("source_sha256") != receipt["sources"]
            or row.get("implementation_sha256") != plan["cli_implementation_sha256"]
            for row in candidate.values()
        ):
            raise ValueError("secant confirmation changed the frozen scientific source")
        pages.append(
            _roof(
                arm,
                SECANT,
                "Secant position steps · independent roof confirmation",
                "Four DS26 recordings in frozen hash order and four DS29 recordings in lexical "
                "order. Stock is the complete compact projector on the same recorded inputs.",
                candidate,
                stock,
                name=f"{SECANT}-confirmation",
            )
        )
    return pages


def _combined(arm, evidence):
    folder = evidence / "combined-fit"
    receipt = shared._json(folder / "prediction-lock.json")
    shared._verify_seal(folder / "source-lock.json", receipt["source_lock_sha256"])
    cases = receipt["cases"]
    if len(set(cases)) != len(cases) or set(cases) not in (set(SMOKE), set(TIMING)):
        raise ValueError("combined fit differs from its smoke or expanded timing roster")
    candidate, stock = [
        shared._read_bound(_sealed(folder, receipt, filename), cases, ("method", method))
        for filename, method in zip(COMBINED_FILES[:2], (COMBINED, "orbit_projector"), strict=True)
    ]
    shared._exact_pair(candidate, stock, cases, ("input_sha256",))
    additional = {}
    for key, method, filename in (
        ("all_visits", PHASE, "two-refresh-positions.jsonl.gz"),
        ("one_native_factors", SECANT, "secant-positions.jsonl.gz"),
    ):
        if filename in receipt["files"]:
            records = shared._read_bound(
                _sealed(folder, receipt, filename), cases, ("method", method)
            )
            shared._exact_pair(candidate, records, cases, ("input_sha256",))
            additional[key] = records
    return _roof(
        arm,
        COMBINED,
        "Secant position steps with two early phase refreshes",
        "Apply both changes together and compare their complete native-to-cavity result with "
        "stock on the same recorded GLRT, causal catalogue and original 25 km tile. "
        "Individual changes appear when paired receipts are available.",
        candidate,
        stock,
        additional=additional,
    )


def _conditioning(arm, evidence, method=CONDITIONING):
    earlier = method == CONDITIONING_RETRY
    folder = evidence / GROUPS[method][0]
    candidate = _records(folder / "positions.jsonl.gz", SMOKE, "method", CONDITIONING)
    qualification = shared._json(folder / "qualification.json")
    shared._exact(qualification["cases"], SMOKE, "conditioned detector acquisition schedule")
    control = folder / "control-positions.jsonl.gz"
    stock = (
        _records(control, SMOKE, "method", "conditioned_cfo_capture_control")
        if control.is_file()
        else None
    )
    inputs = shared._frozen_roof()[1]
    for case in SMOKE:
        source = inputs[case]["native"]["sha256"]
        row = candidate[case]
        if row.get("source_archive_sha256") != source:
            raise ValueError(f"conditioned detector trial has an unmatched archive for {case}")
        if stock is None:
            metrics = dict(row["result"]["metrics"])
            if metrics.pop("position_attempted", None) is not False:
                raise ValueError("conditioned position fits require a matched control")
            if metrics != qualification["cases"][case]:
                raise ValueError("detector-only position row differs from its stage measurement")
            continue
        control_row = stock[case]
        if (
            earlier
            or control_row["source_archive_sha256"] != source
            or control_row["input_sha256"] != f"sha256:{source}"
            or row["result"]["metrics"]["control_input_sha256"] != control_row["input_sha256"]
        ):
            raise ValueError(
                f"conditioned position replay differs from its archive control for {case}"
            )
        split_receipts = row["detector_receipts_sha256"]
        shared._exact(
            split_receipts,
            ("development", "holdout", "extension", "blind"),
            "conditioned IQ receipts",
        )
        for split, digest in split_receipts.items():
            shared._verify_seal(folder / f"{case}-{split}.json.gz", digest)
    caption = (
        "The candidate replaces sampled visits with fresh IQ results and uses archived detections "
        "elsewhere. The capture-era position control uses the complete archived detections."
        if stock is not None
        else "The sampled raw windows tested detector payload parity and work. All downstream "
        "positions are unmeasured."
    )
    title = "Conditioned CFO refinement on sampled raw IQ"
    if earlier:
        title = "Conditioned CFO with whole-acquisition retry"
        saving = qualification["pooled_fraction_saved"]["full_cpu_s"]
        caption += f" Pooled detector CPU changed by {-saving:+.1%}."
    return _roof(
        arm,
        method,
        title,
        caption,
        candidate,
        stock,
    )


def _raw_track(arm, evidence):
    folder = evidence / "raw-orbit-fit"
    receipt = shared._json(folder / "prediction-lock.json")
    shared._exact(receipt["cases"], TIMING, "raw track fit replay roster")
    candidate, stock = [
        _records(_sealed(folder, receipt, filename), TIMING, "method", method)
        for filename, method in zip(RAW_TRACK_FILES[:2], (TRACK, TRACK_TRANSFER), strict=True)
    ]
    shared._exact_pair(
        candidate,
        stock,
        TIMING,
        (
            "native_sha256",
            "catalog_sha256",
            "observation_sha256",
            "input_sha256",
            "tile",
            "capture_authority",
            "track_config_sha256",
            "tracker_source_sha256",
        ),
    )
    _, frozen = shared._frozen_roof()
    ordinary = shared._json(shared.ORDINARY / "recording-receipts.json")["recordings"]
    for case in TIMING:
        binding = frozen[case]
        previously_replayed = case in SMOKE
        variant = (
            "session-verified-iq-factor-reuse"
            if previously_replayed
            else "qualified-ordinary-factor-reuse"
        )
        for row in (candidate[case], stock[case]):
            if (
                row["native_sha256"] != ordinary[case]["native_sha256"]
                or row["catalog_sha256"] != binding["catalog"]["sha256"]
                or any(row["tile"][key] != binding["regions"][0][key] for key in ("id", "center"))
                or row["mode"] != "matched-tile"
                or row["cohort"] != "ordinary-iq-factors"
                or row["variant"] != variant
                or row["acquired_in_this_measurement"] is not False
                or (row["upstream_iq_replay"] is not None) != previously_replayed
            ):
                raise ValueError(f"raw orbit fit changed the saved IQ factor authority on {case}")
    groups = (
        (
            "previously-replayed",
            "Orbit-aware track fit on two previously replayed IQ recordings",
            "Earlier whole-IQ replays confirmed these ordinary detector factors.",
            SMOKE,
        ),
        (
            "stored",
            "Orbit-aware track fit on four stored ordinary factor archives",
            "Use the authenticated whole-recording ordinary detector factors.",
            tuple(case for case in TIMING if case not in SMOKE),
        ),
    )
    return [
        _roof(
            arm,
            RAW_TRACK,
            title,
            f"{caption} Both fits rebuild the anonymous tracks and begin at identical packets.",
            {k: candidate[k] for k in cases},
            {k: stock[k] for k in cases},
            name=f"{RAW_TRACK}-{name}",
        )
        for name, title, caption, cases in groups
    ]


def _location_rows(arm, samples):
    labels = {
        "present": "Correct tile supplied",
        "missing": "Correct region omitted",
        "shuffle": "Shuffled detections · no site",
    }
    groups = {condition: [] for condition in labels}
    for case, condition, truth, result, eligible in samples:
        endpoint = result.get("arms", {}).get(arm, {})
        published, forced = endpoint.get("latlon"), endpoint.get("forced_latlon")
        state = result["status"]
        if not eligible:
            forced = forced if forced is not None else published
            published, state = None, "unavailable"
        rows = groups[condition]
        publication = (
            "published" if published is not None else ("withheld" if state == "ok" else state)
        )
        rows.append(
            Mark(labels[condition], case, "candidate", publication, distance_km(published, truth))
        )
        diagnostic = "diagnostic" if forced is not None else "no_estimate"
        rows.append(
            Mark(labels[condition], case, "diagnostic", diagnostic, distance_km(forced, truth))
        )
    return [
        row
        for rows in groups.values()
        for row in rows
        if row.series != "diagnostic"
        or any(m.series == "diagnostic" and m.error_km is not None for m in rows)
    ]


def _fresh_roster(labels):
    conditions = Counter(item["condition"] for item in labels.values())
    paired = {
        condition: {
            item["capture_id"]: item["latlon"]
            for item in labels.values()
            if item["condition"] == condition
        }
        for condition in ("present", "missing")
    }
    shuffled = next((item for item in labels.values() if item["condition"] == "shuffle"), {})
    if (
        conditions != {"present": 4, "missing": 4, "shuffle": 1}
        or paired["present"] != paired["missing"]
        or len(paired["present"]) != 4
        or None in paired["present"].values()
        or shuffled["capture_id"] in paired["present"]
        or shuffled["latlon"] is not None
    ):
        raise ValueError(
            "fresh transfer needs four paired sites and one geographic null per cohort"
        )


def _fresh_pages(arm, evidence, method):
    folder = evidence / "fresh-transfer"
    seal = shared._json(folder / "prediction-lock.json")
    raw = folder / "predictions.jsonl.gz"
    shared._verify_seal(raw, seal["predictions_sha256"])
    shared._verify_seal(folder / "input-lock.json", seal["input_lock_sha256"])
    shared._exact(seal["methods"], FRESH_METHODS, "fresh transfer methods")
    input_lock = shared._json(folder / "input-lock.json")
    shared._verify_seal(folder / "source-lock.json", input_lock["sources_sha256"])
    with gzip.open(raw, "rt") as stream:
        records = list(map(json.loads, stream))
    predictions = {(r["cohort"], r["method"], r["id"]): r for r in records}
    expected = set()
    pages = []
    captures = set()
    for cohort in FRESH_COHORTS:
        labels_path = folder / f"labels-{cohort}.json"
        offers_path = folder / f"offers-{cohort}.json"
        receipt_path = folder / f"cohort-lock-{cohort}.json"
        manifest_path = folder / f"capture-manifest-{cohort}.json"
        shared._verify_seal(receipt_path, input_lock["cohort_locks"][cohort])
        binding = shared._json(receipt_path)
        shared._verify_seal(labels_path, binding["labels_sha256"])
        shared._verify_seal(offers_path, binding["offers_sha256"])
        shared._verify_seal(manifest_path, binding["manifest_sha256"])
        native = shared._json(manifest_path)["cases"]
        labels = shared._json(labels_path)
        offers = shared._json(offers_path)
        offered = {r["id"]: r for r in offers}
        shared._exact(labels, offered, f"fresh {cohort} labels")
        shared._exact([r["id"] for r in offers], seal["cases"][cohort], f"fresh {cohort} offers")
        _fresh_roster(labels)
        current = {r["capture_id"] for r in labels.values()}
        if current & captures:
            raise ValueError("transfer cohorts share a synthetic acquisition")
        captures.update(current)
        expected.update(product((cohort,), FRESH_METHODS, labels))
        samples, controls = [], []
        for ident, label in labels.items():
            offer = offered[ident]
            for selected, cohort_rows in ((method, samples), (FRESH_CONTROL, controls)):
                prediction = predictions[cohort, selected, ident]
                result = prediction["result"]
                validate_result(result)
                if (
                    label["capture_id"] != offer["capture_id"]
                    or prediction["capture_id"] != label["capture_id"]
                    or prediction["tile"] != offer["tile"]
                    or prediction["mode"] != "supplied-tile"
                    or prediction["native_sha256"] != native[label["capture_id"]]
                    or prediction["catalog_sha256"] != binding["catalogue_sha256"]
                ):
                    raise ValueError(f"fresh {cohort} prediction differs from its sealed offer")
                cohort_rows.append(
                    (label["capture_id"], label["condition"], label["latlon"], result, True)
                )
        prefix = "Region challenge" if method == REGION else "Joint-pass control"
        rows = _location_rows(arm, samples)
        if method == REGION:
            rows.extend(
                replace(mark, series="stock")
                for mark in _location_rows(arm, controls)
                if mark.series == "candidate"
            )
        pages.append(
            Page(
                f"{method}-{cohort}-transfer",
                method,
                f"{prefix} · {cohort} synthetic observations",
                "Four independent synthetic sites have correct and omitted 25 km offers. "
                "The shuffle tests publication without geographic truth.",
                rows,
                scope="transfer",
            )
        )
    if set(predictions) != expected or len(records) != len(expected):
        raise ValueError("fresh transfer predictions differ from their prespecified method rosters")
    return pages


def _track_transfer(arm, evidence, method=TRACK_TRANSFER):
    folder = evidence / "track-transfer"
    if method == TRACK:
        folder /= "robust-orbit-fit"
    lock = shared._json(folder / "prediction-lock.json")
    score_lock = shared._json(folder / "score-lock.json")
    if score_lock["method"] != method or score_lock["plan_sha256"] != lock["plan_sha256"]:
        raise ValueError("track transfer score lock names a different method or plan")
    for filename, digest in (
        ("prediction-lock.json", score_lock["prediction_lock_sha256"]),
        ("scores.json", score_lock["scores_sha256"]),
        ("predictions.jsonl.gz", lock["predictions_sha256"]),
        ("plan.json", lock["plan_sha256"]),
        ("source-lock.json", lock["source_lock_sha256"]),
    ):
        shared._verify_seal(folder / filename, digest)
    plan = shared._json(folder / "plan.json")
    field = shared._json(shared.REPORT / "physical-transfer/plan.json")
    synthetic, _, _ = shared._fresh_evidence(shared.REPORT / "fresh-scenes")
    field_modes = {"supplied-correct": "supplied-tile", "omitted": "omitted-tile"}
    raw_field = {
        (r["original_case"], r["mode"]): r for r in field["cases"] if r["mode"] != "global"
    }
    conditions = {"present": "supplied-correct", "missing": "omitted", "shuffle": "shuffle"}
    bindings = {item["id"]: item for item in plan["queries"]}
    physical_bindings = {
        (item["target_key"], field_modes[item["mode"]]): ident
        for ident, item in bindings.items()
        if item["dataset"] == "starloc"
    }
    shared._exact(physical_bindings, raw_field, "frozen track transfer physical queries")
    roster = set(physical_bindings.values()) | set(synthetic)
    records = _records(folder / "predictions.jsonl.gz", roster, "method", method)
    shared._exact([r["id"] for r in plan["queries"]], roster, "track transfer queries")
    scored = shared._json(folder / "scores.json")["rows"]
    shared._exact([row["id"] for row in scored], roster, "track transfer scores")
    scores = {row["id"]: row for row in scored}
    if plan["truth_sha256"] != {
        "starloc": field["scoring_truth_sha256"],
        "synthetic_glrt": sha256(encoded(synthetic) + b"\n").hexdigest(),
    }:
        raise ValueError("track transfer labels differ from the frozen truth commitments")
    refs = {r["id"]: r for r in corpus.references("transfer124")}
    cases = {"starloc": [], "synthetic_glrt": []}
    for case, binding in bindings.items():
        row = records[case]
        score = scores[case]
        physical = binding["dataset"] == "starloc"
        if physical:
            original = raw_field[binding["target_key"], field_modes[binding["mode"]]]
            original_case = original["original_case"]
            group = original["site_group"]
            condition = "present" if original["mode"] == "supplied-tile" else "missing"
            truth = refs[original_case]["truth"]
            if (
                binding["target_key"] != original_case
                or binding["tile"]["center"] != original["tile_center"]
                or any(
                    binding[k] != original[k] for k in ("observation_sha256", "catalogue_sha256")
                )
            ):
                raise ValueError("track transfer changed the frozen StarLoc query")
        else:
            label = synthetic[case]
            group, condition, truth = label["capture_id"], label["condition"], label["latlon"]
            if binding["target_key"] != case:
                raise ValueError("track transfer synthetic query changed its label binding")
        dataset = "starloc" if physical else "synthetic_glrt"
        if (
            row["input_sha256"] != binding["input_sha256"]
            or binding["group"] != group
            or binding["dataset"] != dataset
            or binding["contract_eligible"] == physical
            or score["condition"] != conditions[condition]
            or score["contract_eligible"] != binding["contract_eligible"]
            or score["status"] != row["result"]["status"]
        ):
            raise ValueError("track transfer score differs from the sealed query or position")
        point = row["result"].get("arms", {}).get(arm, {})
        arm_score = score["arms"][arm]
        for endpoint, name in (("latlon", "issued"), ("forced_latlon", "forced")):
            if point.get(endpoint) != arm_score[name] or not shared._same_error(
                distance_km(point.get(endpoint), truth), arm_score[f"{name}_error_km"]
            ):
                raise ValueError("track transfer geographic error differs from its sealed position")
        cases[dataset].append((group, condition, truth, row["result"], not physical))
    new = method == TRACK
    prefix = "Orbit-aware robust fit" if new else "Robust track fit"
    slug = "robust-orbit-fit" if new else "robust-em"
    pages = [
        Page(
            f"{slug}-starloc",
            method,
            f"{prefix} at four measured StarLoc sites",
            "The available center-beacon CFO supplies one radio lane. These inputs fall outside "
            "the receiver's two-lane contract. Any coordinate is a numerical diagnostic.",
            _location_rows(arm, cases["starloc"]),
            scope="transfer",
        ),
        Page(
            f"{slug}-synthetic",
            method,
            f"{prefix} on four compatible synthetic sites",
            "The frozen synthetic GLRT includes the folded CFO observable. Each site is attempted "
            "with correct and omitted offers. The shuffled negative has no geographic truth.",
            _location_rows(arm, cases["synthetic_glrt"]),
            scope="transfer",
        ),
    ]
    if new and _present(folder.parent, TRACK_TRANSFER_FILES):
        shared._verify_seal(folder.parent / "plan.json", lock["plan_sha256"])
        old = _track_transfer(arm, evidence)[1]
        current = pages[1]
        matches = [replace(m, series="stock") for m in old.rows if m.series == "candidate"]
        pages[1] = replace(
            current,
            subtitle=f"{current.subtitle} The original robust fit uses the same queries.",
            rows=current.rows + matches,
        )
    return pages


def pages(arm, methods=None, evidence=REPORT):
    if arm not in ARMS:
        raise ValueError("select an available calibration arm")
    evidence = Path(evidence)
    measured = available(evidence)
    selected = list(dict.fromkeys(methods or measured))
    generators = {
        ANCHOR: _anchors,
        LIKELIHOOD: _likelihood,
        REGION: _region_pages,
        TRACK: _track_pages,
        SECANT: _secant_pages,
        CONDITIONING: _conditioning,
        CONDITIONING_RETRY: lambda arm, evidence: _conditioning(arm, evidence, CONDITIONING_RETRY),
        PHASE: _phase_pages,
        FRESH_CONTROL: lambda arm, evidence: _fresh_pages(arm, evidence, FRESH_CONTROL),
        TRACK_TRANSFER: _track_transfer,
        RAW_TRACK: _raw_track,
        COMBINED: _combined,
    }
    if not selected:
        raise ValueError("no completed convergence evidence is available")
    if missing := set(selected) - set(measured):
        raise ValueError(f"convergence evidence is unavailable for {sorted(missing)}")
    book = []
    for method in selected:
        result = generators[method](arm, evidence)
        book.extend(result if isinstance(result, list) else [result])
    return book


def generate(out, arms=ARMS, methods=None, *, evidence=REPORT):
    return shared.render(
        out,
        arms,
        lambda arm: pages(arm, methods, evidence),
        title="Receiver convergence position errors",
    )
