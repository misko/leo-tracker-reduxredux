"""Render the short-receiver trials from their saved outcomes and frozen references."""

import gzip
import io
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from hashlib import sha256
from itertools import product
from math import isclose
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, write
from ..position_figure import Mark, draw, marks, save_png
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import cold_missing, cold_scenes, cold_transfer_figures, prototype_figures
from .prefix_figures import TIMING_IDS, csv_file

REPORT = corpus.REPO / "reports/2026_11_19_short_receiver"
ORDINARY = corpus.REPO / "reports/2026_11_19_receiver_frontend/ordinary"
SMOKE = ("DS26-0036", "DS29-0082")
TIMING = tuple(TIMING_IDS)
SEARCH_BUDGET = ("v5_one_seed", "v5_first_ranked")
SEARCH_CONTROL = "search-budget/orbit_projector.jsonl.gz"
INITIAL_RANK = "v5_initial_rank1"
BROAD_RANK = "v5_first_ranked_broad"
INITIAL_CONTROL = "v5_initial_best3"
PROJECTOR = "orbit_projector"
SHARED_SEARCH = "v5_shared_search"
SHARED_DEADLINE_CASE = "DS26-0122"
SHARED_CASES = (*SMOKE, SHARED_DEADLINE_CASE, "DS29-0174")
SHARED_ORIGINAL = (
    "original-receipt.json",
    "original-positions.jsonl.gz",
    "original-stock-positions.jsonl.gz",
)
SHARED_FOLLOWUP = ("followup-receipt.json", "followup-position.jsonl.gz")
FIELD_METHOD = "anonymous_beacon_arcs"
FIELD_FILES = ("plan.json", "prediction-lock.json", "positions.jsonl.gz", "scores.json")
RAW_ROBUST = "raw_robust"
RAW_FILES = ("prediction-lock.json", "positions.jsonl.gz", "control-positions.jsonl.gz")
FRESH_METHODS = ("joint_pass_id", "pass_geometry")
FRESH_FILES = (
    "prediction-lock.json",
    "input-lock.json",
    "source-lock.json",
    "capture-input-lock.json",
    "capture-manifest.json",
    "offers.json",
    "predictions.jsonl.gz",
    "scores.json",
)


@dataclass(frozen=True)
class Study:
    title: str
    caption: str
    candidate: str
    cases: tuple[str, ...] = TIMING
    control: str | None = None
    variant: str | None = None
    stock_variant: str | None = None
    wrong: str | None = None


@dataclass(frozen=True)
class Page:
    name: str
    method: str
    title: str
    subtitle: str
    rows: list[Mark]
    scope: str = "roof"
    labels: dict | None = None
    show_terminal_counts: bool = False


STUDIES = {
    "v5_one_seed": Study(
        "V5 with one discovery seed",
        "Use one initial discovery seed, then fit through the v5 cavity stage on all detected "
        "visits. Both runs use the causal TLEs and the original tile.",
        "search-budget/v5_one_seed.jsonl.gz",
        control=SEARCH_CONTROL,
    ),
    "v5_first_ranked": Study(
        "V5 with one ranked initial branch",
        "Fit the first ranked branch from the original discovery roster, then run through the "
        "v5 cavity stage on all stored GLRT detections in the original tile.",
        "search-budget/v5_first_ranked.jsonl.gz",
        control=SEARCH_CONTROL,
    ),
    INITIAL_RANK: Study(
        "V5 first-ranked and best-of-three initial fixes",
        "Read initial positions from the same original v5 archive per recording. The first-ranked "
        "and selected best-of-three branches both stop before downstream recovery.",
        "search-budget/initial-checkpoints/v5_initial_rank1.jsonl.gz",
        control="search-budget/initial-checkpoints/v5_initial_best3.jsonl.gz",
    ),
    BROAD_RANK: Study(
        "First-ranked compact v5 on the scheduled roof cohort",
        "Replay the branch disagreements and preselected agreement controls. Stock and the four "
        "v5 references span the full roof corpus. Unmeasured cases stay in the denominator.",
        "search-budget/broad/v5_first_ranked_broad.jsonl.gz",
        control="search-budget/broad/orbit_projector.jsonl.gz",
    ),
    "v5_prefix_180": Study(
        "Compact v5 with 180 seconds of detector factors",
        "Fit the first 180 seconds of eligible visits from the original sample counter. "
        "The matched stock uses the full exposure with the same compact projector and cavity fit.",
        "prefix/prefix-positions.jsonl.gz",
        control="prefix/full-positions.jsonl.gz",
        variant="capture-era-prefix",
        stock_variant="capture-era-full",
    ),
    "v5_prefix_180_raw": Study(
        "Compact v5 after 180 seconds of raw-IQ replay",
        "Replay both physical lanes of the authenticated first 180 seconds through ordinary "
        "native GLRT. The matched stock uses ordinary native detections over the full exposure.",
        "prefix/raw-prefix-positions.jsonl.gz",
        cases=SMOKE,
        control="prefix/ordinary-native-full-positions.jsonl.gz",
        variant="ordinary-native-raw-prefix",
        stock_variant="ordinary-native-full-control",
    ),
    SHARED_SEARCH: Study(
        "Compact v5 with shared branch search · original paired attempts",
        "Four paired attempts on complete stored detections. DS26-0122 stock returned a fix. "
        "Its candidate was still running when the joint 650-second deadline expired.",
        "shared-search/original-positions.jsonl.gz",
        cases=SHARED_CASES,
        control="shared-search/original-stock-positions.jsonl.gz",
    ),
    "joint_pass_id": Study(
        "Satellite identity from native carrier and frame timing",
        "Select satellite identities on early visits and verify the fit on later visits. "
        "This run supplies the original 25 km tile to the GLRT-only receiver.",
        "joint-pass/matched-tile.jsonl.gz",
        wrong="joint-pass/omitted-tile.jsonl.gz",
    ),
    "robust_em": Study(
        "Robust satellite association and position fit",
        "Fit both calibration arms from archived anonymous GLRT tracks and causal orbits. "
        "This run supplies the original 25 km tile.",
        "robust-em/positions.jsonl.gz",
        wrong="robust-em/wrong-region.jsonl.gz",
    ),
    "refine_bank": Study(
        "Fused GLRT refinement through v5",
        "Replay fused refinement on the scheduled IQ sample, then use archived detections for "
        "the remaining visits. The capture-era control uses the same original recording.",
        "glrt-refinement/positions.jsonl.gz",
        cases=SMOKE,
        control="glrt-refinement/control-positions.jsonl.gz",
    ),
}


@lru_cache(maxsize=1)
def _frozen_roof():
    _, files = corpus._selection("roof16")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    refs = {r["id"]: r for r in corpus.references("ds26-common127")}
    refs.update({r["id"]: r for r in corpus.references("roof16") if r["group"] == "DS29"})
    return refs, inputs


def _exact(records, cases, context):
    if set(records) != set(cases) or len(records) != len(cases):
        raise ValueError(f"{context} does not cover the prespecified recording roster")


def _read_bound(path, cases, identity, *, mode=None):
    records = read_predictions(path)
    _exact(records, cases, path)
    _, inputs = _frozen_roof()
    field, expected = identity
    for ident, record in records.items():
        if record.get(field) != expected or (mode is not None and record.get("mode") != mode):
            raise ValueError(f"{path} has an unexpected method or policy for {ident}")
        for kind in ("native", "catalog"):
            if record.get(kind + "_sha256") != inputs[ident][kind]["sha256"]:
                raise ValueError(f"{path} has an unmatched {kind} digest for {ident}")
        result = record["result"]
        if (
            result["status"] in ("ok", "withheld")
            and result["metrics"].get("position_attempted") is not False
            and "arms" not in result
        ):
            raise ValueError(f"{path} omitted the measured position arms for {ident}")
    return records


def _shared_attempts(folder, files, cases):
    receipt = _json(folder / files[0])
    _exact(receipt["cases"], cases, files[0])
    attempts = []
    for filename in files[1:]:
        method = (
            "compact_finish" if filename == "original-stock-positions.jsonl.gz" else SHARED_SEARCH
        )
        path = folder / filename
        _verify_seal(path, receipt["files"][filename])
        rows = read_predictions(path)
        _exact(rows, cases, path)
        if any(row.get("method") != method for row in rows.values()):
            raise ValueError(f"{path} differs from the assigned method")
        attempts.append(rows)
    return attempts


def _shared_pages(arm, evidence):
    study = STUDIES[SHARED_SEARCH]
    frozen, _ = _frozen_roof()
    folder = evidence / "shared-search"
    cases = study.cases
    candidate, stock = _shared_attempts(folder, SHARED_ORIGINAL, cases)
    _exact_pair(candidate, stock, cases, ("input_sha256", "cpu"))
    initial = candidate[SHARED_DEADLINE_CASE]["result"]
    if (
        initial["status"] != "timed_out"
        or any(row["result"]["status"] != "ok" for row in stock.values())
        or any(a.get("forced_latlon") is not None for a in initial.get("arms", {}).values())
    ):
        raise ValueError("shared-search original deadline evidence differs from the saved attempt")
    first = Page(
        SHARED_SEARCH,
        SHARED_SEARCH,
        study.title,
        study.caption,
        _visible_marks([frozen[k] for k in sorted(cases)], candidate, SHARED_SEARCH, arm, stock),
    )
    if not all((folder / name).is_file() for name in SHARED_FOLLOWUP):
        return [first]
    case = SHARED_DEADLINE_CASE
    (followup,) = _shared_attempts(folder, SHARED_FOLLOWUP, (case,))
    _exact_pair(followup, stock, (case,), ("input_sha256", "cpu"))
    if followup[case].get("qualification") != "standalone_corroboration":
        raise ValueError("shared-search confirmation requires a separately identified worker")
    return [
        first,
        Page(
            f"{SHARED_SEARCH}-followup",
            SHARED_SEARCH,
            "Shared search · DS26-0122 confirmation",
            "One same-input candidate follow-up with its own 650-second deadline. The stock "
            "fix is from the original pair. The original timeout remains on the paired page.",
            _visible_marks([frozen[case]], followup, SHARED_SEARCH, arm, {case: stock[case]}),
        ),
    ]


def _exact_pair(candidate, control, cases, matched_fields):
    for ident in cases:
        if any(
            candidate[ident].get(key) is None or candidate[ident][key] != control[ident].get(key)
            for key in matched_fields
        ):
            raise ValueError(f"paired results differ in their matched provenance for {ident}")


def _search_budget(method, study, evidence):
    archive = method in (INITIAL_RANK, BROAD_RANK)
    cases = tuple(_frozen_roof()[0]) if archive else TIMING
    other_match = {
        INITIAL_RANK: ("source_archive_sha256",),
        BROAD_RANK: (),
    }.get(method, ("cpu",))
    stock_method = INITIAL_CONTROL if method == INITIAL_RANK else PROJECTOR
    folder = (evidence / study.candidate).parent
    receipt = _json(folder / "receipt.json")
    _exact(receipt["cases"], cases, "search-budget receipt")
    paired = []
    for name, name_in_row in ((study.candidate, method), (study.control, stock_method)):
        path = evidence / name
        _verify_seal(path, receipt["files"].get(path.name))
        paired.append(_read_bound(path, cases, ("method", name_in_row)))
    candidate, control = paired
    _exact_pair(candidate, control, cases, ("input_sha256", *other_match))
    if method == INITIAL_RANK:
        for case in cases:
            first = candidate[case]["result"]["metrics"]
            best = control[case]["result"]["metrics"]
            if (
                first["cold_rank"] != 0
                or best["cold_rank"] != best["winning_rank"]
                or any(
                    first[key] != best[key]
                    for key in ("winning_rank", "center_scores", "refreshed_c0_objectives")
                )
            ):
                raise ValueError(
                    f"archived initial branches differ in search provenance for {case}"
                )
    return cases, candidate, control


def _visible_marks(refs, records, method, arm, controls=None, ordinary=None, *, additional=None):
    extra = dict(additional or {})
    if controls is not None:
        extra["stock"] = controls
    if ordinary is not None:
        extra["all_visits"] = ordinary
    rows = marks(refs, records, None, method, arm, additional_modes=extra)
    if not any(m.series == "one_forced" and m.error_km is not None for m in rows):
        rows = [m for m in rows if m.series != "one_forced"]
    return rows


def _refine_pair(study, evidence):
    records = read_predictions(evidence / study.candidate)
    stock = read_predictions(evidence / study.control)
    _, inputs = _frozen_roof()
    _exact(records, SMOKE, "refine-bank position trials")
    _exact(stock, SMOKE, "refine-bank capture-era controls")
    for case in SMOKE:
        candidate, baseline = records[case], stock[case]
        archive = inputs[case]["native"]["sha256"]
        metrics = candidate["result"]["metrics"]
        if (
            (candidate["method"], candidate["variant"], baseline["method"])
            != ("refine_bank", "partial-iq-refine-bank", "refine_bank_capture_control")
            or candidate.get("source_archive_sha256") != archive
            or baseline.get("source_archive_sha256") != archive
            or baseline.get("input_sha256") != f"sha256:{archive}"
            or metrics.get("control_input_sha256") != baseline["input_sha256"]
        ):
            raise ValueError(f"refine-bank replay differs from its capture-era control for {case}")
        folder = (evidence / study.candidate).parent
        detector = candidate["detector_receipts_sha256"]
        for split in ("development", "holdout"):
            stage = folder / f"{case}-{split}.json.gz"
            _verify_seal(stage, detector[split])
    return records, stock


def _roof_page(arm, method, study, evidence):
    frozen, inputs = _frozen_roof()
    cases, stock = study.cases, None
    if method in (*SEARCH_BUDGET, INITIAL_RANK):
        cases, records, stock = _search_budget(method, study, evidence)
    elif method == "refine_bank":
        records, stock = _refine_pair(study, evidence)
    else:
        identity = ("variant", study.variant) if study.variant else ("method", method)
        mode = "matched-tile" if study.wrong else None
        records = _read_bound(evidence / study.candidate, cases, identity, mode=mode)
        if study.control:
            stock = _read_bound(evidence / study.control, cases, ("variant", study.stock_variant))
    if method in ("v5_prefix_180", "v5_prefix_180_raw"):
        for case in cases:
            candidate, baseline = records[case], stock[case]
            metrics = candidate["result"]["metrics"]
            stock_metrics = baseline["result"]["metrics"]
            for key in ("catalogue_latest_sha256", "causal_cutoff_utc_ns", "kernel_sha256"):
                if metrics.get(key) is None or metrics[key] != stock_metrics.get(key):
                    raise ValueError(f"{method} changed the matched {key} for {case}")
    if study.wrong:
        for case, row in records.items():
            supplied = row.get("offer", row.get("tile"))
            expected = inputs[case]["regions"][0]
            if (
                not supplied
                or any(supplied.get(k) != expected[k] for k in ("id", "center"))
                or (supplied.get("width_km", 25) != expected.get("width_km", 25))
            ):
                raise ValueError(f"{method} matched-tile trial used the wrong offer for {case}")
            if (
                method == "robust_em"
                and row.get("observation_sha256") != inputs[case]["observation"]
            ):
                raise ValueError(f"{method} used a different anonymous track projection for {case}")
    ordered = sorted(cases)
    rows = _visible_marks([frozen[case] for case in ordered], records, method, arm, stock)
    return Page(method, method, study.title, study.caption, rows), records


def _broad_pages(arm, evidence):
    study = STUDIES[BROAD_RANK]
    cases, candidate, stock = _search_budget(BROAD_RANK, study, evidence)
    _, _, initial = _search_budget(INITIAL_RANK, STUDIES[INITIAL_RANK], evidence)
    frozen, _ = _frozen_roof()
    differing = {ident for ident in cases if initial[ident]["result"]["metrics"]["winning_rank"]}
    agreements = sorted(
        set(cases) - differing - set(TIMING),
        key=lambda ident: sha256(f"v5-first-ranked-broad-v1:{ident}".encode()).hexdigest(),
    )
    expected = differing | set(agreements[:3]) | set(TIMING)
    if len(differing) != 31 or differing.intersection(TIMING) != {"DS26-0036"}:
        raise ValueError("first-ranked full roster differs from the prespecified replay selection")
    for ident in cases:
        row = candidate[ident]
        if ident in TIMING:
            signal = "six_pair_replay"
        elif ident in expected:
            signal = "broad_fresh"
        else:
            signal = "unmeasured_agreement"
        result = row["result"]
        unmeasured = ident not in expected
        if (
            row.get("source") != signal
            or stock[ident].get("source") != "archived_projector"
            or (result["status"] == "missing") != unmeasured
            or (
                unmeasured
                and (
                    row.get("worker_wall_s") is not None
                    or any(
                        endpoint.get("forced_latlon") is not None
                        for endpoint in result.get("arms", {}).values()
                    )
                )
            )
        ):
            raise ValueError(
                f"first-ranked broad receipt misstates the replay decision for {ident}"
            )
    measured = sorted(expected)
    sample_count, unmeasured_count = len(measured), len(cases) - len(measured)
    wide = _visible_marks(
        [frozen[case] for case in sorted(cases)], candidate, BROAD_RANK, arm, stock
    )
    paired = _visible_marks(
        [frozen[case] for case in measured],
        {case: candidate[case] for case in measured},
        BROAD_RANK,
        arm,
        {case: stock[case] for case in measured},
    )
    return [
        Page(
            BROAD_RANK,
            BROAD_RANK,
            study.title,
            f"{sample_count} candidate replays and {unmeasured_count} unmeasured agreements. "
            f"{study.caption}",
            wide,
        ),
        Page(
            f"{BROAD_RANK}-replayed",
            BROAD_RANK,
            "First-ranked compact v5 on the paired replay subset",
            f"{sample_count} recordings with a candidate attempt, selected by archived branch "
            "rank and prespecified agreement controls. Failures remain in the replay denominator.",
            paired,
        ),
    ]


def _raw_robust_pages(arm, evidence, ordinary=ORDINARY):
    folder = evidence / "raw-robust"
    lock = _json(folder / "prediction-lock.json")
    _exact(lock["cases"], TIMING, "raw robust prediction seal")
    pair = []
    for name in RAW_FILES[1:]:
        path = folder / name
        _verify_seal(path, lock["files"][name])
        rows = read_predictions(path)
        _exact(rows, TIMING, path)
        pair.append(rows)
    candidate, stock = pair

    ordinary_receipt = _json(ordinary / "recording-receipts.json")
    pred_path = ordinary / "positions.jsonl.gz"
    native = ordinary_receipt["recordings"]
    _exact(native, TIMING, "ordinary native recording receipts")
    if (
        sha256(gzip.decompress(pred_path.read_bytes())).hexdigest()
        != ordinary_receipt["rows_sha256"]
    ):
        raise ValueError("ordinary v5 reference differs from its recording receipt")
    ordinary_v5 = read_predictions(pred_path)
    _exact(ordinary_v5, TIMING, "ordinary native v5 measurements")

    frozen, inputs = _frozen_roof()
    for case in TIMING:
        capture, ordinary_run = stock[case], candidate[case]
        case_input = inputs[case]
        tile = case_input["regions"][0]
        for row, variant, digest in (
            (capture, "capture-era-artifact", case_input["native"]["sha256"]),
            (
                ordinary_run,
                "fresh-iq" if case in SMOKE else "ordinary-native-artifact",
                native[case]["native_sha256"],
            ),
        ):
            supplied = row["tile"]
            if (
                row["variant"] != variant
                or row["method"] != RAW_ROBUST
                or row["mode"] != "matched-tile"
                or row["native_sha256"] != digest
                or row["catalog_sha256"] != case_input["catalog"]["sha256"]
                or row["implementation_sha256"] != lock["robust_em"]["robust_em.py"]
                or supplied["id"] != tile["id"]
                or supplied["center"] != tile["center"]
            ):
                raise ValueError(
                    f"raw robust source differs from its locked acquisition for {case}"
                )
        if any(
            capture[key] != ordinary_run[key]
            for key in ("capture_authority", "track_config_sha256")
        ):
            raise ValueError(
                f"raw robust detector comparison changed track or capture policy for {case}"
            )
        if ordinary_run["acquisition"].get("replayed_here") != (case in SMOKE):
            raise ValueError(f"raw robust receipt misstates the IQ replay for {case}")

    book = []
    for name, title, source, cases in (
        (
            "raw_robust-fresh",
            "Robust position fit after two fresh ordinary IQ replays",
            "Replay both lanes of the full recording through ordinary native GLRT.",
            SMOKE,
        ),
        (
            "raw_robust-stored",
            "Robust position fit on four stored ordinary detector artifacts",
            "Reuse whole-recording ordinary native detections.",
            tuple(case for case in TIMING if case not in SMOKE),
        ),
    ):
        marks = _visible_marks(
            [frozen[k] for k in cases],
            {k: candidate[k] for k in cases},
            RAW_ROBUST,
            arm,
            {k: stock[k] for k in cases},
            {k: ordinary_v5[k] for k in cases},
        )
        book.append(
            Page(
                name,
                RAW_ROBUST,
                title,
                f"{source} Both robust arms rebuild their anonymous tracks. Controls include "
                "the same robust fit on capture-era detections and v5 on ordinary detections.",
                marks,
            )
        )
    return book


def _wrong_page(arm, method, study, evidence, correct, *, single_alt=False):
    frozen, _ = _frozen_roof()
    path = evidence / study.wrong
    if method == "robust_em" or single_alt:
        cases = ("DS26-0036",)
        omitted = _read_bound(path, cases, ("method", method), mode="wrong-region")
        inventory = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())
        case = cases[0]
        expected = inventory[case]
        row = omitted[case]
        if row.get("tile") != expected["regions"][0] or (
            row.get("observation_sha256") != expected["observation_sha256"]
        ):
            raise ValueError("robust EM wrong-region trial differs from its frozen alternate offer")
        roster = "One DS26 recording receives its original tile or the frozen alternate r0 tile."
    else:
        queries = {ref["id"]: ref for ref in corpus.references("transfer124")}
        bindings = {r["id"]: r for r in cold_transfer_figures._frozen_bindings(queries)}
        cases = tuple(cold_missing.CASES)
        omitted = _read_bound(path, cases, ("method", method), mode="omitted-tile")
        for ident, row in omitted.items():
            binding = bindings[ident]
            if row.get("offer") != binding["supplied_tile"] or any(
                row.get(key) != binding[key] for key in ("query_id", "query_sha256")
            ):
                raise ValueError(f"{path} has an unmatched omitted offer for {ident}")
            if queries[binding["query_id"]]["truth"] != frozen[ident]["truth"]:
                raise ValueError("wrong-region query does not share the roof reference")
        roster = "Three DS29 cases receive their original tile or the first frozen wrong offer."
    if any(
        correct[k]["implementation_sha256"] != omitted[k]["implementation_sha256"] for k in cases
    ):
        raise ValueError("wrong-region comparison requires the same implementation in both modes")

    refs = [frozen[case] for case in cases]
    actual = _visible_marks(refs, {k: correct[k] for k in cases}, method, arm)
    wrong = _visible_marks(refs, omitted, method, arm)
    rows = []
    for cohort, data in (
        ("Original roof tile supplied", actual),
        ("Correct roof region omitted", wrong),
    ):
        for mark in data:
            if data is wrong and mark.series in ROLES:
                continue
            series = {"one": "candidate", "one_forced": "diagnostic"}.get(mark.series, mark.series)
            rows.append(replace(mark, dataset=cohort, series=series))
    return Page(
        f"{method}-wrong-region",
        method,
        f"{study.title} with a wrong region",
        f"{roster} V5 references use the original tile. A published wrong-offer point is false.",
        rows,
        scope="transfer",
    )


def _field_page(arm, evidence):
    folder = evidence / "physical-transfer"
    plan_path, lock_path, predictions_path, scores_path = (folder / name for name in FIELD_FILES)
    lock = json.loads(lock_path.read_bytes())
    for path, field in ((plan_path, "plan_sha256"), (predictions_path, "positions_sha256")):
        if sha256(path.read_bytes()).hexdigest() != lock[field]:
            raise ValueError(f"{path} differs from its physical transfer seal")
    plan = json.loads(plan_path.read_bytes())
    expected_sites = {f"field-site-{i:02d}" for i in range(5, 9)}
    labels = {
        "global": "Global search",
        "supplied-tile": "Correct tile supplied",
        "omitted-tile": "Correct region omitted",
    }
    positions = read_predictions(predictions_path)
    _exact(positions, [row["alias"] for row in plan["cases"]], "physical transfer")
    planned = {(c["mode"], c["site_group"]) for c in plan["cases"]}
    if len(planned) != len(plan["cases"]) or planned != set(product(labels, expected_sites)):
        raise ValueError("physical transfer requires all three modes on the fixed four sites")
    scored = json.loads(scores_path.read_bytes())["rows"]
    scores = {(r["id"], r["arm"]): r for r in scored}
    if len(scores) != len(scored) or scores.keys() != set(product(positions, ARMS)):
        raise ValueError("physical transfer scores differ from their prediction roster")
    refs = {ref["id"]: ref for ref in corpus.references("transfer124")}
    per_site = {}
    per_mode = {mode: [] for mode in labels}
    for row in plan["cases"]:
        ident, mode, site = (row[k] for k in ("alias", "mode", "site_group"))
        prediction = positions[ident]
        if (
            prediction.get("method"),
            prediction.get("mode"),
            prediction.get("input_sha256"),
            prediction.get("implementation_sha256"),
        ) != (
            FIELD_METHOD,
            mode,
            row["input_sha256"],
            plan["implementation_sha256"],
        ):
            raise ValueError("physical transfer prediction differs from its input plan")
        ref = refs[row["original_case"]]
        if ref["group"] != "StarLoc" or per_site.setdefault(site, ref["id"]) != ref["id"]:
            raise ValueError("physical transfer modes must share one measured capture per site")
        result = prediction["result"]
        endpoint = result.get("arms", {}).get(arm, {})
        score = scores[ident, arm]
        if (
            score["method"],
            score["mode"],
            score["site_group"],
            score["status"],
            score["publication"],
        ) != (
            FIELD_METHOD,
            mode,
            site,
            result["status"],
            endpoint.get("latlon") is not None,
        ):
            raise ValueError("physical transfer score differs from its saved decision")
        pair = []
        for series, key, score_key in (
            ("candidate", "latlon", "published_error_km"),
            ("diagnostic", "forced_latlon", "forced_error_km"),
        ):
            error = distance_km(endpoint.get(key), ref["truth"])
            saved = score[score_key]
            if not _same_error(error, saved):
                raise ValueError("physical transfer geographic error differs from sealed positions")
            state = "published" if series == "candidate" else "diagnostic"
            if error is None:
                state = (
                    "no_estimate"
                    if series == "diagnostic"
                    else ("withheld" if result["status"] == "ok" else result["status"])
                )
            pair.append(Mark(labels[mode], site, series, state, error))
        per_mode[mode].extend(pair)
    rows = [
        row
        for mode in per_mode.values()
        for row in mode
        if row.series != "diagnostic"
        or any(m.series == "diagnostic" and m.error_km is not None for m in mode)
    ]
    return Page(
        FIELD_METHOD,
        FIELD_METHOD,
        "Anonymous beacon arcs at four measured field sites",
        "One StarLoc capture per held-out site group. All three searches use prepared measured "
        "tracks and causal TLEs. The worldwide false fix remains a published point.",
        rows,
        scope="transfer",
    )


def _json(path):
    return json.loads(path.read_bytes())


def _verify_seal(path, expected):
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"{path} differs from its frozen content hash")


def _same_error(measured, saved):
    if measured is None or saved is None:
        return measured is saved
    return isclose(measured, saved, abs_tol=1e-8, rel_tol=0)


def _fresh_evidence(folder):
    prediction_lock = _json(folder / "prediction-lock.json")
    input_lock = _json(folder / "input-lock.json")
    capture_lock = _json(folder / "capture-input-lock.json")
    for name, expected in (
        ("input-lock.json", prediction_lock["input_lock_sha256"]),
        ("predictions.jsonl.gz", prediction_lock["predictions_sha256"]),
        ("source-lock.json", input_lock["sources_sha256"]),
        ("capture-input-lock.json", input_lock["captures_sha256"]),
        ("offers.json", input_lock["offers_sha256"]),
        ("capture-manifest.json", capture_lock["manifest_sha256"]),
    ):
        _verify_seal(folder / name, expected)
    offered = _json(folder / "offers.json")
    cases = [row["id"] for row in offered]
    if (
        len(set(cases)) != 9
        or cases != prediction_lock["cases"]
        or prediction_lock["methods"] != list(FRESH_METHODS)
        or prediction_lock["mode"] != "supplied-tile"
    ):
        raise ValueError("fresh scenes require both frozen methods on all nine offers")
    offered = {row["id"]: row for row in offered}
    scored = _json(folder / "scores.json")
    labels = scored["labels"]
    _exact(labels, cases, "fresh scene labels")
    if sha256(encoded(labels) + b"\n").hexdigest() != input_lock["labels_sha256"]:
        raise ValueError("fresh scene labels differ from their pre-prediction commitment")
    present = {r["capture_id"]: r["latlon"] for r in labels.values() if r["condition"] == "present"}
    missing = {r["capture_id"]: r["latlon"] for r in labels.values() if r["condition"] == "missing"}
    shuffled = [r for r in labels.values() if r["condition"] == "shuffle"]
    if (
        len(present) != 4
        or present != missing
        or None in present.values()
        or len(shuffled) != 1
        or shuffled[0]["capture_id"] in present
        or shuffled[0]["latlon"] is not None
    ):
        raise ValueError("fresh scenes require four matched sites and one unlocated shuffle")

    manifest = _json(folder / "capture-manifest.json")["cases"]
    with gzip.open(folder / "predictions.jsonl.gz", "rt") as stream:
        raw = list(map(json.loads, stream))
    predictions = {(r["method"], r["id"]): r for r in raw}
    _exact(predictions, set(product(FRESH_METHODS, cases)), "fresh scene predictions")
    scores = {(r["method"], r["id"], r["arm"]): r for r in scored["cases"]}
    _exact(scores, set(product(FRESH_METHODS, cases, ARMS)), "fresh scene scores")
    if len(predictions) != len(raw) or len(scores) != len(scored["cases"]):
        raise ValueError("fresh scenes repeat a prediction or score")
    for (_, ident), row in predictions.items():
        query = offered[ident]
        if (
            row["tile"] != query["tile"]
            or row["mode"] != "supplied-tile"
            or row["capture_id"] != query["capture_id"]
            or row["capture_id"] != labels[ident]["capture_id"]
            or row["native_sha256"] != manifest[row["capture_id"]]
            or row["catalog_sha256"] != cold_scenes.CATALOG_SHA256
        ):
            raise ValueError("fresh scene prediction differs from its frozen offered input")
        validate_result(row["result"])
    return labels, predictions, scores


def _fresh_page(arm, method, evidence):
    labels, predictions, scores = _fresh_evidence(evidence / "fresh-scenes")
    modes = {
        "present": "Correct synthetic tile",
        "missing": "Correct synthetic region omitted",
        "shuffle": "Shuffled detections · no site",
    }
    rows = []
    for condition, cohort in modes.items():
        group = []
        for ident, label in labels.items():
            if label["condition"] != condition:
                continue
            prediction = predictions[method, ident]
            result = prediction["result"]
            endpoint = result.get("arms", {}).get(arm, {})
            score = scores[method, ident, arm]
            center = prediction["tile"]["center"]
            published = endpoint.get("latlon") is not None
            state = "withheld" if result["status"] == "ok" and not published else result["status"]
            if (
                score["capture_id"] != label["capture_id"]
                or score["condition"] != condition
                or score["mode"] != prediction["mode"]
                or score["status"] != state
                or score["published"] != published
                or score["false_publication"] != (published and condition != "present")
                or score["tile_latlon"] != center
                or not _same_error(distance_km(center, label["latlon"]), score["center_error_km"])
            ):
                raise ValueError("fresh scene score differs from its sealed offer and decision")
            for series, key, score_key in (
                ("candidate", "latlon", "error_km"),
                ("diagnostic", "forced_latlon", "forced_error_km"),
            ):
                point = endpoint.get(key)
                error = distance_km(point, label["latlon"])
                if score[key] != point or not _same_error(error, score[score_key]):
                    raise ValueError("fresh scene error differs from the sealed position")
                status = (
                    ("published" if published else state)
                    if series == "candidate"
                    else ("diagnostic" if point is not None else "no_estimate")
                )
                group.append(Mark(cohort, label["capture_id"], series, status, error))
        rows.extend(
            row
            for row in group
            if row.series != "diagnostic"
            or any(m.series == "diagnostic" and m.error_km is not None for m in group)
        )
    title = {
        "joint_pass_id": "Satellite identity on four new synthetic scenes",
        "pass_geometry": "Pass geometry on four new synthetic scenes",
    }
    return Page(
        f"{method}-fresh-scenes",
        method,
        title[method],
        "Four synthetic captures each receive a correct or wrong 25 km tile. The shuffled "
        "negative has no geographic truth. A point from a wrong offer is a false publication.",
        rows,
        scope="transfer",
    )


def _available(evidence):
    available = []
    for method, study in STUDIES.items():
        names = [study.candidate]
        if study.control:
            names.append(study.control)
        if method in (*SEARCH_BUDGET, INITIAL_RANK, BROAD_RANK):
            names.append((Path(study.candidate).parent / "receipt.json").as_posix())
        if method == SHARED_SEARCH:
            names.append("shared-search/original-receipt.json")
        if all((evidence / name).is_file() for name in names):
            available.append(method)
    if all((evidence / "physical-transfer" / name).is_file() for name in FIELD_FILES):
        available.append(FIELD_METHOD)
    if all((evidence / "raw-robust" / name).is_file() for name in RAW_FILES):
        available.append(RAW_ROBUST)
    if all((evidence / "fresh-scenes" / name).is_file() for name in FRESH_FILES):
        if "joint_pass_id" not in available:
            available.append("joint_pass_id")
        available.append("pass_geometry")
    return available


def pages(arm, selected=None, evidence=REPORT):
    if arm not in ARMS:
        raise ValueError("select an available calibration arm")
    evidence = Path(evidence)
    selected = list(dict.fromkeys(selected or _available(evidence)))
    if unknown := set(selected) - STUDIES.keys() - {FIELD_METHOD, RAW_ROBUST, *FRESH_METHODS}:
        raise ValueError(f"unknown short-receiver modifications: {sorted(unknown)}")
    if not selected:
        raise ValueError("no complete short-receiver evidence is available")
    book = []
    for method in selected:
        if method == FIELD_METHOD:
            book.append(_field_page(arm, evidence))
            continue
        if method == BROAD_RANK:
            book.extend(_broad_pages(arm, evidence))
            continue
        if method == SHARED_SEARCH:
            book.extend(_shared_pages(arm, evidence))
            continue
        if method == RAW_ROBUST:
            book.extend(_raw_robust_pages(arm, evidence))
            continue
        fresh = method in FRESH_METHODS and all(
            (evidence / "fresh-scenes" / name).is_file() for name in FRESH_FILES
        )
        if fresh:
            book.append(_fresh_page(arm, method, evidence))
        if method == "pass_geometry" and not fresh:
            raise ValueError("complete pass geometry fresh scene receipts are unavailable")
        if method not in STUDIES or (
            fresh and not (evidence / STUDIES[method].candidate).is_file()
        ):
            continue
        study = STUDIES[method]
        roof, records = _roof_page(arm, method, study, evidence)
        book.append(roof)
        if study.wrong and (evidence / study.wrong).is_file():
            book.append(_wrong_page(arm, method, study, evidence, records))
    return book


def generate(out, arms=ARMS, methods=None, *, evidence=REPORT):
    """Write matched roof figures and separate transfer figures for saved trials."""
    return render(
        out, arms, lambda arm: pages(arm, methods, evidence), title="Short-receiver position errors"
    )


def _book_roster(pages):
    names = [page.name for page in pages]
    if len(set(names)) != len(names):
        raise ValueError("book has a duplicate chart name")
    return {
        (page.name, page.method, page.title, page.subtitle, page.scope): Counter(
            (row.dataset, row.recording, row.series)
            for row in page.rows
            if row.series != "diagnostic" and not row.series.endswith("_forced")
        )
        for page in pages
    }


def render(out, arms, pages_for_arm, *, title, fit_titles=False):
    """Export two calibration books and their position atlas manifest."""
    arms = tuple(arms)
    if not arms or len(arms) != len(set(arms)) or set(arms) - set(ARMS):
        raise ValueError("select one or both distinct calibration arms")
    out = local_output(out)
    books = {arm: pages_for_arm(arm) for arm in arms}
    roster = _book_roster(books[arms[0]])
    if any(_book_roster(books[arm]) != roster for arm in arms[1:]):
        raise ValueError("calibration arms have different figure or recording rosters")
    manifest = []
    for arm, book in books.items():
        directory = out / arm
        for scope, filename in (("roof", "modifications"), ("transfer", "transfer")):
            selected = [page for page in book if page.scope == scope]
            if not selected:
                continue
            pdf = io.BytesIO()
            source_rows = []
            metadata = dict(Title=title, CreationDate=None, ModDate=None)
            with PdfPages(pdf, metadata=metadata) as document:
                for page in selected:
                    if scope == "roof":
                        figure = draw(
                            page.rows,
                            page.method,
                            arm,
                            page.subtitle,
                            title=page.title,
                            series_labels=page.labels,
                            show_terminal_counts=page.show_terminal_counts,
                        )
                    else:
                        figure = prototype_figures.draw(
                            prototype_figures.Page(page.name, page.title, page.subtitle, page.rows),
                            arm,
                            series_labels=page.labels,
                            show_terminal_counts=page.show_terminal_counts,
                        )
                    path = f"{page.name}.png"
                    try:
                        if fit_titles:
                            heading = next(
                                text for text in figure.texts if text.get_text() == page.title
                            )
                            bounds = heading.get_window_extent()
                            available = 0.975 * figure.bbox.width - bounds.x0
                            while bounds.width > available and heading.get_fontsize() > 1:
                                size = heading.get_fontsize()
                                heading.set_fontsize(
                                    min(size - 0.25, size * available / bounds.width)
                                )
                                bounds = heading.get_window_extent()
                        save_png(figure, directory / path)
                        document.savefig(figure, facecolor="white")
                    finally:
                        plt.close(figure)
                    manifest.append(
                        dict(
                            id=page.name,
                            method=page.method,
                            title=page.title,
                            arm=arm,
                            scope=scope,
                            datasets=list(dict.fromkeys(row.dataset for row in page.rows)),
                            image=f"{arm}/{path}",
                            pdf=f"{arm}/{filename}.pdf",
                            csv=f"{arm}/{filename}.csv",
                        )
                    )
                    source_rows.extend(
                        dict(figure=page.name, arm=arm, **asdict(row)) for row in page.rows
                    )
            write(directory / f"{filename}.pdf", pdf.getvalue())
            csv_file(directory / f"{filename}.csv", source_rows)
    write(out / "manifest.json", encoded(manifest) + b"\n")
    readme = [
        f"# {title}",
        "",
        "Roof plots compare each study on its scheduled recordings against all four original v5 "
        "options. Matched stock fits use the inputs and solver boundary described on each page. "
        "Blank rows retain failed or withheld attempts in the denominator. Diagnostic estimates "
        "appear only when a receiver saved one.",
        "",
        "Wrong-region and independent-site results have their own figures. V5 enters only the "
        "paired original-tile comparisons. A false published point remains visible.",
        "",
    ]
    if out.parent.name == "2026_11_19_position_atlas":
        readme[2:2] = ["[Complete position atlas](../index.html)", ""]
    labels = {"c0": "Zero calibration", "fitted_c": "Fitted calibration"}
    for scope, heading in (
        ("roof", "Roof comparisons"),
        ("transfer", "Wrong regions and new sites"),
    ):
        entries = [r for r in manifest if r["scope"] == scope]
        if not entries:
            continue
        readme.extend((f"## {heading}", ""))
        for arm in arms:
            arm_entries = [r for r in entries if r["arm"] == arm]
            if not arm_entries:
                continue
            first = arm_entries[0]
            readme.extend(
                (
                    f"**{labels[arm]}** · [PDF]({first['pdf']}) · [Per-sample CSV]({first['csv']})",
                    "",
                )
            )
            readme.extend(f"- [{row['title']}]({row['image']})" for row in arm_entries)
            readme.append("")
    write(out / "README.md", ("\n".join(readme).rstrip() + "\n").encode())
    return manifest
