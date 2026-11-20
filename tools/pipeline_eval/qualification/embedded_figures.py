"""Chart the primary results of the ten embedded positioning prototypes on DS26."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from ..corpus import references
from ..scoring import ARMS, distance_km

REPORT = Path(__file__).resolve().parents[3] / "reports/2026_11_19_receiver_duty/embedded"
ARCHIVE = "primary-results.zip"
PROTOTYPES = {
    "early_stream": (
        "01_stream",
        "Streaming Doppler tracker",
        "Causal tracks and scan-end fixes from saved detector candidates. "
        "The replay starts after waveform detection.",
    ),
    "early_pilots": (
        "02_pilots",
        "Guided pilot search with blind reacquisition",
        "Full-scan fixes replay saved detector candidates with pilot gates and blind scouting. "
        "The raw-IQ cross-check used a separate sample of short windows.",
    ),
    "early_consensus": (
        "03_consensus",
        "Satellite-family consensus",
        "A robust vote across satellite families uses archived Doppler tracks and causal orbits.",
    ),
    "early_compact": (
        "04_compact",
        "Packed Doppler orbit table",
        "A packed orbit table and continuous position fit use archived Doppler tracks.",
    ),
    "early_stationary": (
        "05_stationary",
        "Stationary site forecast from prior fixes",
        "A median of earlier completed fixes forecasts position at scan start. "
        "The forecast uses zero current-scan radio samples and assumes the receiver stays put.",
    ),
    "early_coreset": (
        "06_coreset",
        "12 tracks chosen by geometry",
        "The position fit uses 12 archived Doppler tracks selected for horizontal geometry.",
    ),
    "early_differences": (
        "07_differences",
        "Doppler changes only",
        "The position fit uses paired frequency changes from archived Doppler tracks. "
        "Both calibration arms produce the same positions.",
    ),
    "early_grid": (
        "08_grid",
        "Marginalized position grid",
        "A coarse-to-fine position grid uses archived Doppler tracks and compares "
        "competing satellite identities.",
    ),
    "early_events": (
        "09_events",
        "Pass-event timing only",
        "Event times come from saved detector output. Ambiguity checks withheld all eight fixes.",
    ),
    "early_network": (
        "10_network",
        "Tiny coordinate network",
        "A network trained on synthetic examples predicts position from a Doppler map "
        "built from archived tracks. Both calibration arms produce the same positions.",
    ),
}
TITLES = {slug: title for slug, (_, title, _) in PROTOTYPES.items()}


def pack(source, directory):
    """Bundle the original report files byte for byte for offline chart generation."""
    names = ["comparison.json", "panel.json", "scoring-reference.json", "scores.csv"]
    names.extend(f"{report}/result.json" for report, _, _ in PROTOTYPES.values())
    data = BytesIO()
    with ZipFile(data, "w") as bundle:
        for name in names:
            bundle.writestr(
                ZipInfo(name), (source / name).read_bytes(), ZIP_DEFLATED, compresslevel=9
            )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ARCHIVE).write_bytes(data.getvalue())


def _read(bundle, name, expected):
    data = bundle.read(name)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{name} differs from the published source digest")
    return json.loads(data)


def _check_score(point, status, truth, score):
    case = f"{score['method']} {score['case']} {score['arm']}"
    coordinates = [score["latitude_deg"], score["longitude_deg"]]
    expected_point = list(map(float, coordinates)) if any(coordinates) else None
    if point != expected_point or status != score["status"]:
        raise ValueError(f"{case} endpoint differs from the published score row")
    error = distance_km(point, truth)
    if error is None:
        if score["error_km"]:
            raise ValueError(f"{case} has a geographic score without an issued position")
    elif not math.isclose(error, float(score["error_km"]), rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"{case} coordinate-derived error differs from the published score")


def _predictions(document, refs, scores, report):
    cases = document["cases"]
    if Counter(row["case"] for row in cases) != Counter(refs.keys()):
        raise ValueError(f"{report} does not contain one result per DS26 recording")
    predictions = {}
    for row in cases:
        case = row["case"]
        if set(row["arms"]) != set(ARMS):
            raise ValueError(f"{report} {case} needs both calibration arms")
        arms = {}
        for arm, endpoint in row["arms"].items():
            point, status = endpoint.get("latlon"), endpoint["status"]
            if status == "abstain" and point is None and endpoint.get("reason"):
                arms[arm] = {"latlon": None, "reason": endpoint["reason"]}
            elif status == "estimate" and point is not None:
                arms[arm] = {"latlon": point, "rf_rms_hz": endpoint["rms_hz"]}
            else:
                raise ValueError(f"{report} {case} {arm} has an invalid positioning decision")
            _check_score(point, status, refs[case]["truth"], scores[report, case, arm])
        published = any(endpoint["latlon"] is not None for endpoint in arms.values())
        predictions[case] = {
            "result": dict(
                status="ok" if published else "withheld",
                reason=None if published else "prototype withheld both endpoints",
                boundary=document["timing_scope"],
                metrics={},
                arms=arms,
            )
        }
    return predictions


def pages(arm, selected, directory=None):
    from ..figure_books import Page
    from ..position_figure import marks

    selected = selected or TITLES
    refs = {r["id"]: r for r in references("roof16") if r["group"] == "DS26"}
    result = []
    with ZipFile((directory or REPORT) / ARCHIVE) as bundle:
        comparison = json.loads(bundle.read("comparison.json"))
        digests = comparison["evidence_sha256"]
        panel = _read(bundle, "panel.json", digests["panel.json"])["cases"]
        site = _read(bundle, "scoring-reference.json", digests["scoring-reference.json"])
        truth = [site["latitude_deg"], site["longitude_deg"]]
        if panel != comparison["panel"] or panel != list(refs) or len(panel) != 8:
            raise ValueError("prototype recordings differ from the frozen DS26 roof roster")
        if site != comparison["reference"] or any(r["truth"] != truth for r in refs.values()):
            raise ValueError("prototype scoring site differs from the frozen DS26 roof reference")
        score_rows = list(csv.DictReader(bundle.read("scores.csv").decode().splitlines()))
        scores = {(r["method"], r["case"], r["arm"]): r for r in score_rows}
        if len(scores) != len(score_rows):
            raise ValueError("duplicated prototype score row")
        for case, ref in refs.items():
            for calibration in ARMS:
                baseline = ref["reference"]["baseline"][calibration]
                _check_score(
                    baseline["latlon"], "estimate", truth, scores["v5_r0", case, calibration]
                )
        for slug in selected:
            report, _, subtitle = PROTOTYPES[slug]
            document = _read(bundle, f"{report}/result.json", comparison["result_sha256"][report])
            predictions = _predictions(document, refs, scores, report)
            rows = marks(list(refs.values()), predictions, None, slug, arm)
            result.append(Page(slug, slug, subtitle, rows))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="the original embedded prototypes report directory"
    )
    parser.add_argument("--out", type=Path, default=REPORT, help="the evidence directory")
    args = parser.parse_args()
    pack(args.source, args.out)
